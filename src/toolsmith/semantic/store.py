import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.retrieval import Citation, read_citation
from toolsmith.semantic import (
    PROFILE_ID,
    Encoder,
    Scope,
    Source,
    clear_index,
    encode_query,
    inspect_coverage,
    inspect_index,
    load_model,
    pending_references,
    prepare_embedding,
    publish_embedding,
    search_embeddings,
)
from toolsmith.storage.database import Store, open_store, row_integer, row_text
from toolsmith.validation import canonical_json, integer


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


def current_scope(store: Store) -> Scope:
    name = "semantic_current_" + uuid4().hex
    store.connection.execute(
        'CREATE TEMP VIEW "' + name + '" AS SELECT * FROM main.current_text WHERE has_text = 1'
    )
    return Scope(name, schema="temp")


def current_status(store: Store) -> TextIndexStatus:
    observed = unwrap(inspect_coverage(store.connection, current_scope(store)))
    return TextIndexStatus(
        observed.entries, observed.indexed, observed.missing + observed.stale, PROFILE_ID
    )


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
        references = unwrap(pending_references(store.connection, current_scope(store), maximum))
        selected = store.connection.execute(
            "SELECT p.part_id AS id, p.text_digest FROM current_text p JOIN json_each(?) requested ON requested.value = p.reference ORDER BY p.part_id",
            (canonical_json(references).decode(),),
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
            previous = unwrap(inspect_index(store.connection, (reference,)))[0].digest
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
        generation = store.connection.execute(
            "SELECT generation FROM collection WHERE id = 1"
        ).fetchone()[0]
    with selected_encoder(model_directory, encoder) as actual:
        encoded = unwrap(encode_query(query, actual))
    with open_store(root, collection) as store:
        if (
            store.connection.execute("SELECT generation FROM collection WHERE id = 1").fetchone()[0]
            != generation
        ):
            raise ToolsmithError(
                "conflict", "Current text changed while encoding the query; retry explicitly"
            )
        condition = (
            "" if selected is None else " AND item_id = '" + selected.replace("'", "''") + "'"
        )
        store.connection.execute(
            "CREATE TEMP VIEW requested_text AS SELECT * FROM main.current_text WHERE has_text = 1"
            + condition
        )
        report = unwrap(
            search_embeddings(
                store.connection, encoded, Scope("requested_text", schema="temp"), maximum
            )
        )
        citations: list[SemanticCitation] = []
        for hit in report.hits:
            row = store.connection.execute(
                "SELECT version_id, ordinal FROM current_text WHERE reference = ? AND text_digest = ?",
                (hit.reference, hit.digest),
            ).fetchone()
            if row is None:
                raise ToolsmithError("conflict", "Current text changed during semantic search")
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
        return unwrap(clear_index(store.connection))
