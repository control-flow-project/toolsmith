import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from semantic_support import index_database, publish

from toolsmith import lexical, semantic
from toolsmith.files import private_directory
from toolsmith.readers import inspect_html
from toolsmith.result import Failure, unwrap


@pytest.mark.parametrize("kind", ["lexical", "semantic"])
def test_readiness_relation_is_public_current_and_transactional(kind: str) -> None:
    with index_database() as connection:
        if kind == "lexical":
            unwrap(lexical.initialize_index(connection))
            unwrap(
                lexical.index_source(
                    connection, lexical.Source("record", "Clause terms"), expected_digest=None
                )
            )
            relation = unwrap(lexical.indexed_scope(connection))
            again = unwrap(lexical.indexed_scope(connection))
            invalidate = lexical.invalidate_source
        else:
            publish(connection, semantic.Source("record", "Rain weather"))
            relation = unwrap(semantic.indexed_scope(connection))
            again = unwrap(semantic.indexed_scope(connection))
            invalidate = semantic.invalidate_embedding
        assert again == relation
        assert (
            connection.execute(f'SELECT reference FROM temp."{relation.relation}"').fetchone()[0]
            == "record"
        )
        connection.commit()
        connection.execute("BEGIN")
        unwrap(invalidate(connection, "record"))
        assert (
            connection.execute(f'SELECT reference FROM temp."{relation.relation}"').fetchone()
            is None
        )
        connection.rollback()
        assert (
            connection.execute(f'SELECT reference FROM temp."{relation.relation}"').fetchone()[0]
            == "record"
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0


def test_readiness_relation_rejects_namespace_collisions_without_overwriting() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        unwrap(lexical.initialize_index(connection))
        connection.execute("CREATE TEMP TABLE toolsmith_lexical_ready (reference TEXT)")
        result = lexical.indexed_scope(connection)
        assert isinstance(result, Failure) and result.code == "conflict"
        assert (
            connection.execute(
                "SELECT type FROM sqlite_temp_master WHERE name='toolsmith_lexical_ready'"
            ).fetchone()[0]
            == "table"
        )


def test_semantic_connection_preparation_does_not_own_application_schema_or_transactions() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("CREATE TABLE application (id INTEGER PRIMARY KEY)")
        connection.execute("PRAGMA user_version = 71")
        connection.execute("INSERT INTO application VALUES (1)")
        connection.row_factory = sqlite3.Row
        assert unwrap(semantic.prepare_connection(connection))
        assert connection.in_transaction
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 71
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()[0][0]
            == "application"
        )
        connection.rollback()
        assert connection.execute("SELECT count(*) FROM application").fetchone()[0] == 0


def test_lexical_matching_relation_filters_and_counts_without_returned_record_limits() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        unwrap(lexical.initialize_index(connection))
        with connection:
            for index in range(1100):
                unwrap(
                    lexical.index_source(
                        connection,
                        lexical.Source(f"record:{index}", "Dividend recapitalization"),
                        expected_digest=None,
                    )
                )
        matched = unwrap(lexical.matching_scope(connection, "dividend"))
        assert (
            connection.execute(f'SELECT count(*) FROM temp."{matched.relation}"').fetchone()[0]
            == 1100
        )
        assert unwrap(lexical.matching_scope(connection, "dividend")) == matched
        assert (
            connection.execute(
                f'SELECT reference FROM temp."{matched.relation}" WHERE reference=:reference',
                {"reference": "record:1099"},
            ).fetchone()[0]
            == "record:1099"
        )
        connection.execute("BEGIN")
        unwrap(lexical.invalidate_source(connection, "record:1099"))
        assert (
            connection.execute(f'SELECT count(*) FROM temp."{matched.relation}"').fetchone()[0]
            == 1099
        )
        connection.rollback()
        assert (
            connection.execute(f'SELECT count(*) FROM temp."{matched.relation}"').fetchone()[0]
            == 1100
        )
        injection = unwrap(
            lexical.matching_scope(connection, "dividend'; DROP TABLE lexical_document; --")
        )
        assert (
            connection.execute(f'SELECT count(*) FROM temp."{injection.relation}"').fetchone()[0]
            == 0
        )
        assert connection.execute("SELECT count(*) FROM lexical_document").fetchone()[0] == 1100
        assert isinstance(lexical.matching_scope(connection, '"broken', mode="fts5"), Failure)


def test_html_inspection_counts_all_resources_without_a_dom_or_browser_dependency() -> None:
    result = unwrap(
        inspect_html(
            b'<html><head><title>Original</title><script src="external.js"></script></head><body><main>Observed text<img src="data:image/png,AAAA"><img src="image.png"></main></body></html>'
        )
    )
    assert result.title == "Original"
    assert "Observed text" in result.text
    assert result.content_root and result.external_resources == 2
    assert isinstance(
        inspect_html(b"<html><title>Access denied</title><body>Forbidden</body></html>"), Failure
    )


def test_explicit_private_directory_creation_handles_nested_consumers_without_following_links(
    tmp_path: Path,
) -> None:
    selected = tmp_path / "case" / "assignment" / "output"
    with private_directory(selected, create=True):
        assert selected.stat().st_mode & 0o777 == 0o700
        assert selected.parent.stat().st_mode & 0o777 == 0o700
    target = tmp_path / "outside"
    target.mkdir(mode=0o700)
    (tmp_path / "symlink").symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError), private_directory(tmp_path / "symlink" / "nested", create=True):
        pass
    assert not (target / "nested").exists()
