import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.retrieval import Citation, read_citation
from toolsmith.semantic import (
    PROFILE_ID,
    Candidate,
    Encoder,
    Source,
    encode_query,
    indexed_digest,
    load_model,
    prepare_embedding,
    publish_embedding,
    search_embeddings,
)
from toolsmith.storage.database import Store, open_store, row_integer, row_text
from toolsmith.validation import integer


@dataclass(frozen=True)
class TextIndexStatus:
    parts: int
    indexed: int
    pending: int
    profile: str


@dataclass(frozen=True)
class TextIndexReport:
    newly_indexed: int
    status: TextIndexStatus


@dataclass(frozen=True)
class SemanticCitation:
    score: float
    citation: Citation
    match_start: int
    match_end: int


@dataclass(frozen=True)
class TextSearchReport:
    hits: tuple[SemanticCitation, ...]
    parts: int
    indexed: int
    missing: int
    stale: int


@contextmanager
def selected_encoder(directory: Path, encoder: Encoder | None) -> Iterator[Encoder]:
    if encoder is not None:
        yield encoder
    else:
        with unwrap(load_model(directory)) as loaded:
            yield loaded


def current_status(store: Store) -> TextIndexStatus:
    parts, indexed = store.connection.execute(
        "SELECT COUNT(*), COALESCE(SUM(CASE WHEN d.profile_id = ? AND d.text_digest = p.text_digest THEN 1 ELSE 0 END), 0) FROM part p JOIN item i ON i.latest_version = p.version_id LEFT JOIN embedding_document d ON d.reference = 'part:' || p.id WHERE p.has_text = 1",
        (PROFILE_ID,),
    ).fetchone()
    return TextIndexStatus(parts, indexed, parts - indexed, PROFILE_ID)


@boundary
def inspect_text_index(root: Path, collection: str) -> TextIndexStatus:
    with open_store(root, collection) as store:
        return current_status(store)


@boundary
def index_text(
    root: Path,
    collection: str,
    model_directory: Path,
    maximum_parts: int = 10,
    *,
    encoder: Encoder | None = None,
    clock: Clock | None = None,
) -> TextIndexReport:
    maximum = integer(maximum_parts, 1, 100, "Maximum indexed parts")
    with open_store(root, collection) as store:
        selected = store.connection.execute(
            "SELECT p.id FROM part p JOIN item i ON i.latest_version = p.version_id LEFT JOIN embedding_document d ON d.reference = 'part:' || p.id WHERE p.has_text = 1 AND (d.reference IS NULL OR d.text_digest != p.text_digest OR d.profile_id != ?) ORDER BY p.id LIMIT ?",
            (PROFILE_ID, maximum),
        ).fetchall()
        if not selected:
            return TextIndexReport(0, current_status(store))
    with selected_encoder(model_directory, encoder) as actual:
        return index_parts(root, collection, selected, actual, clock)


def index_parts(
    root: Path, collection: str, selected: list[sqlite3.Row], actual: Encoder, clock: Clock | None
) -> TextIndexReport:
    completed = 0
    for entry in selected:
        part_id = row_integer(entry, "id")
        reference = "part:" + str(part_id)
        with open_store(root, collection) as store:
            row = store.connection.execute(
                "SELECT p.text FROM part p JOIN item i ON i.latest_version = p.version_id WHERE p.id = ?",
                (part_id,),
            ).fetchone()
            if row is None:
                raise ToolsmithError(
                    "conflict", "Current text changed before indexing; retry explicitly"
                )
            source = Source(reference, row_text(row, "text", 4 * 1024 * 1024))
            previous = unwrap(indexed_digest(store.connection, reference))
        prepared = unwrap(prepare_embedding(source, actual))
        with open_store(root, collection, write=True) as store, store.connection:
            row = store.connection.execute(
                "SELECT p.text_digest FROM part p JOIN item i ON i.latest_version = p.version_id WHERE p.id = ?",
                (part_id,),
            ).fetchone()
            if row is None or row["text_digest"] != prepared.digest:
                raise ToolsmithError(
                    "conflict", "Current text changed while encoding; vectors were not published"
                )
            completed += unwrap(
                publish_embedding(
                    store.connection,
                    prepared,
                    source,
                    utc_now(clock or SystemClock()),
                    expected_digest=previous,
                )
            )
    with open_store(root, collection) as store:
        return TextIndexReport(completed, current_status(store))


@boundary
def search_semantic_text(
    root: Path,
    collection: str,
    query: str,
    model_directory: Path,
    maximum_records: int = 20,
    *,
    encoder: Encoder | None = None,
    item: str | None = None,
) -> TextSearchReport:
    from toolsmith.validation import identity

    maximum = integer(maximum_records, 1, 100, "Maximum records")
    selected = None if item is None else identity(item, "Item")
    with open_store(root, collection) as store:
        rows = store.connection.execute(
            "SELECT p.id, p.version_id, p.ordinal, p.text_digest FROM part p JOIN item i ON i.latest_version = p.version_id WHERE p.has_text = 1 AND (? IS NULL OR i.id = ?) ORDER BY p.id LIMIT 10001",
            (selected, selected),
        ).fetchall()
        if len(rows) > 10_000:
            raise ToolsmithError(
                "limit", "Select an item to keep semantic candidates within 10000 parts"
            )
    with selected_encoder(model_directory, encoder) as actual:
        return search_parts(root, collection, query, selected, rows, actual, maximum)


def search_parts(
    root: Path,
    collection: str,
    query: str,
    selected: str | None,
    rows: list[sqlite3.Row],
    actual: Encoder,
    maximum: int,
) -> TextSearchReport:
    encoded = unwrap(encode_query(query, actual))
    with open_store(root, collection) as store:
        current_rows = store.connection.execute(
            "SELECT p.id, p.version_id, p.ordinal, p.text_digest FROM part p JOIN item i ON i.latest_version = p.version_id WHERE p.has_text = 1 AND (? IS NULL OR i.id = ?) ORDER BY p.id LIMIT 10001",
            (selected, selected),
        ).fetchall()
        if [tuple(row) for row in current_rows] != [tuple(row) for row in rows]:
            raise ToolsmithError(
                "conflict", "Current candidates changed while encoding the query; retry explicitly"
            )
        report = unwrap(
            search_embeddings(
                store.connection,
                encoded,
                tuple(
                    Candidate("part:" + str(row["id"]), row_text(row, "text_digest"))
                    for row in rows
                ),
                maximum,
            )
        )
        citations: list[SemanticCitation] = []
        by_reference = {"part:" + str(row["id"]): row for row in rows}
        for hit in report.hits:
            row = by_reference[hit.reference]
            current = store.connection.execute(
                "SELECT 1 FROM part p JOIN item i ON i.latest_version = p.version_id WHERE p.id = ? AND p.text_digest = ?",
                (row["id"], hit.digest),
            ).fetchone()
            if current is None:
                raise ToolsmithError(
                    "conflict", "Current text changed during semantic search; retry explicitly"
                )
            citation = unwrap(
                read_citation(
                    root,
                    collection,
                    row_text(row, "version_id"),
                    row_integer(row, "ordinal"),
                    hit.start,
                    min(hit.end - hit.start, 16_384),
                )
            )
            citations.append(SemanticCitation(hit.score, citation, hit.start, hit.end))
        return TextSearchReport(
            tuple(citations), report.candidates, report.indexed, report.missing, report.stale
        )


@boundary
def clear_text_index(root: Path, collection: str) -> int:
    with open_store(root, collection, write=True) as store, store.connection:
        count = store.connection.execute("SELECT COUNT(*) FROM embedding_document").fetchone()[0]
        store.connection.execute("DELETE FROM embedding_chunk")
        store.connection.execute("DELETE FROM embedding_document")
        store.connection.execute("DELETE FROM embedding_profile")
        return int(count)
