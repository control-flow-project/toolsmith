import math
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from importlib.resources import files

from toolsmith.result import Failure, Success, ToolsmithError, boundary, unwrap
from toolsmith.scopes import Coverage, Scope, coverage, scope_query
from toolsmith.search_batch import (
    EmbeddingQuery,
    QueryResult,
    SearchBatch,
    SearchQuery,
    validate_queries,
)
from toolsmith.semantic.chunks import Encoder, encode_query
from toolsmith.semantic.profile import (
    MAX_CHUNKS,
    MAX_SOURCE_BYTES,
    PROFILE_ID,
    PROFILE_JSON,
    Chunk,
    Prepared,
    Source,
    fingerprint,
    unpack_vector,
    validate_source,
)
from toolsmith.semantic.vector import load_vector_extension
from toolsmith.sqlite import execute, transaction
from toolsmith.validation import digest, integer, source_reference, text, timestamp

SCHEMA_SQL = files("toolsmith.semantic").joinpath("schema.sql").read_text(encoding="utf-8")


@boundary
def prepare_connection(connection: sqlite3.Connection) -> bool:
    load_vector_extension(connection)
    return True


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


def validate_profile(connection: sqlite3.Connection) -> None:
    rows = execute(connection, "SELECT id, definition FROM embedding_profile LIMIT 2").fetchall()
    if any(tuple(row) != (PROFILE_ID, PROFILE_JSON) for row in rows):
        raise ToolsmithError("integrity", "Index contains a different or corrupt embedding profile")
    if (
        not rows
        and execute(connection, "SELECT 1 FROM embedding_document LIMIT 1").fetchone() is not None
    ):
        raise ToolsmithError("integrity", "Indexed sources have no retained profile")


def document_row(connection: sqlite3.Connection, reference: str) -> tuple[str, int, int] | None:
    validate_profile(connection)
    row = execute(
        connection,
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
    for row in execute(
        connection,
        "SELECT c.ordinal, c.start_offset, c.end_offset, c.text_digest, v.vector, v.chunk_id, c.id FROM embedding_chunk c LEFT JOIN embedding_vector v ON v.rowid = c.id WHERE c.reference = ? ORDER BY c.ordinal",
        (reference,),
    ):
        start = integer(row[1], 0, characters, "Chunk start")
        end = integer(row[2], 1, characters, "Chunk end")
        if (
            row[0] != ordinal
            or row[5] != row[6]
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
    load_vector_extension(connection)
    with transaction(connection, "toolsmith_embedding", write=True):
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip():
                execute(connection, statement)
    return IndexReport(0, 0, PROFILE_ID)


@boundary
def indexed_digest(connection: sqlite3.Connection, reference: str) -> str | None:
    load_vector_extension(connection)
    with transaction(connection, "toolsmith_embedding"):
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
    load_vector_extension(connection)
    validate_prepared(prepared, source)
    recorded = timestamp(indexed_at)
    if recorded is None:
        raise ToolsmithError(
            "invalid_input", "Index publication requires a timezone-aware timestamp"
        )
    expected = None if expected_digest is None else digest(expected_digest)
    with transaction(connection, "toolsmith_embedding", write=True):
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
        remove_embedding(connection, source.reference)
        execute(
            connection,
            "INSERT OR IGNORE INTO embedding_profile (id, definition) VALUES (?, ?)",
            (PROFILE_ID, PROFILE_JSON),
        )
        execute(
            connection,
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
        for chunk in prepared.chunks:
            cursor = execute(
                connection,
                "INSERT INTO embedding_chunk (reference, ordinal, start_offset, end_offset, text_digest) VALUES (?, ?, ?, ?, ?)",
                (source.reference, chunk.ordinal, chunk.start, chunk.end, chunk.digest),
            )
            execute(
                connection,
                "INSERT INTO embedding_vector (rowid, vector, chunk_id) VALUES (?, ?, ?)",
                (cursor.lastrowid, chunk.vector, cursor.lastrowid),
            )
    return True


def remove_embedding(connection: sqlite3.Connection, reference: str) -> bool:
    execute(
        connection,
        "DELETE FROM embedding_vector WHERE rowid IN (SELECT id FROM embedding_chunk WHERE reference = ?)",
        (reference,),
    )
    return (
        execute(
            connection, "DELETE FROM embedding_document WHERE reference = ?", (reference,)
        ).rowcount
        > 0
    )


@boundary
def invalidate_embedding(connection: sqlite3.Connection, reference: str) -> bool:
    load_vector_extension(connection)
    selected = source_reference(reference)
    with transaction(connection, "toolsmith_embedding", write=True):
        validate_profile(connection)
        return remove_embedding(connection, selected)


@boundary
def _search_in_scope(
    connection: sqlite3.Connection,
    query: bytes,
    selected: str,
    observed: Coverage,
    maximum: int,
) -> SearchReport:
    unpack_vector(query)
    seen: set[str] = set()
    winners: list[Hit] = []
    with transaction(connection, "toolsmith_embedding"):
        rows = execute(
            connection,
            "SELECT c.id, c.reference, d.text_digest, c.start_offset, c.end_offset, c.text_digest, v.distance FROM embedding_vector(?, ?) v CROSS JOIN embedding_chunk c CROSS JOIN embedding_document d CROSS JOIN ("
            + selected
            + ") s WHERE v.chunk_id IN (SELECT allowed.id FROM embedding_chunk allowed JOIN embedding_document current ON current.reference = allowed.reference JOIN ("
            + selected
            + ") permitted ON permitted.reference = current.reference AND permitted.text_digest = current.text_digest) AND c.id = v.rowid AND v.chunk_id = c.id AND d.reference = c.reference AND s.reference = d.reference AND s.text_digest = d.text_digest",
            (query, '{"K":' + str(maximum * max(1, observed.largest_source_chunks)) + "}"),
        )
        try:
            for row in rows:
                reference = source_reference(row[1])
                if reference in seen:
                    continue
                metadata = document_row(connection, reference)
                if metadata is None:
                    raise ToolsmithError("integrity", "Vector hit has no indexed source")
                spans = execute(
                    connection,
                    "SELECT count(*), min(start_offset), max(end_offset) FROM embedding_chunk WHERE reference = ?",
                    (reference,),
                ).fetchone()
                if tuple(spans) != (metadata[2], 0, metadata[1]):
                    raise ToolsmithError(
                        "integrity", "Indexed source has incomplete chunk metadata"
                    )
                start = integer(row[3], 0, metadata[1], "Match start")
                end = integer(row[4], start + 1, metadata[1], "Match end")
                digest(row[5])
                vector = execute(
                    connection, "SELECT vector FROM embedding_vector WHERE rowid = ?", (row[0],)
                ).fetchone()
                if vector is None:
                    raise ToolsmithError("integrity", "Vector hit has no retained vector")
                unpack_vector(vector[0])
                if type(row[6]) not in {float, int} or not math.isfinite(row[6]):
                    raise ToolsmithError("integrity", "Native vector distance is not finite")
                winners.append(
                    Hit(reference, digest(row[2]), max(-1.0, min(1.0, 1.0 - row[6])), start, end)
                )
                seen.add(reference)
                if len(winners) == min(maximum, observed.indexed):
                    break
        finally:
            rows.close()
        if len(winners) != min(maximum, observed.indexed):
            raise ToolsmithError("integrity", "Indexed scope has incomplete retained vector hits")
    return SearchReport(
        tuple(winners), observed.entries, observed.indexed, observed.missing, observed.stale
    )


@boundary
def search_embeddings(
    connection: sqlite3.Connection,
    query: bytes,
    scope: Scope,
    maximum_records: int = 20,
) -> SearchReport:
    maximum = integer(maximum_records, 1, 100, "Maximum records")
    load_vector_extension(connection)
    with transaction(connection, "toolsmith_embedding_search"):
        validate_profile(connection)
        selected = scope_query(connection, scope)
        observed = coverage(connection, selected, "embedding_document")
        return unwrap(_search_in_scope(connection, query, selected, observed, maximum))


@boundary
def search_batch(
    connection: sqlite3.Connection,
    queries: tuple[SearchQuery, ...],
    scope: Scope,
    encoder: Encoder,
    maximum_records: int = 20,
) -> SearchBatch[SearchReport]:
    checked = validate_queries(queries)
    maximum = integer(maximum_records, 1, 100, "Maximum records")
    if not checked:
        return SearchBatch(())
    encoded = tuple(QueryResult(query.id, encode_query(query.text, encoder)) for query in checked)
    return _search_encoded_batch(connection, encoded, scope, maximum)


@boundary
def search_embeddings_batch(
    connection: sqlite3.Connection,
    queries: tuple[EmbeddingQuery, ...],
    scope: Scope,
    maximum_records: int = 20,
) -> SearchBatch[SearchReport]:
    maximum = integer(maximum_records, 1, 100, "Maximum records")
    if not isinstance(queries, tuple) or any(
        not isinstance(query, EmbeddingQuery) for query in queries
    ):
        raise ToolsmithError("invalid_input", "Supply typed embedding queries")
    identities = [text(query.id, 300, "Query id") for query in queries]
    if len(set(identities)) != len(identities) or any(
        not isinstance(query.vector, bytes) for query in queries
    ):
        raise ToolsmithError(
            "invalid_input", "Embedding query ids must be unique and vectors must be bytes"
        )
    if sum(len(query.vector) + len(query.id.encode()) for query in queries) > 32 * 1024 * 1024:
        raise ToolsmithError(
            "limit", "Embedding query input exceeds 32 MiB; process remaining inputs explicitly"
        )
    return _search_encoded_batch(
        connection,
        tuple(QueryResult(query.id, Success(query.vector)) for query in queries),
        scope,
        maximum,
    )


def _search_encoded_batch(
    connection: sqlite3.Connection,
    queries: tuple[QueryResult[bytes], ...],
    scope: Scope,
    maximum: int,
) -> SearchBatch[SearchReport]:
    if not queries:
        return SearchBatch(())
    load_vector_extension(connection)
    with transaction(connection, "toolsmith_embedding_batch"):
        validate_profile(connection)
        selected = scope_query(connection, scope)
        observed = coverage(connection, selected, "embedding_document")
        return SearchBatch(
            tuple(
                QueryResult(
                    query.id,
                    query.result
                    if isinstance(query.result, Failure)
                    else _search_in_scope(
                        connection, query.result.value, selected, observed, maximum
                    ),
                )
                for query in queries
            )
        )


@boundary
def relocate_embedding(
    connection: sqlite3.Connection, old_reference: str, source: Source, *, expected_digest: str
) -> bool:
    load_vector_extension(connection)
    previous_reference = source_reference(old_reference)
    validate_source(source)
    expected = digest(expected_digest)
    if fingerprint(source.text) != expected:
        raise ToolsmithError(
            "conflict", "Reference relocation requires the same exact canonical text"
        )
    with transaction(connection, "toolsmith_embedding", write=True):
        previous = document_row(connection, previous_reference)
        if previous is None or previous[0] != expected:
            raise ToolsmithError("conflict", "Indexed source changed before reference relocation")
        for chunk, _ in retained_chunks(connection, previous_reference, previous[1], previous[2]):
            if fingerprint(source.text[chunk.start : chunk.end]) != chunk.digest:
                raise ToolsmithError(
                    "integrity", "Relocated vectors do not match canonical source spans"
                )
        if previous_reference == source.reference:
            return False
        if document_row(connection, source.reference) is not None:
            raise ToolsmithError("conflict", "Target reference already has derivatives")
        execute(
            connection,
            "UPDATE embedding_document SET reference = ? WHERE reference = ?",
            (source.reference, previous_reference),
        )
        return True


@boundary
def clear_index(connection: sqlite3.Connection) -> int:
    load_vector_extension(connection)
    with transaction(connection, "toolsmith_embedding", write=True):
        count = execute(connection, "SELECT count(*) FROM embedding_document").fetchone()[0]
        execute(connection, "DELETE FROM embedding_vector")
        execute(connection, "DELETE FROM embedding_document")
        execute(connection, "DELETE FROM embedding_profile")
        return integer(count, 0, 2**63 - 1, "Cleared source count")


@boundary
def check_index(
    connection: sqlite3.Connection, source_text: Callable[[str], str | None]
) -> IndexReport:
    load_vector_extension(connection)
    with transaction(connection, "toolsmith_embedding"):
        validate_profile(connection)
        documents, chunks = 0, 0
        if (
            execute(
                connection,
                "SELECT 1 FROM embedding_chunk c LEFT JOIN embedding_document d ON d.reference = c.reference WHERE d.reference IS NULL LIMIT 1",
            ).fetchone()
            is not None
        ):
            raise ToolsmithError("integrity", "Index contains orphan vector chunks")
        if (
            execute(
                connection,
                "SELECT 1 FROM embedding_vector v LEFT JOIN embedding_chunk c ON c.id = v.rowid WHERE c.id IS NULL LIMIT 1",
            ).fetchone()
            is not None
        ):
            raise ToolsmithError("integrity", "Native vector index contains orphan vectors")
        for document in execute(
            connection, "SELECT reference FROM embedding_document ORDER BY reference"
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
