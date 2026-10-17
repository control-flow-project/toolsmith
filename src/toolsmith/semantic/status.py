import sqlite3
from dataclasses import dataclass

from toolsmith.result import ToolsmithError, boundary
from toolsmith.scopes import Scope, coverage, scope_query
from toolsmith.semantic.index import validate_profile
from toolsmith.semantic.profile import MAX_CHUNKS, MAX_SOURCE_BYTES, PROFILE_ID
from toolsmith.sqlite import execute, transaction
from toolsmith.validation import canonical_json, digest, integer, source_reference, timestamp


@dataclass(frozen=True)
class IndexState:
    reference: str
    digest: str | None
    characters: int
    chunks: int
    indexed_at: str | None
    profile: str


@dataclass(frozen=True)
class IndexCoverage:
    entries: int
    indexed: int
    missing: int
    stale: int


@boundary
def inspect_coverage(connection: sqlite3.Connection, scope: Scope) -> IndexCoverage:
    with transaction(connection, "toolsmith_scope_metadata"):
        validate_profile(connection)
        selected = scope_query(connection, scope)
        entries, indexed, missing, stale, _largest = coverage(
            connection, selected, "embedding_document"
        )
        return IndexCoverage(entries, indexed, missing, stale)


@boundary
def pending_references(
    connection: sqlite3.Connection, scope: Scope, maximum_records: int = 100
) -> tuple[str, ...]:
    maximum = integer(maximum_records, 1, 1000, "Maximum pending references")
    with transaction(connection, "toolsmith_pending_metadata"):
        validate_profile(connection)
        selected = scope_query(connection, scope)
        coverage(connection, selected, "embedding_document")
        rows = execute(
            connection,
            "SELECT s.reference FROM ("
            + selected
            + ") s LEFT JOIN embedding_document d ON d.reference = s.reference WHERE d.reference IS NULL OR d.text_digest != s.text_digest ORDER BY s.reference LIMIT ?",
            (maximum,),
        )
        return tuple(source_reference(row[0]) for row in rows)


@boundary
def inspect_index(
    connection: sqlite3.Connection, references: tuple[str, ...]
) -> tuple[IndexState, ...]:
    if not isinstance(references, tuple):
        raise ToolsmithError("invalid_input", "Supply explicit metadata references")
    selected = tuple(source_reference(reference) for reference in references)
    if len(set(selected)) != len(selected):
        raise ToolsmithError("invalid_input", "Metadata references must be unique")
    with transaction(connection, "toolsmith_embedding_metadata"):
        validate_profile(connection)
        rows = execute(
            connection,
            "SELECT d.reference, d.text_digest, d.characters, d.chunks, d.indexed_at, d.profile_id "
            "FROM embedding_document d JOIN json_each(?) r ON d.reference = r.value",
            (canonical_json(selected).decode(),),
        )
        found: dict[str, IndexState] = {}
        for row in rows:
            observed = timestamp(row[4])
            if row[5] != PROFILE_ID or observed is None:
                raise ToolsmithError(
                    "integrity", "Semantic metadata contains invalid profile or time"
                )
            reference = source_reference(row[0])
            found[reference] = IndexState(
                reference,
                digest(row[1]),
                integer(row[2], 1, MAX_SOURCE_BYTES, "Characters"),
                integer(row[3], 1, MAX_CHUNKS, "Chunks"),
                observed,
                PROFILE_ID,
            )
        return tuple(
            found.get(reference, IndexState(reference, None, 0, 0, None, PROFILE_ID))
            for reference in selected
        )
