import hashlib
from pathlib import Path

import pytest

from toolsmith.operations.integrity import check_integrity
from toolsmith.readers.models import Document, TextPart
from toolsmith.result import Failure, unwrap
from toolsmith.retrieval import read_citation, search_text
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
    assert migrated.schema_version == 2 and migrated.text_versions == migrated.files == 1
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
