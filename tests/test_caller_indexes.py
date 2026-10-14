import hashlib
import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest
from semantic_support import FixtureEncoder, index_database, publish

from toolsmith import lexical, semantic
from toolsmith.result import Failure, ToolsmithError, unwrap
from toolsmith.sqlite import transaction


def checksum(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def test_library_cursors_preserve_arbitrary_application_row_factories() -> None:
    with index_database() as connection:

        def application_rows(cursor: sqlite3.Cursor, row: tuple[object, ...]) -> dict[str, object]:
            return {
                column[0]: value
                for column, value in zip(cursor.description or (), row, strict=True)
            }

        connection.row_factory = application_rows
        unwrap(lexical.initialize_index(connection))
        source = lexical.Source("source", "Source words")
        unwrap(lexical.index_source(connection, source, expected_digest=None))
        assert unwrap(lexical.inspect_index(connection, (source.reference,)))[0].digest == checksum(
            source.text
        )
        publish(connection, semantic.Source("semantic", "Rain weather"))
        assert unwrap(semantic.inspect_index(connection, ("semantic",)))[0].digest is not None
        assert connection.row_factory is application_rows
        assert connection.execute("SELECT 7 AS value").fetchone() == {"value": 7}


@pytest.mark.parametrize("kind", ["lexical", "semantic"])
def test_index_initialization_rejects_existing_or_partial_schemas(kind: str) -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        initializer = lexical.initialize_index if kind == "lexical" else semantic.initialize_index
        table = "lexical_document" if kind == "lexical" else "embedding_document"
        connection.execute("CREATE TABLE application_data (value TEXT)")
        connection.execute("INSERT INTO application_data VALUES ('Preserved')")
        connection.commit()
        connection.execute(f"CREATE TABLE {table} (unrecognized TEXT)")
        result = initializer(connection)
        assert isinstance(result, Failure) and result.code == "integrity"
        assert not connection.in_transaction
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name IN ('lexical_chunk','embedding_profile')"
        ).fetchall()
        connection.execute(f"DROP TABLE {table}")
        unwrap(initializer(connection))
        assert isinstance(initializer(connection), Failure)
        assert connection.execute("SELECT value FROM application_data").fetchone()[0] == "Preserved"


def test_case_pages_phrases_amendments_and_authorized_candidates() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.row_factory = sqlite3.Row
        unwrap(lexical.initialize_index(connection))
        sources = (
            lexical.Source("case-a:source-1:page-1", "Restricted Payments include dividends."),
            lexical.Source(
                "case-a:amendment:page-2", "Restricted transactions and other Payments."
            ),
            lexical.Source("case-b:source-1:page-1", "Restricted Payments " * 20),
            lexical.Source("case-a:source-1:page-3", ""),
        )
        for source in sources:
            unwrap(lexical.index_source(connection, source, expected_digest=None))
        candidates = tuple(
            lexical.Candidate(source.reference, checksum(source.text))
            for source in sources
            if source.reference.startswith("case-a:")
        )
        phrase = unwrap(lexical.search(connection, '"Restricted Payments"', candidates, 1))
        assert [hit.reference for hit in phrase.hits] == [sources[0].reference]
        broad = unwrap(lexical.search(connection, "Restricted Payments", candidates))
        assert {hit.reference for hit in broad.hits} == {sources[0].reference, sources[1].reference}
        assert broad.indexed == 3 and broad.missing == broad.stale == 0
        assert (
            unwrap(
                lexical.check_index(
                    connection, {source.reference: source.text for source in sources}.get
                )
            )
            == 4
        )
        assert not unwrap(lexical.index_source(connection, sources[0], expected_digest=None))
        replacement = replace(sources[0], text="New covenant wording.")
        unwrap(
            lexical.index_source(connection, replacement, expected_digest=checksum(sources[0].text))
        )
        changed = unwrap(lexical.search(connection, "Restricted", candidates))
        assert changed.stale == 1 and all(
            hit.reference != sources[0].reference for hit in changed.hits
        )
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA trusted_schema").fetchone()[0] == 0
    finally:
        connection.close()


def test_full_page_text_is_caller_owned_and_not_a_short_archive_citation() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE physical_page (reference TEXT PRIMARY KEY, text TEXT)")
        body = "exact page text β\n" * 10000
        connection.execute("INSERT INTO physical_page VALUES ('page:1', ?)", (body,))
        unwrap(lexical.initialize_index(connection))
        unwrap(
            lexical.index_source(connection, lexical.Source("page:1", body), expected_digest=None)
        )
        assert (
            connection.execute(
                "SELECT text FROM physical_page WHERE reference='page:1'"
            ).fetchone()[0]
            == body
        )
        assert len(body) > 16384
        assert unwrap(lexical.check_index(connection, {"page:1": body}.get)) == 1
    finally:
        connection.close()


def test_article_and_both_derivatives_rollback_together() -> None:
    with index_database() as connection:
        connection.execute("PRAGMA user_version = 42")
        connection.execute("CREATE TABLE article (id TEXT PRIMARY KEY, text TEXT)")
        connection.execute("INSERT INTO article VALUES ('body', 'Original rain story')")
        connection.commit()
        unwrap(lexical.initialize_index(connection))
        original = semantic.Source("article:body", "Original rain story")
        publish(connection, original)
        unwrap(
            lexical.index_source(
                connection, lexical.Source(original.reference, original.text), expected_digest=None
            )
        )
        with (
            pytest.raises(ToolsmithError),
            transaction(connection, "consumer_correction", write=True),
        ):
            connection.execute("UPDATE article SET text='Correction' WHERE id='body'")
            unwrap(lexical.invalidate_source(connection, original.reference))
            unwrap(semantic.invalidate_embedding(connection, original.reference))
            unwrap(
                lexical.index_source(
                    connection,
                    lexical.Source(original.reference, "Correction"),
                    expected_digest="a" * 64,
                )
            )
        assert connection.execute("SELECT text FROM article").fetchone()[0] == original.text
        assert unwrap(semantic.inspect_index(connection, (original.reference,)))[
            0
        ].digest == semantic.fingerprint(original.text)
        assert unwrap(lexical.inspect_index(connection, (original.reference,)))[
            0
        ].digest == checksum(original.text)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 42


def test_bulk_semantic_metadata_does_not_read_vectors_or_canonical_text() -> None:
    with index_database() as connection:
        original = semantic.Source("body", "Rain and wet weather")
        publish(connection, original)
        connection.execute("UPDATE embedding_chunk SET vector = zeroblob(1536)")
        connection.commit()
        traced: list[str] = []
        connection.set_trace_callback(traced.append)
        states = unwrap(semantic.inspect_index(connection, ("missing", "body")))
        connection.set_trace_callback(None)
        assert states[0].digest is None
        assert states[1].digest == semantic.fingerprint(original.text)
        assert states[1].chunks == 1
        assert not any("embedding_chunk" in query or "vector" in query for query in traced)
        assert isinstance(semantic.check_index(connection, {"body": original.text}.get), Failure)


def test_semantic_filtered_representation_window_keeps_missing_and_stale_counts() -> None:
    with index_database() as connection:
        sources = (
            semantic.Source("article:1:headline", "Wet weather"),
            semantic.Source("article:1:body", "Rain caused wet weather"),
            semantic.Source("article:2:body", "Rain weather secret scope"),
        )
        for source in sources:
            publish(connection, source)
        candidates = (
            semantic.Candidate(sources[0].reference, semantic.fingerprint(sources[0].text)),
            semantic.Candidate(sources[1].reference, "a" * 64),
            semantic.Candidate("article:3:summary", "b" * 64),
        )
        result = unwrap(
            semantic.search_embeddings(
                connection, unwrap(semantic.encode_query("Rain", FixtureEncoder())), candidates, 1
            )
        )
        assert result.indexed == result.stale == result.missing == 1
        assert [hit.reference for hit in result.hits] == [sources[0].reference]


@pytest.mark.parametrize("corruption", ["text", "title", "ordinal", "count", "postings"])
def test_lexical_audit_detects_corrupt_derivatives(corruption: str) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        unwrap(lexical.initialize_index(connection))
        source = lexical.Source("page:1", "Original source words")
        unwrap(lexical.index_source(connection, source, expected_digest=None))
        if corruption == "text":
            connection.execute("UPDATE lexical_chunk SET text='Forged' WHERE reference='page:1'")
        elif corruption == "title":
            connection.execute("UPDATE lexical_search SET title='Forged'")
        elif corruption == "ordinal":
            connection.execute("UPDATE lexical_chunk SET ordinal=4")
        elif corruption == "count":
            connection.execute("UPDATE lexical_document SET chunks=9")
        else:
            connection.execute("DELETE FROM lexical_search")
        connection.commit()
        assert isinstance(
            lexical.check_index(connection, {source.reference: source.text}.get), Failure
        )
        if corruption == "title":
            assert isinstance(
                lexical.search(
                    connection,
                    "Forged",
                    (lexical.Candidate(source.reference, checksum(source.text)),),
                ),
                Failure,
            )
    finally:
        connection.close()
