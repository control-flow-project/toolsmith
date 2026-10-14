import hashlib
import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files

from toolsmith.lexical.chunks import text_chunks
from toolsmith.lexical.query import QueryMode, compile_query
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.sqlite import execute, transaction
from toolsmith.validation import canonical_json, digest, integer, source_reference, text

SCHEMA_SQL = files("toolsmith.lexical").joinpath("schema.sql").read_text(encoding="utf-8")
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES = 100_000


@dataclass(frozen=True)
class Source:
    reference: str
    text: str
    title: str = ""


@dataclass(frozen=True)
class Candidate:
    reference: str
    digest: str


@dataclass(frozen=True)
class IndexState:
    reference: str
    digest: str | None
    characters: int
    chunks: int
    title: str = ""


@dataclass(frozen=True)
class Hit:
    reference: str
    digest: str
    start: int
    end: int
    text: str
    rank: float


@dataclass(frozen=True)
class SearchReport:
    hits: tuple[Hit, ...]
    candidates: int
    indexed: int
    missing: int
    stale: int


@boundary
def initialize_index(connection: sqlite3.Connection) -> bool:
    with transaction(connection, "toolsmith_lexical", write=True):
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip():
                execute(connection, statement)
    return True


def source_digest(source: Source) -> str:
    if not isinstance(source, Source):
        raise ToolsmithError("invalid_input", "Supply a typed lexical source")
    source_reference(source.reference)
    text(source.title, 1024, "Source title", allow_empty=True)
    return hashlib.sha256(
        text(source.text, MAX_SOURCE_BYTES, "Source", allow_empty=True).encode()
    ).hexdigest()


def state(connection: sqlite3.Connection, reference: str) -> IndexState:
    row = execute(
        connection,
        "SELECT text_digest, characters, chunks, title FROM lexical_document WHERE reference = ?",
        (source_reference(reference),),
    ).fetchone()
    if row is None:
        return IndexState(reference, None, 0, 0)
    return IndexState(
        reference,
        digest(row[0]),
        integer(row[1], 0, MAX_SOURCE_BYTES, "Characters"),
        integer(row[2], 0, 100000, "Chunks"),
        text(row[3], 1024, "Indexed title", allow_empty=True),
    )


@boundary
def inspect_index(
    connection: sqlite3.Connection, references: tuple[str, ...]
) -> tuple[IndexState, ...]:
    if not isinstance(references, tuple) or len(references) > MAX_CANDIDATES:
        raise ToolsmithError("limit", "Supply at most 100000 source references")
    checked = tuple(source_reference(reference) for reference in references)
    if len(set(checked)) != len(checked):
        raise ToolsmithError("invalid_input", "Source references must be unique")
    with transaction(connection, "toolsmith_lexical"):
        rows = execute(
            connection,
            "SELECT d.reference, d.text_digest, d.characters, d.chunks, d.title FROM lexical_document d "
            "JOIN json_each(?) r ON d.reference = r.value",
            (canonical_json(checked).decode(),),
        )
        found = {
            source_reference(row[0]): IndexState(
                source_reference(row[0]),
                digest(row[1]),
                integer(row[2], 0, MAX_SOURCE_BYTES, "Characters"),
                integer(row[3], 0, 100000, "Chunks"),
                text(row[4], 1024, "Indexed title", allow_empty=True),
            )
            for row in rows
        }
        return tuple(
            found.get(reference, IndexState(reference, None, 0, 0)) for reference in checked
        )


def remove_source(connection: sqlite3.Connection, reference: str) -> bool:
    execute(
        connection,
        "DELETE FROM lexical_search WHERE rowid IN (SELECT id FROM lexical_chunk WHERE reference = ?)",
        (reference,),
    )
    return (
        execute(
            connection, "DELETE FROM lexical_document WHERE reference = ?", (reference,)
        ).rowcount
        > 0
    )


@boundary
def index_source(
    connection: sqlite3.Connection, source: Source, *, expected_digest: str | None
) -> bool:
    checksum = source_digest(source)
    expected = None if expected_digest is None else digest(expected_digest)
    with transaction(connection, "toolsmith_lexical", write=True):
        previous = state(connection, source.reference)
        if previous.digest == checksum and previous.title == source.title:
            return False
        if previous.digest != expected:
            raise ToolsmithError("conflict", "Lexical source changed before index publication")
        chunks = tuple(text_chunks(source.text))
        remove_source(connection, source.reference)
        execute(
            connection,
            "INSERT INTO lexical_document (reference, text_digest, characters, chunks, title) VALUES (?, ?, ?, ?, ?)",
            (source.reference, checksum, len(source.text), len(chunks), source.title),
        )
        for ordinal, (start, end, body) in enumerate(chunks):
            cursor = execute(
                connection,
                "INSERT INTO lexical_chunk (reference, ordinal, start_offset, end_offset, text, text_digest) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    source.reference,
                    ordinal,
                    start,
                    end,
                    body,
                    hashlib.sha256(body.encode()).hexdigest(),
                ),
            )
            execute(
                connection,
                "INSERT INTO lexical_search (rowid, text, title) VALUES (?, ?, ?)",
                (cursor.lastrowid, body, source.title),
            )
    return True


@boundary
def invalidate_source(connection: sqlite3.Connection, reference: str) -> bool:
    selected = source_reference(reference)
    with transaction(connection, "toolsmith_lexical", write=True):
        return remove_source(connection, selected)


@boundary
def search(
    connection: sqlite3.Connection,
    query: str,
    candidates: tuple[Candidate, ...],
    maximum_records: int = 20,
    *,
    mode: QueryMode = "literal",
    offset: int = 0,
) -> SearchReport:
    expression = unwrap(compile_query(query, mode))
    maximum = integer(maximum_records, 1, 1000, "Maximum records")
    beginning = integer(offset, 0, 1_000_000, "Offset")
    if not isinstance(candidates, tuple) or len(candidates) > MAX_CANDIDATES:
        raise ToolsmithError("limit", "Supply at most 100000 authorized lexical candidates")
    selected: dict[str, str] = {}
    for candidate in candidates:
        if not isinstance(candidate, Candidate):
            raise ToolsmithError("invalid_input", "Supply typed authorized candidates")
        reference = source_reference(candidate.reference)
        if reference in selected:
            raise ToolsmithError("invalid_input", "Candidate references must be unique")
        selected[reference] = digest(candidate.digest)
    missing, stale = 0, 0
    with transaction(connection, "toolsmith_lexical"):
        states = {
            record.reference: record
            for record in unwrap(inspect_index(connection, tuple(selected)))
        }
        current: dict[str, str] = {}
        for reference, checksum in selected.items():
            actual = states[reference].digest
            if actual is None:
                missing += 1
            elif actual != checksum:
                stale += 1
            else:
                current[reference] = checksum
        rows = execute(
            connection,
            "WITH candidate AS (SELECT key AS reference, value AS digest FROM json_each(?)) "
            "SELECT c.reference, d.text_digest, c.start_offset, c.end_offset, c.text, bm25(lexical_search), c.text_digest, lexical_search.text, lexical_search.title, d.title "
            "FROM lexical_search JOIN lexical_chunk c ON c.id = lexical_search.rowid "
            "JOIN lexical_document d ON d.reference = c.reference "
            "JOIN candidate a ON a.reference = d.reference AND a.digest = d.text_digest "
            "WHERE lexical_search MATCH ? ORDER BY bm25(lexical_search), c.reference, c.ordinal LIMIT ? OFFSET ?",
            (canonical_json(current).decode(), expression, maximum, beginning),
        )
        hits: list[Hit] = []
        for row in rows:
            body = text(row[4], 8192, "Indexed chunk", allow_empty=True)
            start = integer(row[2], 0, MAX_SOURCE_BYTES, "Start")
            end = integer(row[3], start + 1, MAX_SOURCE_BYTES, "End")
            rank = float(row[5])
            if (
                len(body) != end - start
                or not math.isfinite(rank)
                or hashlib.sha256(body.encode()).hexdigest() != digest(row[6])
                or row[7] != body
                or row[8] != row[9]
            ):
                raise ToolsmithError("integrity", "Lexical hit has invalid source spans or rank")
            hits.append(Hit(source_reference(row[0]), digest(row[1]), start, end, body, rank))
    return SearchReport(tuple(hits), len(candidates), len(current), missing, stale)


@boundary
def check_index(connection: sqlite3.Connection, source_text: Callable[[str], str | None]) -> int:
    with transaction(connection, "toolsmith_lexical"):
        references = tuple(
            row[0]
            for row in execute(
                connection, "SELECT reference FROM lexical_document ORDER BY reference"
            )
        )
        for reference in references:
            body = source_text(reference)
            if (
                body is None
                or source_digest(Source(reference, body)) != state(connection, reference).digest
            ):
                raise ToolsmithError("integrity", "Lexical canonical source is missing or changed")
            actual = execute(
                connection,
                "SELECT c.ordinal, c.start_offset, c.end_offset, c.text, f.text, c.text_digest, f.title FROM lexical_chunk c "
                "LEFT JOIN lexical_search f ON f.rowid = c.id WHERE c.reference = ? ORDER BY c.ordinal",
                (reference,),
            ).fetchall()
            expected = tuple(text_chunks(body))
            metadata = state(connection, reference)
            if (
                metadata.characters != len(body)
                or metadata.chunks != len(expected)
                or len(actual) != len(expected)
                or any(
                    row[0] != ordinal
                    or tuple(row[1:4]) != chunk
                    or row[4] != chunk[2]
                    or row[5] != hashlib.sha256(chunk[2].encode()).hexdigest()
                    or row[6] != metadata.title
                    for ordinal, (row, chunk) in enumerate(zip(actual, expected, strict=True))
                )
            ):
                raise ToolsmithError(
                    "integrity", "Lexical chunks or postings differ from their source"
                )
        if (
            execute(
                connection,
                "SELECT 1 FROM lexical_search f LEFT JOIN lexical_chunk c ON c.id = f.rowid WHERE c.id IS NULL LIMIT 1",
            ).fetchone()
            is not None
        ):
            raise ToolsmithError("integrity", "Lexical postings contain an orphan")
        if (
            execute(
                connection,
                "SELECT 1 FROM lexical_chunk c LEFT JOIN lexical_document d ON d.reference = c.reference WHERE d.reference IS NULL LIMIT 1",
            ).fetchone()
            is not None
        ):
            raise ToolsmithError("integrity", "Lexical index contains an orphan chunk")
        return len(references)
