import sqlite3

import pytest
from semantic_support import index_database


def test_embedding_metadata_tables_are_strict_and_primary_keys_reject_null() -> None:
    with index_database() as connection:
        tables = {
            row[1]: row[5]
            for row in connection.execute("PRAGMA table_list")
            if row[1] in {"embedding_profile", "embedding_document", "embedding_chunk"}
        }
        assert tables == {
            "embedding_profile": 1,
            "embedding_document": 1,
            "embedding_chunk": 1,
        }
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO embedding_profile(id,definition) VALUES (:id,:definition)",
                {"id": None, "definition": "profile"},
            )


def test_embedding_metadata_rejects_wrong_storage_types() -> None:
    with index_database() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO embedding_profile(id,definition) VALUES (:id,:definition)",
            {"id": "profile", "definition": b"binary-is-not-text"},
        )


def test_embedding_profile_foreign_key_has_an_index() -> None:
    with index_database() as connection:
        indexes = [
            tuple(row[2] for row in connection.execute("PRAGMA index_info(" + index[1] + ")"))
            for index in connection.execute("PRAGMA index_list(embedding_document)")
        ]
        assert any(index[:1] == ("profile_id",) for index in indexes)
