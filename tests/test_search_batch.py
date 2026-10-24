import hashlib
import json
import sqlite3

import pytest
from semantic_support import FixtureEncoder, ScopeEntry, index_database, publish, selected_scope

from toolsmith import lexical, semantic
from toolsmith.result import Failure, unwrap
from toolsmith.scopes import Coverage
from toolsmith.search_batch import (
    SearchQuery,
    read_queries,
)


def test_lexical_batch_queries_one_authorized_index_without_crossing_scope() -> None:
    with index_database() as connection:
        unwrap(lexical.initialize_index(connection))
        allowed = lexical.Source("allowed", "Quarterly revenue earnings rose strongly")
        hidden = lexical.Source("hidden", "Quarterly revenue earnings secret")
        for source in (allowed, hidden):
            unwrap(lexical.index_source(connection, source, expected_digest=None))
        scope = selected_scope(
            connection,
            (ScopeEntry(allowed.reference, hashlib.sha256(allowed.text.encode()).hexdigest()),),
        )
        queries = (SearchQuery("first", "Quarterly"), SearchQuery("second", "earnings"))
        batch = unwrap(lexical.search_batch(connection, queries, scope))
        assert [item.id for item in batch.items] == ["first", "second"]
        assert [[hit.reference for hit in unwrap(item.result).hits] for item in batch.items] == [
            ["allowed"],
            ["allowed"],
        ]


def test_semantic_batch_keeps_input_identity_and_returns_each_query_result() -> None:
    with index_database() as connection:
        source = semantic.Source("weather", "Rain weather wet")
        publish(connection, source)
        scope = selected_scope(
            connection,
            (ScopeEntry(source.reference, hashlib.sha256(source.text.encode()).hexdigest()),),
        )
        queries = (SearchQuery("one", "Rain weather"), SearchQuery("two", "Wet roads"))
        batch = unwrap(semantic.search_batch(connection, queries, scope, FixtureEncoder()))
        assert [item.id for item in batch.items] == ["one", "two"]
        assert all(unwrap(item.result).hits[0].reference == "weather" for item in batch.items)


def test_one_unencodable_semantic_query_does_not_drop_other_results() -> None:
    with index_database() as connection:
        source = semantic.Source("weather", "Rain weather")
        publish(connection, source)
        scope = selected_scope(
            connection,
            (ScopeEntry(source.reference, hashlib.sha256(source.text.encode()).hexdigest()),),
        )
        batch = unwrap(
            semantic.search_batch(
                connection,
                (SearchQuery("long", "rain " * 300), SearchQuery("valid", "Rain weather")),
                scope,
                FixtureEncoder(),
            )
        )
        assert isinstance(batch.items[0].result, Failure)
        assert unwrap(batch.items[1].result).hits[0].reference == "weather"


def test_query_reader_preserves_a_large_batch_without_a_two_hundred_item_cap() -> None:
    items = [{"id": str(number), "text": "Company quarterly result"} for number in range(2500)]
    queries = unwrap(read_queries(json.dumps(items).encode()))
    assert len(queries) == 2500
    assert queries[-1].id == "2499"


@pytest.mark.parametrize(
    "value",
    [
        b"{}",
        b'[{"id":"same","text":"one"},{"id":"same","text":"two"}]',
        b'[{"id":"one","text":"value","extra":true}]',
    ],
)
def test_batch_query_input_is_validated_before_search(value: bytes) -> None:
    assert isinstance(read_queries(value), Failure)


def test_empty_batches_do_not_require_a_fake_query_or_model_call() -> None:
    with index_database() as connection:
        scope = selected_scope(connection, ())
        assert unwrap(lexical.search_batch(connection, (), scope)).items == ()
        assert unwrap(semantic.search_batch(connection, (), scope, FixtureEncoder())).items == ()


@pytest.mark.parametrize("kind", ["lexical", "semantic"])
def test_bulk_search_measures_corpus_coverage_once(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from toolsmith.lexical import index as lexical_index
    from toolsmith.semantic import index as semantic_index

    with index_database() as connection:
        source = semantic.Source("weather", "Rain weather")
        publish(connection, source)
        unwrap(lexical.initialize_index(connection))
        unwrap(
            lexical.index_source(
                connection, lexical.Source(source.reference, source.text), expected_digest=None
            )
        )
        scope = selected_scope(
            connection,
            (ScopeEntry(source.reference, hashlib.sha256(source.text.encode()).hexdigest()),),
        )
        owner = lexical_index if kind == "lexical" else semantic_index
        from toolsmith.scopes import coverage

        calls = 0

        def count(connection: sqlite3.Connection, selected: str, document: str) -> Coverage:
            nonlocal calls
            calls += 1
            return coverage(connection, selected, document)

        monkeypatch.setattr(owner, "coverage", count)
        queries = tuple(SearchQuery(str(number), "Rain weather") for number in range(250))
        result = unwrap(
            lexical.search_batch(connection, queries, scope)
            if kind == "lexical"
            else semantic.search_batch(connection, queries, scope, FixtureEncoder())
        )
        assert len(result.items) == 250 and calls == 1
