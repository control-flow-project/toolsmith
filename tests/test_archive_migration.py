import hashlib
from pathlib import Path

import pytest
from semantic_support import FixtureEncoder, index_database, publish

from toolsmith.operations.integrity import check_integrity
from toolsmith.readers.models import Document, TextPart
from toolsmith.result import Failure, unwrap
from toolsmith.retrieval import read_citation, search_text
from toolsmith.semantic import Scope, encode_query, fingerprint, migrate_index, search_embeddings
from toolsmith.storage.artifacts import put_file, read_file
from toolsmith.storage.database import initialize_store, open_store
from toolsmith.storage.migration import migrate_store
from toolsmith.storage.text import put_text


def version_one(root: Path) -> tuple[str, str]:
    unwrap(initialize_store(root, "sample"))
    text = unwrap(
        put_text(
            root,
            "sample",
            "document",
            Document("Title", (TextPart("Page", "Original archived words", 7),)),
            "text",
        )
    )
    original = unwrap(
        put_file(
            root, "sample", b"original bytes", "original.bin", "application/octet-stream", "file"
        )
    )
    with open_store(root, "sample", write=True) as store, store.connection:
        store.connection.execute("DROP TRIGGER current_text_generation")
        store.connection.execute("DROP VIEW current_text")
        store.connection.execute("ALTER TABLE collection DROP COLUMN generation")
        store.connection.execute("DROP TABLE embedding_vector")
        store.connection.execute("DROP TABLE embedding_chunk")
        store.connection.execute(
            "CREATE TABLE embedding_chunk (reference TEXT NOT NULL REFERENCES embedding_document(reference) ON DELETE CASCADE ON UPDATE CASCADE, ordinal INTEGER NOT NULL, start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL, text_digest TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(reference,ordinal))"
        )
        store.connection.execute("DROP TABLE lexical_search")
        store.connection.execute("DROP TABLE lexical_chunk")
        store.connection.execute("DROP TABLE lexical_document")
        store.connection.execute(
            "CREATE TABLE chunk (id INTEGER PRIMARY KEY, part_id INTEGER NOT NULL REFERENCES part(id), start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL, text TEXT NOT NULL, UNIQUE(part_id,start_offset,end_offset))"
        )
        store.connection.execute(
            "CREATE VIRTUAL TABLE chunk_search USING fts5(text,title,tokenize='unicode61')"
        )
        store.connection.execute("PRAGMA user_version = 1")
    return text.version, original.version


def test_forward_copy_verifies_and_preserves_original_and_exact_citations(tmp_path: Path) -> None:
    source, destination = tmp_path / "old", tmp_path / "new"
    text_version, file_version = version_one(source)
    before = hashlib.sha256((source / "toolsmith.sqlite3").read_bytes()).hexdigest()
    migrated = unwrap(migrate_store(source, "sample", destination))
    assert migrated.schema_version == 3 and migrated.text_versions == migrated.files == 1
    assert hashlib.sha256((source / "toolsmith.sqlite3").read_bytes()).hexdigest() == before
    citation = unwrap(read_citation(destination, "sample", text_version, 1))
    assert citation.text == "Original archived words" and citation.physical_page == 7
    assert unwrap(read_file(destination, "sample", file_version)) == b"original bytes"
    assert unwrap(search_text(destination, "sample", "archived"))
    assert unwrap(check_integrity(destination, "sample")).valid
    with open_store(destination, "sample") as current:
        assert (
            current.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name IN ('chunk','chunk_search')"
            ).fetchone()
            is None
        )
    assert not list(tmp_path.glob(".stage-*"))


def test_version_two_archive_forward_copy_uses_the_same_current_schema(tmp_path: Path) -> None:
    from toolsmith import lexical

    source, destination = tmp_path / "old-two", tmp_path / "new"
    version, file = version_one(source)
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(source / "toolsmith.sqlite3")) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DROP TABLE chunk_search")
        connection.execute("DROP TABLE chunk")
        unwrap(lexical.initialize_index(connection))
        for row in connection.execute(
            "SELECT p.id,p.text,v.title FROM part p JOIN text_version v ON v.id=p.version_id"
        ):
            unwrap(
                lexical.index_source(
                    connection,
                    lexical.Source("part:" + str(row[0]), row[1], row[2]),
                    expected_digest=None,
                )
            )
        connection.execute("PRAGMA user_version=2")
    before = hashlib.sha256((source / "toolsmith.sqlite3").read_bytes()).hexdigest()
    assert unwrap(migrate_store(source, "sample", destination)).schema_version == 3
    assert hashlib.sha256((source / "toolsmith.sqlite3").read_bytes()).hexdigest() == before
    assert (
        unwrap(read_citation(destination, "sample", version, 1)).text == "Original archived words"
    )
    assert unwrap(read_file(destination, "sample", file)) == b"original bytes"
    assert unwrap(check_integrity(destination, "sample")).valid


def test_generic_vector_forward_migration_preserves_exact_vectors_and_outer_rollback() -> None:
    from toolsmith.semantic import Source

    with index_database() as connection:
        source = Source("current", "rain on wet roads")
        publish(connection, source)
        old = connection.execute(
            "SELECT c.reference,c.ordinal,c.start_offset,c.end_offset,c.text_digest,v.vector FROM embedding_chunk c JOIN embedding_vector v ON v.rowid=c.id"
        ).fetchall()
        with connection:
            connection.execute("DROP TABLE embedding_vector")
            connection.execute("DROP TABLE embedding_chunk")
            connection.execute(
                "CREATE TABLE embedding_chunk (reference TEXT NOT NULL REFERENCES embedding_document(reference) ON DELETE CASCADE ON UPDATE CASCADE,ordinal INTEGER NOT NULL,start_offset INTEGER NOT NULL,end_offset INTEGER NOT NULL,text_digest TEXT NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(reference,ordinal))"
            )
            connection.executemany("INSERT INTO embedding_chunk VALUES (?,?,?,?,?,?)", old)
        assert isinstance(
            migrate_index(connection, lambda reference: "changed canonical text"), Failure
        )
        assert (
            tuple(row[1] for row in connection.execute("PRAGMA table_info(embedding_chunk)"))[-1]
            == "vector"
        )
        assert unwrap(migrate_index(connection, lambda reference: source.text)) == 1
        assert connection.execute("SELECT vector FROM embedding_vector").fetchone()[0] == old[0][-1]
        result = unwrap(
            search_embeddings(
                connection,
                unwrap(encode_query("wet", FixtureEncoder())),
                Scope("embedding_document"),
                1,
            )
        )
        assert result.hits[0].digest == fingerprint(source.text)
        assert isinstance(migrate_index(connection, lambda reference: source.text), Failure)


@pytest.mark.parametrize("failure", ["collection", "destination", "object", "schema"])
def test_failed_forward_migration_never_changes_source_or_overwrites_destination(
    tmp_path: Path, failure: str
) -> None:
    source, destination = tmp_path / "old", tmp_path / "new"
    version_one(source)
    if failure == "destination":
        destination.mkdir()
        (destination / "keep").write_bytes(b"preserved")
    elif failure == "object":
        next((source / "objects").iterdir()).write_bytes(b"corrupt")
    elif failure == "schema":
        import sqlite3

        connection = sqlite3.connect(source / "toolsmith.sqlite3")
        try:
            connection.execute("CREATE TABLE unexpected (id INTEGER)")
            connection.commit()
        finally:
            connection.close()
    before = hashlib.sha256((source / "toolsmith.sqlite3").read_bytes()).hexdigest()
    result = migrate_store(source, "wrong" if failure == "collection" else "sample", destination)
    assert isinstance(result, Failure)
    assert hashlib.sha256((source / "toolsmith.sqlite3").read_bytes()).hexdigest() == before
    assert not list(tmp_path.glob(".stage-*"))
    if failure == "destination":
        assert (destination / "keep").read_bytes() == b"preserved"
    else:
        assert not destination.exists()
