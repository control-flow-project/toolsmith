import math
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files

from toolsmith.result import ToolsmithError, boundary
from toolsmith.semantic.profile import (
    MAX_CANDIDATES,
    MAX_CHUNKS,
    MAX_SEARCH_CHUNKS,
    MAX_SOURCE_BYTES,
    PROFILE_ID,
    PROFILE_JSON,
    Candidate,
    Chunk,
    Prepared,
    Source,
    fingerprint,
    source_reference,
    unpack_vector,
    validate_source,
)
from toolsmith.validation import digest, integer, timestamp

SCHEMA_SQL = files("toolsmith.semantic").joinpath("schema.sql").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Hit:
    reference: str
    digest: str
    score: float
    start: int
    end: int


@dataclass(frozen=True)
class SearchReport:
    hits: tuple[Hit, ...]
    candidates: int
    indexed: int
    missing: int
    stale: int


@dataclass(frozen=True)
class IndexReport:
    documents: int
    chunks: int
    profile: str


@contextmanager
def database_errors(connection: sqlite3.Connection) -> Iterator[None]:
    if not isinstance(connection, sqlite3.Connection):
        raise ToolsmithError("invalid_input", "Supply an explicit caller-owned SQLite connection")
    try:
        yield
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", 0) & 255
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise ToolsmithError("deferred", "Semantic index database is busy", 0.1) from error
        raise ToolsmithError("integrity", "Semantic index schema or transaction failed") from error


@contextmanager
def index_transaction(connection: sqlite3.Connection, *, write: bool = False) -> Iterator[None]:
    with database_errors(connection):
        if write and connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise ToolsmithError(
                "denied", "Caller must enable SQLite foreign keys before index writes"
            )
        owned = not connection.in_transaction
        name = "toolsmith_embedding_write" if write else "toolsmith_embedding_read"
        connection.execute("SAVEPOINT " + name)
        try:
            yield
            connection.execute("RELEASE " + name)
        except BaseException:
            if owned:
                connection.rollback()
            elif connection.in_transaction:
                connection.execute("ROLLBACK TO " + name)
                connection.execute("RELEASE " + name)
            raise


def validate_profile(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT id, definition FROM embedding_profile LIMIT 2").fetchall()
    if any(tuple(row) != (PROFILE_ID, PROFILE_JSON) for row in rows):
        raise ToolsmithError("integrity", "Index contains a different or corrupt embedding profile")


def document_row(connection: sqlite3.Connection, reference: str) -> tuple[str, int, int] | None:
    validate_profile(connection)
    row = connection.execute(
        "SELECT text_digest, characters, chunks, profile_id, indexed_at FROM embedding_document WHERE reference = ?",
        (source_reference(reference),),
    ).fetchone()
    if row is None:
        return None
    if row[3] != PROFILE_ID or timestamp(row[4]) is None:
        raise ToolsmithError("integrity", "Indexed document has invalid profile or provenance")
    return (
        digest(row[0]),
        integer(row[1], 1, MAX_SOURCE_BYTES, "Characters"),
        integer(row[2], 1, MAX_CHUNKS, "Chunk count"),
    )


def retained_chunks(
    connection: sqlite3.Connection, reference: str, characters: int, count: int
) -> Iterator[tuple[Chunk, tuple[float, ...]]]:
    previous_end = 0
    previous_start = -1
    ordinal = 0
    for row in connection.execute(
        "SELECT ordinal, start_offset, end_offset, text_digest, vector FROM embedding_chunk WHERE reference = ? ORDER BY ordinal",
        (reference,),
    ):
        start = integer(row[1], 0, characters, "Chunk start")
        end = integer(row[2], 1, characters, "Chunk end")
        if (
            row[0] != ordinal
            or ordinal >= count
            or not previous_start <= start <= previous_end < end
        ):
            raise ToolsmithError("integrity", "Stored chunks lack complete ordered source coverage")
        encoded: object = row[4]
        values = unpack_vector(encoded)
        if not isinstance(encoded, bytes):
            raise ToolsmithError("integrity", "Vector storage must contain bytes")
        yield Chunk(ordinal, start, end, digest(row[3]), encoded), values
        previous_start, previous_end = start, end
        ordinal += 1
    if ordinal != count or previous_end != characters:
        raise ToolsmithError("integrity", "Stored semantic source is incomplete")


@boundary
def initialize_index(connection: sqlite3.Connection) -> IndexReport:
    with index_transaction(connection, write=True):
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip():
                connection.execute(statement)
    return IndexReport(0, 0, PROFILE_ID)


@boundary
def indexed_digest(connection: sqlite3.Connection, reference: str) -> str | None:
    with index_transaction(connection):
        row = document_row(connection, reference)
        if row is None:
            return None
        for _ in retained_chunks(connection, reference, row[1], row[2]):
            pass
        return row[0]


def validate_prepared(prepared: Prepared, source: Source) -> None:
    validate_source(source)
    if (
        not isinstance(prepared, Prepared)
        or prepared.profile != PROFILE_ID
        or prepared.reference != source.reference
        or prepared.digest != fingerprint(source.text)
        or type(prepared.characters) is not int
        or prepared.characters != len(source.text)
        or not isinstance(prepared.chunks, tuple)
        or not 1 <= len(prepared.chunks) <= MAX_CHUNKS
    ):
        raise ToolsmithError(
            "invalid_input", "Prepared embeddings do not match the complete source/profile"
        )
    previous_end, previous_start = 0, -1
    for ordinal, chunk in enumerate(prepared.chunks):
        if (
            not isinstance(chunk, Chunk)
            or type(chunk.ordinal) is not int
            or chunk.ordinal != ordinal
            or type(chunk.start) is not int
            or type(chunk.end) is not int
            or not 0 <= chunk.start <= previous_end < chunk.end <= len(source.text)
            or chunk.start < previous_start
            or chunk.digest != fingerprint(source.text[chunk.start : chunk.end])
        ):
            raise ToolsmithError(
                "invalid_input", "Prepared chunks do not cover exact complete source spans"
            )
        unpack_vector(chunk.vector)
        previous_start, previous_end = chunk.start, chunk.end
    if previous_end != len(source.text):
        raise ToolsmithError("invalid_input", "Prepared chunks omit source characters")


@boundary
def publish_embedding(
    connection: sqlite3.Connection,
    prepared: Prepared,
    source: Source,
    indexed_at: str,
    *,
    expected_digest: str | None,
) -> bool:
    validate_prepared(prepared, source)
    recorded = timestamp(indexed_at)
    if recorded is None:
        raise ToolsmithError(
            "invalid_input", "Index publication requires a timezone-aware timestamp"
        )
    expected = None if expected_digest is None else digest(expected_digest)
    with index_transaction(connection, write=True):
        previous = document_row(connection, source.reference)
        if previous is not None:
            for _ in retained_chunks(connection, source.reference, previous[1], previous[2]):
                pass
            if previous[0] == prepared.digest:
                return False
        if (None if previous is None else previous[0]) != expected:
            raise ToolsmithError(
                "conflict", "Indexed source changed while encoding; publication was rolled back"
            )
        connection.execute(
            "DELETE FROM embedding_document WHERE reference = ?", (source.reference,)
        )
        connection.execute(
            "INSERT OR IGNORE INTO embedding_profile (id, definition) VALUES (?, ?)",
            (PROFILE_ID, PROFILE_JSON),
        )
        connection.execute(
            "INSERT INTO embedding_document (reference, profile_id, text_digest, characters, chunks, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                source.reference,
                PROFILE_ID,
                prepared.digest,
                prepared.characters,
                len(prepared.chunks),
                recorded,
            ),
        )
        connection.executemany(
            "INSERT INTO embedding_chunk (reference, ordinal, start_offset, end_offset, text_digest, vector) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    source.reference,
                    chunk.ordinal,
                    chunk.start,
                    chunk.end,
                    chunk.digest,
                    chunk.vector,
                )
                for chunk in prepared.chunks
            ],
        )
    return True


@boundary
def invalidate_embedding(connection: sqlite3.Connection, reference: str) -> bool:
    selected = source_reference(reference)
    with index_transaction(connection, write=True):
        validate_profile(connection)
        cursor = connection.execute(
            "DELETE FROM embedding_document WHERE reference = ?", (selected,)
        )
        return cursor.rowcount > 0


@boundary
def search_embeddings(
    connection: sqlite3.Connection,
    query: bytes,
    candidates: tuple[Candidate, ...],
    maximum_records: int = 20,
) -> SearchReport:
    maximum = integer(maximum_records, 1, 100, "Maximum records")
    values = unpack_vector(query)
    if not isinstance(candidates, tuple) or len(candidates) > MAX_CANDIDATES:
        raise ToolsmithError("limit", "Supply at most 10000 explicit authorized candidates")
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Candidate):
            raise ToolsmithError("invalid_input", "Supply typed authorized semantic candidates")
        reference = source_reference(candidate.reference)
        digest(candidate.digest)
        if reference in seen:
            raise ToolsmithError("invalid_input", "Semantic candidates must have unique references")
        seen.add(reference)
    missing, stale = 0, 0
    scanned_chunks = 0
    winners: list[Hit] = []
    with index_transaction(connection):
        validate_profile(connection)
        for candidate in candidates:
            row = document_row(connection, candidate.reference)
            if row is None:
                missing += 1
                continue
            if row[0] != candidate.digest:
                stale += 1
                continue
            scanned_chunks += row[2]
            if scanned_chunks > MAX_SEARCH_CHUNKS:
                raise ToolsmithError(
                    "limit",
                    "Selected semantic candidates exceed 100000 chunks; select a smaller authorized set",
                )
            best: Hit | None = None
            for chunk, chunk_values in retained_chunks(
                connection, candidate.reference, row[1], row[2]
            ):
                score = math.fsum(
                    left * right for left, right in zip(values, chunk_values, strict=True)
                )
                hit = Hit(
                    candidate.reference, row[0], max(-1.0, min(1.0, score)), chunk.start, chunk.end
                )
                if best is None or hit.score > best.score:
                    best = hit
            if best is None:
                raise ToolsmithError("integrity", "Indexed source has no vector chunks")
            winners.append(best)
            winners.sort(key=lambda hit: (-hit.score, hit.reference))
            if len(winners) > maximum:
                winners.pop()
    return SearchReport(
        tuple(winners), len(candidates), len(candidates) - missing - stale, missing, stale
    )


@boundary
def check_index(
    connection: sqlite3.Connection, source_text: Callable[[str], str | None]
) -> IndexReport:
    with index_transaction(connection):
        validate_profile(connection)
        documents, chunks = 0, 0
        if (
            connection.execute(
                "SELECT 1 FROM embedding_chunk c LEFT JOIN embedding_document d ON d.reference = c.reference WHERE d.reference IS NULL LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise ToolsmithError("integrity", "Index contains orphan vector chunks")
        for document in connection.execute(
            "SELECT reference FROM embedding_document ORDER BY reference"
        ):
            reference = source_reference(document[0])
            row = document_row(connection, reference)
            if row is None:
                raise ToolsmithError("integrity", "Indexed document is missing")
            body = source_text(reference)
            if body is None or fingerprint(body) != row[0] or len(body) != row[1]:
                raise ToolsmithError("integrity", "Indexed canonical source is missing or changed")
            for chunk, _ in retained_chunks(connection, reference, row[1], row[2]):
                if fingerprint(body[chunk.start : chunk.end]) != chunk.digest:
                    raise ToolsmithError(
                        "integrity", "Vector span differs from the canonical source"
                    )
                chunks += 1
            documents += 1
        return IndexReport(documents, chunks, PROFILE_ID)
