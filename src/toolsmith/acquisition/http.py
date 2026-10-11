import math
from dataclasses import dataclass, replace
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from toolsmith.acquisition.limits import policy_hash, reserve, settle
from toolsmith.acquisition.policy import SourcePolicy, validate_policy
from toolsmith.acquisition.transport import (
    NativeResolver,
    NativeTransport,
    Resolver,
    Response,
    Transport,
    one_header,
    remaining,
)
from toolsmith.acquisition.urls import canonical_url, public_address
from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.files import MAX_FILE_BYTES, absolute_path
from toolsmith.readers.html import read_html
from toolsmith.readers.text import read_text
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.storage.artifacts import file_reference, insert_file
from toolsmith.storage.database import Store, open_store
from toolsmith.storage.models import Document, FileReference, TextReference, file_name
from toolsmith.storage.operations import begin_operation, complete_operation, status_in_store
from toolsmith.storage.text import insert_document, text_reference
from toolsmith.validation import (
    JsonValue,
    canonical_json,
    digest,
    fields,
    identity,
    integer,
    json_value,
    text,
)


@dataclass(frozen=True)
class Acquisition:
    request_id: str
    final_url: str
    requests: int
    wire_bytes: int
    received_at: str
    artifact: FileReference | None
    document: TextReference | None
    warnings: tuple[str, ...]
    reused: bool


def retry_after(response: Response, clock: Clock) -> float | None:
    value = one_header(response.headers, "retry-after")
    if value is None:
        return 60 if response.status == 429 else 0
    if value.isascii() and value.isdecimal():
        delay = float(value)
    else:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return 60 if response.status == 429 else 0
            delay = max(0, date.timestamp() - clock.wall())
        except (ValueError, TypeError, OverflowError):
            return 60 if response.status == 429 else 0
    return delay if math.isfinite(delay) and delay <= 2**53 - clock.wall() else None


def prior_acquisition(store: Store, value: JsonValue) -> Acquisition:
    result = fields(
        value,
        {
            "request_id",
            "final_url",
            "requests",
            "wire_bytes",
            "received_at",
            "artifact",
            "document",
            "warnings",
            "reused",
        },
    )
    artifact = result["artifact"]
    document = result["document"]
    warnings = result["warnings"]
    if not isinstance(warnings, list) or not all(isinstance(warning, str) for warning in warnings):
        raise ToolsmithError("integrity", "Recorded acquisition warnings are invalid")
    file_result = (
        None
        if artifact is None
        else file_reference(
            store,
            digest(
                fields(
                    artifact,
                    {
                        "collection",
                        "version",
                        "name",
                        "media_type",
                        "content_sha256",
                        "content_bytes",
                        "source_url",
                        "recorded_at",
                        "reused",
                    },
                )["version"],
                "File version",
            ),
            reused=True,
        )
    )
    text_result = (
        None
        if document is None
        else text_reference(
            store,
            digest(
                fields(
                    document,
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
                )["version"],
                "Text version",
            ),
            reused=True,
        )
    )
    return Acquisition(
        identity(result["request_id"], "Request identity"),
        canonical_url(result["final_url"]),
        integer(result["requests"], 0, 100, "Recorded requests"),
        integer(result["wire_bytes"], 0, MAX_FILE_BYTES, "Recorded wire bytes"),
        text(result["received_at"], 100, "Received time"),
        file_result,
        text_result,
        tuple(text(warning, 1024, "Warning") for warning in warnings),
        True,
    )


def request_json(
    url: str, policy: SourcePolicy, network_state: Path, item: str | None, name: str | None
) -> JsonValue:
    import hashlib

    return {
        "url": url,
        "policy": json_value(policy),
        "policy_sha256": policy_hash(policy),
        "network_state_sha256": hashlib.sha256(str(network_state).encode()).hexdigest(),
        "item": item,
        "name": name,
    }


def acquire_in_store(
    store: Store,
    network_state: Path,
    url: str,
    policy: SourcePolicy,
    request_id: str,
    item: str | None,
    name: str | None,
    clock: Clock,
    resolver: Resolver,
    transport: Transport,
    resume: bool,
) -> Acquisition:
    with store.connection:
        previous = begin_operation(
            store,
            request_id,
            "http",
            request_json(url, policy, network_state, item, name),
            clock,
            resume=resume,
        )
        if previous is not None:
            return prior_acquisition(store, previous.result)
    deadline = clock.monotonic() + policy.deadline_seconds
    current = url
    redirects = 0
    warnings = (
        ("Explicit resume may repeat a GET whose previous receipt was not recorded.",)
        if resume
        else ()
    )
    try:
        while True:
            remaining(deadline, clock)
            if urlsplit(current).hostname not in policy.hosts:
                raise ToolsmithError(
                    "denied",
                    "Request or redirect host is not explicitly approved by this source policy",
                )
            status = status_in_store(store, request_id)
            if status.requests >= policy.maximum_requests:
                raise ToolsmithError(
                    "limit",
                    "Recorded operation request allowance is exhausted; resume cannot reset it",
                )
            addresses = resolver.resolve(urlsplit(current).hostname or "", deadline, clock)
            if not 1 <= len(addresses) <= 64:
                raise ToolsmithError("denied", "DNS must return a bounded nonempty address set")
            checked = tuple(public_address(address) for address in addresses)
            remaining(deadline, clock)
            reservation = reserve(network_state, policy, clock)
            with store.connection:
                store.connection.execute(
                    "UPDATE operation SET requests = requests + 1, updated_at = ? WHERE id = ?",
                    (utc_now(clock), request_id),
                )
            response = transport.get(
                current, checked, policy.maximum_response_bytes, deadline, clock
            )
            remaining(deadline, clock)
            if (
                not isinstance(response.content, bytes)
                or len(response.content) > policy.maximum_response_bytes
            ):
                raise ToolsmithError(
                    "limit", "Transport returned more than the approved expanded byte limit"
                )
            used = integer(response.wire_bytes, 0, policy.maximum_response_bytes, "Wire bytes")
            cooldown = retry_after(response, clock)
            settle(network_state, policy, clock, reservation, used, cooldown)
            if response.status in {429, 503} and (cooldown is None or cooldown > 0):
                raise ToolsmithError(
                    "deferred",
                    "Upstream requested a cooldown; no automatic retry occurred",
                    cooldown,
                )
            if response.status in {301, 302, 303, 307, 308}:
                location = one_header(response.headers, "location")
                if location is None or redirects >= policy.maximum_redirects:
                    raise ToolsmithError(
                        "http", "Redirect lacks a location or exceeds its explicit limit"
                    )
                current = canonical_url(urljoin(current, location))
                redirects += 1
                continue
            if response.status != 200:
                raise ToolsmithError(
                    "http", "Approved source returned HTTP status " + str(response.status)
                )
            content_type = (
                (one_header(response.headers, "content-type") or "application/octet-stream")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            observed = utc_now(clock)
            artifact: FileReference | None = None
            document: TextReference | None = None
            parsed: Document | None = None
            if item is not None:
                if content_type in {"text/html", "application/xhtml+xml"}:
                    parsed = unwrap(read_html(response.content))
                elif content_type == "text/plain":
                    parsed = unwrap(read_text(response.content, item))
                else:
                    raise ToolsmithError(
                        "unavailable",
                        "This response type has no selected text reader; no PDF, OCR or browser substitute is used",
                    )
                parsed = replace(parsed, source_url=current, observed_at=observed)
            with store.connection:
                if name is not None:
                    artifact = insert_file(
                        store, response.content, name, content_type, current, clock
                    )
                if parsed is not None and item is not None:
                    document = insert_document(store, item, parsed, clock)
                result = Acquisition(
                    request_id,
                    current,
                    status_in_store(store, request_id).requests,
                    used,
                    observed,
                    artifact,
                    document,
                    warnings,
                    False,
                )
                complete_operation(store, request_id, json_value(result), clock)
                return result
    except ToolsmithError as error:
        with store.connection:
            store.connection.execute(
                "UPDATE operation SET status = 'failed', failure_json = ?, updated_at = ? WHERE id = ?",
                (canonical_json(json_value(error.failure)).decode(), utc_now(clock), request_id),
            )
        raise


@boundary
def acquire_http(
    root: Path,
    collection: str,
    network_state: Path,
    url: str,
    policy: SourcePolicy,
    request_id: str,
    *,
    item: str | None = None,
    name: str | None = None,
    clock: Clock | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> Acquisition:
    selected = canonical_url(url)
    checked = validate_policy(policy)
    absolute_path(network_state)
    if item is None and name is None or checked.retention == "text_only" and name is not None:
        raise ToolsmithError(
            "denied", "Select text retention or policy-permitted original retention explicitly"
        )
    selected_item = None if item is None else identity(item, "Item")
    selected_name = None if name is None else file_name(name)
    selected_request = identity(request_id, "Request identity")
    with open_store(root, collection, write=True) as store:
        return acquire_in_store(
            store,
            network_state,
            selected,
            checked,
            selected_request,
            selected_item,
            selected_name,
            clock or SystemClock(),
            resolver or NativeResolver(),
            transport or NativeTransport(),
            False,
        )


@boundary
def resume_http(
    root: Path,
    collection: str,
    network_state: Path,
    policy: SourcePolicy,
    request_id: str,
    *,
    clock: Clock | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> Acquisition:
    checked = validate_policy(policy)
    absolute_path(network_state)
    selected_request = identity(request_id, "Request identity")
    with open_store(root, collection, write=True) as store:
        row = store.connection.execute(
            "SELECT kind, request_json FROM operation WHERE id = ?", (selected_request,)
        ).fetchone()
        if row is None or row["kind"] != "http":
            raise ToolsmithError(
                "not_found",
                "No HTTP operation with that identity exists in the selected collection",
            )
        from toolsmith.validation import parse_json

        request = fields(
            parse_json(str(row["request_json"]).encode()),
            {"url", "policy", "policy_sha256", "network_state_sha256", "item", "name"},
        )
        item = None if request["item"] is None else identity(request["item"], "Item")
        name = None if request["name"] is None else file_name(request["name"])
        return acquire_in_store(
            store,
            network_state,
            canonical_url(request["url"]),
            checked,
            selected_request,
            item,
            name,
            clock or SystemClock(),
            resolver or NativeResolver(),
            transport or NativeTransport(),
            True,
        )
