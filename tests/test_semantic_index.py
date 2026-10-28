import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from semantic_support import FixtureEncoder, ScopeEntry, index_database, publish, selected_scope

from toolsmith.result import Failure, unwrap
from toolsmith.semantic import (
    Scope,
    Source,
    check_index,
    encode_query,
    fingerprint,
    indexed_digest,
    initialize_index,
    invalidate_embedding,
    prepare_embedding,
    publish_embedding,
    search_embeddings,
)


def test_generic_sources_ranking_candidates_and_idempotent_reuse() -> None:
    with index_database() as connection:
        sources = [
            Source("weather", "rain makes wet roads"),
            Source("bank", "bank deposits and loans"),
        ]
        for source in sources:
            assert publish(connection, source)
            assert not publish(connection, source)
        candidates = tuple(
            ScopeEntry(source.reference, fingerprint(source.text)) for source in sources
        )
        result = unwrap(
            search_embeddings(
                connection,
                unwrap(encode_query("wet", FixtureEncoder())),
                selected_scope(connection, candidates),
            )
        )
        assert [hit.reference for hit in result.hits] == ["weather", "bank"]
        assert (result.indexed, result.missing, result.stale) == (2, 0, 0)
        restricted = unwrap(
            search_embeddings(
                connection,
                unwrap(encode_query("wet", FixtureEncoder())),
                selected_scope(connection, candidates[1:]),
            )
        )
        assert [hit.reference for hit in restricted.hits] == ["bank"]
        assert (
            unwrap(
                check_index(connection, {source.reference: source.text for source in sources}.get)
            ).documents
            == 2
        )


def test_stale_and_missing_sources_are_reported_and_not_searched() -> None:
    with index_database() as connection:
        publish(connection, Source("changed", "previous words"))
        candidates = (
            ScopeEntry("changed", fingerprint("new words")),
            ScopeEntry("missing", fingerprint("not indexed")),
        )
        result = unwrap(
            search_embeddings(
                connection,
                unwrap(encode_query("wet", FixtureEncoder())),
                selected_scope(connection, candidates),
            )
        )
        assert result.hits == ()
        assert (result.candidates, result.indexed, result.missing, result.stale) == (2, 0, 1, 1)


def test_corrections_and_invalidation_share_the_callers_transaction() -> None:
    with index_database() as connection:
        connection.execute("CREATE TABLE canonical (id TEXT PRIMARY KEY, text TEXT NOT NULL)")
        source = Source("doc", "original text")
        with connection:
            connection.execute(
                "INSERT INTO canonical VALUES (:reference, :text)",
                {"reference": source.reference, "text": source.text},
            )
            publish(connection, source)
        with pytest.raises(RuntimeError), connection:
            connection.execute("UPDATE canonical SET text = 'changed text'")
            assert unwrap(invalidate_embedding(connection, source.reference))
            raise RuntimeError("Controlled outer transaction failure")
        assert unwrap(indexed_digest(connection, source.reference)) == fingerprint(source.text)
        assert connection.execute("SELECT text FROM canonical").fetchone()[0] == source.text
        with connection:
            connection.execute("UPDATE canonical SET text = 'changed text'")
            assert unwrap(invalidate_embedding(connection, source.reference))
        assert unwrap(indexed_digest(connection, source.reference)) is None
        assert connection.execute("SELECT COUNT(*) FROM embedding_chunk").fetchone()[0] == 0


def test_expected_digest_rejects_concurrent_replacement_without_losing_vectors() -> None:
    with index_database() as connection:
        original = Source("doc", "original words")
        publish(connection, original)
        replacement = Source("doc", "new words")
        failed = publish_embedding(
            connection,
            unwrap(prepare_embedding(replacement, FixtureEncoder())),
            replacement,
            "2026-10-13T00:00:00Z",
            expected_digest=None,
        )
        assert isinstance(failed, Failure) and failed.code == "conflict"
        assert unwrap(indexed_digest(connection, "doc")) == fingerprint(original.text)
        assert publish(connection, replacement, fingerprint(original.text))
        assert unwrap(indexed_digest(connection, "doc")) == fingerprint(replacement.text)


@pytest.mark.parametrize(
    "corruption",
    [
        "DELETE FROM embedding_chunk",
        "UPDATE embedding_vector SET vector = zeroblob(1536)",
        "UPDATE embedding_chunk SET start_offset = 1",
        "UPDATE embedding_chunk SET text_digest = 'invalid'",
        "UPDATE embedding_document SET chunks = 2",
        "UPDATE embedding_profile SET definition = 'different'",
    ],
)
def test_corruption_never_becomes_a_successful_search_or_audit(corruption: str) -> None:
    with index_database() as connection:
        source = Source("doc", "words in source")
        publish(connection, source)
        with connection:
            connection.execute(corruption)
        assert isinstance(check_index(connection, lambda reference: source.text), Failure)
        assert isinstance(
            search_embeddings(
                connection,
                unwrap(encode_query("words", FixtureEncoder())),
                selected_scope(connection, (ScopeEntry("doc", fingerprint(source.text)),)),
            ),
            Failure,
        )


@pytest.mark.parametrize("alter", ["profile", "digest", "gap", "short", "ordinal", "vector"])
def test_forged_prepared_inputs_are_rejected_before_mutation(alter: str) -> None:
    with index_database() as connection:
        source = Source("doc", "words in source")
        prepared = unwrap(prepare_embedding(source, FixtureEncoder()))
        if alter == "profile":
            prepared = replace(prepared, profile="different")
        elif alter == "digest":
            prepared = replace(prepared, digest="0" * 64)
        else:
            chunk = prepared.chunks[0]
            if alter == "gap":
                chunk = replace(chunk, start=1)
            elif alter == "short":
                chunk = replace(chunk, end=len(source.text) - 1)
            elif alter == "ordinal":
                chunk = replace(chunk, ordinal=1)
            else:
                chunk = replace(chunk, vector=bytes(1536))
            prepared = replace(prepared, chunks=(chunk,))
        assert isinstance(
            publish_embedding(
                connection, prepared, source, "2026-10-13T00:00:00Z", expected_digest=None
            ),
            Failure,
        )
        assert connection.execute("SELECT COUNT(*) FROM embedding_document").fetchone()[0] == 0


def test_database_constraints_rollback_replacement_and_preserve_outer_work() -> None:
    with index_database() as connection:
        source = Source("doc", "original words")
        publish(connection, source)
        connection.execute(
            "CREATE TRIGGER reject_vectors BEFORE INSERT ON embedding_chunk BEGIN SELECT RAISE(ABORT, 'controlled'); END"
        )
        replacement = Source("doc", "new words")
        result = publish_embedding(
            connection,
            unwrap(prepare_embedding(replacement, FixtureEncoder())),
            replacement,
            "2026-10-13T00:00:00Z",
            expected_digest=fingerprint(source.text),
        )
        assert isinstance(result, Failure)
        assert unwrap(indexed_digest(connection, "doc")) == fingerprint(source.text)


def test_duplicate_candidates_invalid_schema_and_disabled_foreign_keys() -> None:
    with index_database() as connection:
        candidate = ScopeEntry("doc", fingerprint("text"))
        assert isinstance(
            search_embeddings(
                connection,
                unwrap(encode_query("words", FixtureEncoder())),
                selected_scope(connection, (candidate, candidate)),
            ),
            Failure,
        )
        assert isinstance(initialize_index(connection), Failure)
    connection = sqlite3.connect(":memory:")
    try:
        result = initialize_index(connection)
        assert isinstance(result, Failure) and result.code == "denied"
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0
    finally:
        connection.close()


def test_busy_database_is_deferred_not_an_unhandled_exception(tmp_path: Path) -> None:
    first = sqlite3.connect(tmp_path / "index.sqlite3", timeout=0)
    second = sqlite3.connect(tmp_path / "index.sqlite3", timeout=0)
    try:
        first.execute("PRAGMA foreign_keys = ON")
        second.execute("PRAGMA foreign_keys = ON")
        unwrap(initialize_index(first))
        first.execute("BEGIN IMMEDIATE")
        result = invalidate_embedding(second, "doc")
        assert isinstance(result, Failure) and result.code == "deferred"
    finally:
        second.close()
        first.close()


def test_busy_commit_rolls_back_the_entire_index_write(tmp_path: Path) -> None:
    first = sqlite3.connect(tmp_path / "index.sqlite3", timeout=0)
    reader = sqlite3.connect(tmp_path / "index.sqlite3", timeout=0)
    try:
        first.execute("PRAGMA foreign_keys = ON")
        unwrap(initialize_index(first))
        source = Source("doc", "original text")
        publish(first, source)
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM embedding_document").fetchone()
        replacement = Source("doc", "replacement text")
        result = publish_embedding(
            first,
            unwrap(prepare_embedding(replacement, FixtureEncoder())),
            replacement,
            "2026-10-13T00:00:00Z",
            expected_digest=fingerprint(source.text),
        )
        assert isinstance(result, Failure) and result.code == "deferred"
        assert not first.in_transaction
        reader.rollback()
        assert unwrap(indexed_digest(first, "doc")) == fingerprint(source.text)
    finally:
        reader.close()
        first.close()


def test_large_selection_is_searched_without_a_candidate_cutoff() -> None:
    with index_database() as connection:
        source = Source("original", "ordinary bank text")
        publish(connection, source)
        checksum = fingerprint(source.text)
        vector = connection.execute("SELECT vector FROM embedding_vector").fetchone()[0]
        with connection:
            connection.executemany(
                "INSERT INTO embedding_document VALUES (:value, :value_2, :checksum, :text, :value_3, :value_4)",
                (
                    {
                        "value": f"entry:{number}",
                        "value_2": connection.execute(
                            "SELECT id FROM embedding_profile"
                        ).fetchone()[0],
                        "checksum": checksum,
                        "text": len(source.text),
                        "value_3": 1,
                        "value_4": "2026-10-17T00:00:00Z",
                    }
                    for number in range(10001)
                ),
            )
            connection.executemany(
                "INSERT INTO embedding_chunk (reference, ordinal, start_offset, end_offset, text_digest) VALUES (:reference,0,0,:end_offset,:text_digest)",
                (
                    {
                        "reference": f"entry:{number}",
                        "end_offset": len(source.text),
                        "text_digest": checksum,
                    }
                    for number in range(10001)
                ),
            )
            connection.execute(
                "INSERT INTO embedding_vector(rowid,vector,chunk_id) SELECT id, :vector, id FROM embedding_chunk WHERE reference != 'original'",
                {"vector": vector},
            )
        publish(connection, Source("last-entry", "rain on wet roads"))
        report = unwrap(
            search_embeddings(
                connection,
                unwrap(encode_query("wet", FixtureEncoder())),
                Scope("embedding_document"),
                1,
            )
        )
        assert report.indexed == 10_003
        assert report.hits[0].reference == "last-entry"
