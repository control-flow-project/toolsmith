import hashlib
import sqlite3
from contextlib import closing
from typing import cast

import pytest
from semantic_support import FixtureEncoder, ScopeEntry, index_database, publish, selected_scope

from toolsmith import lexical, semantic
from toolsmith.result import Failure, unwrap
from toolsmith.scopes import Scope


@pytest.mark.parametrize(
    "scope",
    [
        Scope("missing"),
        Scope("embedding_document; DROP TABLE embedding_document"),
        Scope("embedding_document", schema="other"),
        Scope("embedding_document", reference="unknown"),
        Scope("embedding_document", digest="text_digest) OR 1=1"),
        Scope("embedding_document", schema=cast(str, [])),
    ],
)
def test_scope_identifiers_never_become_executable_sql(scope: Scope) -> None:
    with index_database() as connection:
        result = semantic.search_embeddings(
            connection, unwrap(semantic.encode_query("wet", FixtureEncoder())), scope
        )
        assert isinstance(result, Failure) and result.code == "invalid_input"
        assert connection.execute("SELECT count(*) FROM embedding_document").fetchone()[0] == 0


@pytest.mark.parametrize(
    "entry",
    [
        ScopeEntry("", "a" * 64),
        ScopeEntry("invalid", "A" * 64),
        ScopeEntry("invalid", "short"),
        ScopeEntry("a\x00b", "a" * 64),
        ScopeEntry("a\x7fb", "a" * 64),
        ScopeEntry("a\x01b", "a" * 64),
        ScopeEntry(" ", "a" * 64),
        ScopeEntry("\u00a0", "a" * 64),
        ScopeEntry("\u2003", "a" * 64),
        ScopeEntry("é" * 101, "a" * 64),
    ],
)
def test_scope_rows_are_validated_without_a_record_count_cap(entry: ScopeEntry) -> None:
    with index_database() as connection:
        result = semantic.search_embeddings(
            connection,
            unwrap(semantic.encode_query("wet", FixtureEncoder())),
            selected_scope(connection, (entry,)),
        )
        assert isinstance(result, Failure) and result.code == "invalid_input"


def test_removed_candidate_api_is_rejected_for_both_searches() -> None:
    assert not hasattr(semantic, "Candidate") and not hasattr(lexical, "Candidate")
    with index_database() as connection:
        unwrap(lexical.initialize_index(connection))
        query = unwrap(semantic.encode_query("wet", FixtureEncoder()))
        assert isinstance(semantic.search_embeddings(connection, query, cast(Scope, ())), Failure)
        assert isinstance(lexical.search(connection, "wet", cast(Scope, ())), Failure)


def test_relational_fts_scope_exceeds_old_100000_limit_and_finds_last_entry() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        unwrap(lexical.initialize_index(connection))
        source = lexical.Source("last-entry", "Specific refinancing result")
        unwrap(lexical.index_source(connection, source, expected_digest=None))
        connection.execute(
            "CREATE TABLE permitted (reference TEXT PRIMARY KEY, text_digest TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO permitted VALUES (:value, :value_2)",
            ({"value": f"missing:{number}", "value_2": "a" * 64} for number in range(100001)),
        )
        connection.execute(
            "INSERT INTO permitted VALUES (:reference, :value)",
            {
                "reference": source.reference,
                "value": hashlib.sha256(source.text.encode()).hexdigest(),
            },
        )
        report = unwrap(lexical.search(connection, "refinancing", Scope("permitted"), 1))
        assert report.candidates == 100_002 and report.missing == 100_001
        assert report.hits[0].reference == source.reference
        assert (
            len(
                unwrap(
                    lexical.inspect_index(
                        connection, tuple(f"missing:{number}" for number in range(100_001))
                    )
                )
            )
            == 100_001
        )


def test_permission_filter_is_inside_native_knn_before_top_k() -> None:
    with index_database() as connection:
        for number in range(40):
            publish(connection, semantic.Source(f"private:{number}", "rain on wet roads"))
        source = semantic.Source("permitted", "ordinary bank lending")
        publish(connection, source)
        result = unwrap(
            semantic.search_embeddings(
                connection,
                unwrap(semantic.encode_query("wet", FixtureEncoder())),
                selected_scope(
                    connection, (ScopeEntry(source.reference, semantic.fingerprint(source.text)),)
                ),
                1,
            )
        )
        assert [hit.reference for hit in result.hits] == ["permitted"]
        assert result.indexed == 1 and result.missing == result.stale == 0


def test_native_distances_do_not_unpack_every_selected_vector() -> None:
    from unittest.mock import patch

    from toolsmith.semantic.profile import unpack_vector

    with index_database() as connection:
        for number in range(300):
            publish(connection, semantic.Source(f"entry:{number}", "ordinary bank lending"))
        with patch("toolsmith.semantic.index.unpack_vector", wraps=unpack_vector) as decoded:
            report = unwrap(
                semantic.search_embeddings(
                    connection,
                    unwrap(semantic.encode_query("wet", FixtureEncoder())),
                    Scope("embedding_document"),
                    3,
                )
            )
        assert len(report.hits) == 3 and report.indexed == 300
        assert decoded.call_count == 4


def test_missing_native_vectors_cannot_silently_shorten_a_complete_scope() -> None:
    with index_database() as connection:
        publish(connection, semantic.Source("first", "rain on wet roads"))
        publish(connection, semantic.Source("second", "ordinary bank lending"))
        connection.execute(
            "DELETE FROM embedding_vector WHERE rowid IN (SELECT id FROM embedding_chunk WHERE reference='second')"
        )
        result = semantic.search_embeddings(
            connection,
            unwrap(semantic.encode_query("wet", FixtureEncoder())),
            Scope("embedding_document"),
            20,
        )
        assert isinstance(result, Failure) and result.code == "integrity"
