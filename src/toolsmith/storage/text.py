import hashlib
import sqlite3
from pathlib import Path

from toolsmith import semantic
from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.lexical import Source, index_source
from toolsmith.readers.models import Document
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.storage.database import Store, open_store, row_integer, row_text
from toolsmith.storage.models import TextReference, validate_document
from toolsmith.storage.operations import begin_operation, complete_operation
from toolsmith.validation import (
    JsonValue,
    canonical_json,
    digest,
    fields,
    identity,
    integer,
    json_value,
)


def text_reference(store: Store, version: str, *, reused: bool = False) -> TextReference:
    row = store.connection.execute(
        "SELECT v.*, (SELECT count(*) FROM part WHERE version_id = v.id) AS parts FROM text_version v WHERE v.id = ?",
        (digest(version, "Text version"),),
    ).fetchone()
    if row is None:
        raise ToolsmithError("not_found", "Exact text version was not found")
    return TextReference(
        store.collection,
        row_text(row, "item_id"),
        row_text(row, "id"),
        row_text(row, "title"),
        row_integer(row, "parts"),
        row_integer(row, "content_bytes"),
        row_text(row, "recorded_at"),
        reused,
    )


def insert_document(store: Store, item: str, document: Document, clock: Clock) -> TextReference:
    selected = identity(item, "Item")
    checked = validate_document(document)
    version = hashlib.sha256(
        canonical_json({"item": selected, "document": json_value(checked)})
    ).hexdigest()
    if (
        store.connection.execute("SELECT 1 FROM text_version WHERE id = ?", (version,)).fetchone()
        is not None
    ):
        reconcile_current_embeddings(store, selected, version)
        store.connection.execute(
            "UPDATE item SET latest_version = ? WHERE id = ?", (version, selected)
        )
        return text_reference(store, version, reused=True)
    store.connection.execute(
        "INSERT INTO item (id, latest_version) VALUES (?, NULL) ON CONFLICT (id) DO NOTHING",
        (selected,),
    )
    store.connection.execute(
        "INSERT INTO text_version (id, item_id, title, method, source_url, published_at, observed_at, recorded_at, content_bytes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            version,
            selected,
            checked.title,
            checked.method,
            checked.source_url,
            checked.published_at,
            checked.observed_at,
            utc_now(clock),
            sum(len(part.text.encode()) for part in checked.parts),
        ),
    )
    for ordinal, part in enumerate(checked.parts, start=1):
        cursor = store.connection.execute(
            "INSERT INTO part (version_id, ordinal, label, physical_page, text, text_digest, has_text, warnings) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version,
                ordinal,
                part.label,
                part.physical_page,
                part.text,
                hashlib.sha256(part.text.encode()).hexdigest(),
                int(bool(part.text.strip())),
                canonical_json(json_value(part.warnings)).decode(),
            ),
        )
        if cursor.lastrowid is None:
            raise ToolsmithError("integrity", "Inserted text part has no identity")
        unwrap(
            index_source(
                store.connection,
                Source("part:" + str(cursor.lastrowid), part.text, checked.title),
                expected_digest=None,
            )
        )
    reconcile_current_embeddings(store, selected, version)
    store.connection.execute("UPDATE item SET latest_version = ? WHERE id = ?", (version, selected))
    return text_reference(store, version)


def reconcile_current_embeddings(store: Store, item: str, version: str) -> None:
    previous = store.connection.execute(
        "SELECT p.id, p.ordinal FROM part p JOIN item i ON i.latest_version = p.version_id "
        "WHERE i.id = ? AND i.latest_version != ?",
        (item, version),
    ).fetchall()
    references = tuple("part:" + str(row["id"]) for row in previous)
    states = {
        entry.reference: entry.digest
        for entry in unwrap(semantic.inspect_index(store.connection, references))
    }
    for old in previous:
        reference = "part:" + str(old["id"])
        previous_digest = states[reference]
        if previous_digest is None:
            continue
        current = store.connection.execute(
            "SELECT id, text_digest, text FROM part WHERE version_id = ? AND ordinal = ?",
            (version, old["ordinal"]),
        ).fetchone()
        if current is not None and current["text_digest"] == previous_digest:
            unwrap(
                semantic.relocate_embedding(
                    store.connection,
                    reference,
                    semantic.Source("part:" + str(current["id"]), current["text"]),
                    expected_digest=previous_digest,
                )
            )
        else:
            unwrap(semantic.invalidate_embedding(store.connection, reference))


@boundary
def put_text(
    root: Path,
    collection: str,
    item: str,
    document: Document,
    request_id: str,
    *,
    clock: Clock | None = None,
) -> TextReference:
    selected = identity(item, "Item")
    checked = validate_document(document)
    actual_clock = clock or SystemClock()
    request: JsonValue = {
        "item": selected,
        "document_sha256": hashlib.sha256(canonical_json(json_value(checked))).hexdigest(),
    }
    with open_store(root, collection, write=True) as store, store.connection:
        previous = begin_operation(store, request_id, "text", request, actual_clock)
        if previous is not None:
            result = fields(
                previous.result,
                {
                    "collection",
                    "item",
                    "version",
                    "title",
                    "parts",
                    "content_bytes",
                    "recorded_at",
                    "reused",
                },
            )
            return text_reference(
                store, digest(result["version"], "Recorded text version"), reused=True
            )
        reference = insert_document(store, selected, checked, actual_clock)
        complete_operation(store, request_id, json_value(reference), actual_clock)
        return reference


@boundary
def inspect_text(root: Path, collection: str, version: str) -> TextReference:
    with open_store(root, collection) as store:
        return text_reference(store, version)


@boundary
def list_text(
    root: Path,
    collection: str,
    maximum_records: int = 100,
    offset: int = 0,
    *,
    item: str | None = None,
) -> tuple[TextReference, ...]:
    maximum = integer(maximum_records, 1, 100, "Maximum records")
    start = integer(offset, 0, 2**63 - 1, "Offset")
    selected = None if item is None else identity(item, "Item")
    with open_store(root, collection) as store:
        rows: list[sqlite3.Row]
        if selected is None:
            rows = store.connection.execute(
                "SELECT latest_version AS id FROM item ORDER BY id LIMIT ? OFFSET ?",
                (maximum, start),
            ).fetchall()
        else:
            rows = store.connection.execute(
                "SELECT id FROM text_version WHERE item_id = ? ORDER BY recorded_at DESC, id LIMIT ? OFFSET ?",
                (selected, maximum, start),
            ).fetchall()
        return tuple(text_reference(store, row_text(row, "id")) for row in rows)
