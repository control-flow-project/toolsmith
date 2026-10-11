import hashlib
import sqlite3
from pathlib import Path

from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.result import ToolsmithError, boundary
from toolsmith.storage.database import Store, open_store, row_integer, row_text
from toolsmith.storage.index import index_part
from toolsmith.storage.models import Document, TextReference, validate_document
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
            "INSERT INTO part (version_id, ordinal, label, physical_page, text, warnings) VALUES (?, ?, ?, ?, ?, ?)",
            (
                version,
                ordinal,
                part.label,
                part.physical_page,
                part.text,
                canonical_json(json_value(part.warnings)).decode(),
            ),
        )
        if cursor.lastrowid is None:
            raise ToolsmithError("integrity", "Inserted text part has no identity")
        index_part(store, cursor.lastrowid, checked.title, part.text)
    store.connection.execute("UPDATE item SET latest_version = ? WHERE id = ?", (version, selected))
    return text_reference(store, version)


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
    start = integer(offset, 0, 1_000_000, "Offset")
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
