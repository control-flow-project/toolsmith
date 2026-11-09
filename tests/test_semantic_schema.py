import sqlite3

import pytest
from semantic_support import index_database


def test_embedding_metadata_tables_are_strict() -> None:
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


def populate_metadata(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO embedding_profile(id,definition) VALUES (:id,:definition)",
        {"id": "profile", "definition": "profile"},
    )
    connection.execute(
        "INSERT INTO embedding_document(reference,profile_id,text_digest,characters,chunks,indexed_at) "
        "VALUES (:reference,:profile,:digest,:characters,:chunks,:indexed_at)",
        {
            "reference": "document",
            "profile": "profile",
            "digest": "digest",
            "characters": 1,
            "chunks": 1,
            "indexed_at": "2026-11-09T00:00:00Z",
        },
    )


@pytest.mark.parametrize(
    "statement,values",
    [
        (
            "INSERT INTO embedding_profile(id,definition) VALUES (:id,:definition)",
            {"id": None, "definition": "profile"},
        ),
        (
            "INSERT INTO embedding_document(reference,profile_id,text_digest,characters,chunks,indexed_at) "
            "VALUES (:reference,'profile','digest',1,1,'2026-11-09T00:00:00Z')",
            {"reference": None},
        ),
    ],
    ids=["profile-id", "document-reference"],
)
def test_embedding_text_primary_keys_reject_null(statement: str, values: dict[str, object]) -> None:
    with index_database() as connection:
        populate_metadata(connection)
        with pytest.raises(sqlite3.IntegrityError) as error:
            connection.execute(statement, values)
        assert error.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_NOTNULL


@pytest.mark.parametrize(
    "statement,values",
    [
        (
            "INSERT INTO embedding_profile(id,definition) VALUES (:id,:definition)",
            {"id": "invalid-profile", "definition": b"binary-is-not-text"},
        ),
        (
            "INSERT INTO embedding_document(reference,profile_id,text_digest,characters,chunks,indexed_at) "
            "VALUES ('invalid-document','profile','digest',:characters,1,'2026-11-09T00:00:00Z')",
            {"characters": "not-an-integer"},
        ),
        (
            "INSERT INTO embedding_chunk(reference,ordinal,start_offset,end_offset,text_digest) "
            "VALUES ('document',:ordinal,0,1,'digest')",
            {"ordinal": "not-an-integer"},
        ),
    ],
    ids=["profile-definition", "document-characters", "chunk-ordinal"],
)
def test_embedding_metadata_rejects_wrong_storage_types(
    statement: str, values: dict[str, object]
) -> None:
    with index_database() as connection:
        populate_metadata(connection)
        with pytest.raises(sqlite3.IntegrityError) as error:
            connection.execute(statement, values)
        # SQLite's extended STRICT datatype code is not exported by Python's sqlite3.
        assert error.value.sqlite_errorcode == 3091  # SQLITE_CONSTRAINT_DATATYPE


def test_embedding_profile_foreign_key_has_an_index() -> None:
    with index_database() as connection:
        indexes = [
            tuple(row[2] for row in connection.execute("PRAGMA index_info(" + index[1] + ")"))
            for index in connection.execute("PRAGMA index_list(embedding_document)")
        ]
        assert any(index[:1] == ("profile_id",) for index in indexes)
