import sqlite3
from collections.abc import Callable

from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.semantic.index import SCHEMA_SQL, check_index, document_row, validate_profile
from toolsmith.semantic.profile import fingerprint, unpack_vector
from toolsmith.semantic.vector import load_vector_extension
from toolsmith.sqlite import execute, transaction
from toolsmith.validation import digest, integer, source_reference


@boundary
def migrate_index(connection: sqlite3.Connection, source_text: Callable[[str], str | None]) -> int:
    load_vector_extension(connection)
    with transaction(connection, "toolsmith_vector_migration", write=True):
        columns = tuple(row[1] for row in execute(connection, "PRAGMA table_info(embedding_chunk)"))
        if columns != (
            "reference",
            "ordinal",
            "start_offset",
            "end_offset",
            "text_digest",
            "vector",
        ):
            raise ToolsmithError(
                "integrity", "Vector migration requires the reviewed raw-vector schema"
            )
        validate_profile(connection)
        execute(connection, "ALTER TABLE embedding_chunk RENAME TO migrating_embedding_chunk")
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip().startswith(
                (
                    "CREATE TABLE embedding_chunk",
                    "CREATE VIRTUAL TABLE embedding_vector",
                    "INSERT INTO embedding_vector",
                )
            ):
                execute(connection, statement)
        for row in execute(
            connection, "SELECT reference FROM embedding_document ORDER BY reference"
        ):
            reference = source_reference(row[0])
            metadata = document_row(connection, reference)
            body = source_text(reference)
            if (
                metadata is None
                or body is None
                or fingerprint(body) != metadata[0]
                or len(body) != metadata[1]
            ):
                raise ToolsmithError(
                    "integrity", "Migration source differs from its canonical text"
                )
            count = 0
            previous_end = 0
            previous_start = -1
            for chunk in execute(
                connection,
                "SELECT ordinal, start_offset, end_offset, text_digest, vector FROM migrating_embedding_chunk WHERE reference = ? ORDER BY ordinal",
                (reference,),
            ):
                start = integer(chunk[1], 0, len(body), "Chunk start")
                end = integer(chunk[2], start + 1, len(body), "Chunk end")
                if (
                    chunk[0] != count
                    or not previous_start <= start <= previous_end < end
                    or fingerprint(body[start:end]) != digest(chunk[3])
                ):
                    raise ToolsmithError(
                        "integrity", "Migration source has incomplete or mismatched vector spans"
                    )
                unpack_vector(chunk[4])
                cursor = execute(
                    connection,
                    "INSERT INTO embedding_chunk (reference, ordinal, start_offset, end_offset, text_digest) VALUES (?,?,?,?,?)",
                    (reference, count, start, end, chunk[3]),
                )
                execute(
                    connection,
                    "INSERT INTO embedding_vector (rowid, vector, chunk_id) VALUES (?,?,?)",
                    (cursor.lastrowid, chunk[4], cursor.lastrowid),
                )
                count += 1
                previous_start, previous_end = start, end
            if count != metadata[2] or previous_end != len(body):
                raise ToolsmithError("integrity", "Migration source omits retained vector chunks")
        execute(connection, "DROP TABLE migrating_embedding_chunk")
        return unwrap(check_index(connection, source_text)).documents
