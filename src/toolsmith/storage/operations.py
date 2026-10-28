import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from toolsmith.clock import Clock, utc_now
from toolsmith.result import ToolsmithError, boundary
from toolsmith.storage.database import Store, open_store, row_integer, row_optional_text, row_text
from toolsmith.validation import JsonValue, canonical_json, identity, parse_json

OperationKind = Literal["text", "file", "http"]


@dataclass(frozen=True)
class OperationStatus:
    identity: str
    kind: str
    status: str
    started_at: str
    updated_at: str
    requests: int
    result: JsonValue
    failure: JsonValue


def status_in_store(store: Store, request_id: str) -> OperationStatus:
    row = store.connection.execute(
        "SELECT * FROM operation WHERE id = :id", {"id": identity(request_id, "Request identity")}
    ).fetchone()
    if row is None:
        raise ToolsmithError(
            "not_found", "Operation identity was not found in the selected collection"
        )
    result = row_optional_text(row, "result_json", 65_536)
    failure = row_optional_text(row, "failure_json", 4096)
    return OperationStatus(
        row_text(row, "id"),
        row_text(row, "kind"),
        row_text(row, "status"),
        row_text(row, "started_at"),
        row_text(row, "updated_at"),
        row_integer(row, "requests"),
        None if result is None else parse_json(result.encode()),
        None if failure is None else parse_json(failure.encode()),
    )


def begin_operation(
    store: Store,
    request_id: str,
    kind: OperationKind,
    request: JsonValue,
    clock: Clock,
    *,
    resume: bool = False,
) -> OperationStatus | None:
    selected = identity(request_id, "Request identity")
    encoded = canonical_json(request)
    checksum = hashlib.sha256(encoded).hexdigest()
    existing = store.connection.execute(
        "SELECT kind, request_hash FROM operation WHERE id = :id", {"id": selected}
    ).fetchone()
    if existing is not None:
        if existing["kind"] != kind or existing["request_hash"] != checksum:
            raise ToolsmithError("conflict", "Request identity is already bound to different input")
        status = status_in_store(store, selected)
        if status.status == "succeeded":
            return status
        if not resume:
            raise ToolsmithError(
                "conflict", "Interrupted or failed HTTP work requires an explicit resume"
            )
        store.connection.execute(
            "UPDATE operation SET status = 'running', failure_json = NULL, updated_at = :updated_at WHERE id = :id",
            {"updated_at": utc_now(clock), "id": selected},
        )
    else:
        if resume:
            raise ToolsmithError("not_found", "There is no recorded operation to resume")
        now = utc_now(clock)
        store.connection.execute(
            "INSERT INTO operation (id, kind, status, request_hash, request_json, started_at, updated_at) VALUES (:id, :kind, 'running', :request_hash, :request_json, :started_at, :updated_at)",
            {
                "id": selected,
                "kind": kind,
                "request_hash": checksum,
                "request_json": encoded.decode(),
                "started_at": now,
                "updated_at": now,
            },
        )
    return None


def complete_operation(store: Store, request_id: str, result: JsonValue, clock: Clock) -> None:
    encoded = canonical_json(result)
    if len(encoded) > 65_536:
        raise ToolsmithError("limit", "Operation result exceeds its byte limit")
    store.connection.execute(
        "UPDATE operation SET status = 'succeeded', result_json = :result_json, failure_json = NULL, updated_at = :updated_at WHERE id = :id",
        {"result_json": encoded.decode(), "updated_at": utc_now(clock), "id": request_id},
    )


@boundary
def operation_status(root: Path, collection: str, request_id: str) -> OperationStatus:
    with open_store(root, collection) as store:
        return status_in_store(store, request_id)
