import hashlib
from pathlib import Path

from toolsmith.acquisition.urls import canonical_url
from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.files import MAX_FILE_BYTES, put_object, read_private, write_new_bytes
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.storage.database import Store, open_store, row_integer, row_optional_text, row_text
from toolsmith.storage.models import FileReference, file_name, media_type
from toolsmith.storage.operations import begin_operation, complete_operation
from toolsmith.validation import JsonValue, canonical_json, digest, fields, json_value


def file_reference(store: Store, version: str, *, reused: bool = False) -> FileReference:
    row = store.connection.execute(
        "SELECT f.*, b.size FROM file_version f JOIN blob b ON b.id = f.blob_id WHERE f.id = ?",
        (digest(version, "File version"),),
    ).fetchone()
    if row is None:
        raise ToolsmithError("not_found", "Exact file version was not found")
    return FileReference(
        store.collection,
        row_text(row, "id"),
        row_text(row, "name"),
        row_text(row, "media_type"),
        row_text(row, "blob_id"),
        row_integer(row, "size", MAX_FILE_BYTES),
        row_optional_text(row, "source_url"),
        row_text(row, "recorded_at"),
        reused,
    )


def insert_file(
    store: Store, content: bytes, name: str, content_type: str, source_url: str | None, clock: Clock
) -> FileReference:
    if not isinstance(content, bytes) or len(content) > MAX_FILE_BYTES:
        raise ToolsmithError("limit", "File input must be bounded bytes")
    filename = file_name(name)
    mime = media_type(content_type)
    source = None if source_url is None else canonical_url(source_url)
    checksum = hashlib.sha256(content).hexdigest()
    version = hashlib.sha256(
        canonical_json(
            {"content": checksum, "name": filename, "media_type": mime, "source_url": source}
        )
    ).hexdigest()
    if (
        store.connection.execute("SELECT 1 FROM file_version WHERE id = ?", (version,)).fetchone()
        is not None
    ):
        existing = file_reference(store, version, reused=True)
        if read_private(store.objects, existing.content_sha256, MAX_FILE_BYTES) != content:
            raise ToolsmithError("integrity", "Immutable file content changed")
        return existing
    put_object(store.objects, store.temporary, content)
    store.connection.execute(
        "INSERT INTO blob (id, size) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
        (checksum, len(content)),
    )
    store.connection.execute(
        "INSERT INTO file_version (id, name, media_type, blob_id, source_url, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (version, filename, mime, checksum, source, utc_now(clock)),
    )
    return file_reference(store, version)


@boundary
def put_file(
    root: Path,
    collection: str,
    content: bytes,
    name: str,
    content_type: str,
    request_id: str,
    *,
    source_url: str | None = None,
    clock: Clock | None = None,
) -> FileReference:
    if not isinstance(content, bytes) or len(content) > MAX_FILE_BYTES:
        raise ToolsmithError("limit", "File input must be bounded bytes")
    filename = file_name(name)
    mime = media_type(content_type)
    source = None if source_url is None else canonical_url(source_url)
    actual_clock = clock or SystemClock()
    request: JsonValue = {
        "content": hashlib.sha256(content).hexdigest(),
        "name": filename,
        "media_type": mime,
        "source_url": source,
    }
    with open_store(root, collection, write=True) as store, store.connection:
        previous = begin_operation(store, request_id, "file", request, actual_clock)
        if previous is not None:
            result = fields(
                previous.result,
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
            )
            return file_reference(
                store, digest(result["version"], "Recorded file version"), reused=True
            )
        reference = insert_file(store, content, filename, mime, source, actual_clock)
        complete_operation(store, request_id, json_value(reference), actual_clock)
        return reference


@boundary
def inspect_file(root: Path, collection: str, version: str) -> FileReference:
    with open_store(root, collection) as store:
        return file_reference(store, version)


@boundary
def read_file(root: Path, collection: str, version: str) -> bytes:
    with open_store(root, collection) as store:
        reference = file_reference(store, version)
        content = read_private(store.objects, reference.content_sha256, MAX_FILE_BYTES)
        if (
            len(content) != reference.content_bytes
            or hashlib.sha256(content).hexdigest() != reference.content_sha256
        ):
            raise ToolsmithError(
                "integrity", "Immutable object bytes do not match their recorded identity"
            )
        return content


@boundary
def export_file(
    root: Path, collection: str, version: str, destination: Path
) -> dict[str, int | bool]:
    content = unwrap(read_file(root, collection, version))
    return unwrap(write_new_bytes(destination, content))
