import os
import sqlite3
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.files import (
    MAX_FILE_BYTES,
    FileDigest,
    PrivateDirectory,
    child_directory,
    new_directory,
    new_private,
    private_directory,
    private_file,
    read_private,
    stream_file,
    write_descriptor,
)
from toolsmith.operations.integrity import validate_database, validate_objects
from toolsmith.result import ToolsmithError, boundary
from toolsmith.storage.database import (
    APPLICATION_ID,
    DATABASE_NAME,
    SCHEMA_VERSION,
    Store,
    configure,
    database_failure,
    open_store,
    row_integer,
    row_text,
)
from toolsmith.validation import (
    JsonValue,
    canonical_json,
    digest,
    fields,
    identity,
    integer,
    parse_json,
)

MAX_BACKUP_BYTES = 20 * 1024**3
MAX_MANIFEST_BYTES = 128 * 1024**2


@dataclass(frozen=True)
class BackupReport:
    collection: str
    schema_version: int
    objects: int
    bytes: int
    verified: bool


def hash_private(directory: PrivateDirectory, name: str, maximum: int) -> FileDigest:
    with private_file(directory, name) as descriptor:
        return stream_file(descriptor, maximum)


def copy_private(
    source: PrivateDirectory,
    target: PrivateDirectory,
    name: str,
    maximum: int,
    expected: FileDigest,
) -> None:
    new_private(target, name, b"")
    with (
        private_file(source, name) as incoming,
        private_file(target, name, create=True) as outgoing,
    ):
        observed = stream_file(incoming, maximum, outgoing)
        if observed != expected:
            raise ToolsmithError("conflict", "Backup input changed during the verified copy")
        os.fsync(outgoing)
    os.fsync(target.descriptor)


def write_manifest(
    directory: PrivateDirectory,
    metadata: dict[str, JsonValue],
    objects: Iterator[tuple[str, int]],
) -> None:
    new_private(directory, "manifest.json", b"")
    with private_file(directory, "manifest.json", create=True) as descriptor:
        written = 0

        def emit(content: bytes) -> None:
            nonlocal written
            written += len(content)
            if written > MAX_MANIFEST_BYTES:
                raise ToolsmithError("limit", "Backup manifest exceeds its input byte budget")
            write_descriptor(descriptor, content)

        emit(canonical_json(metadata)[:-1] + b',"objects":[')
        for ordinal, (checksum, size) in enumerate(objects):
            if ordinal:
                emit(b",")
            emit(canonical_json({"sha256": checksum, "bytes": size}))
        emit(b"]}")
        os.fsync(descriptor)
    os.fsync(directory.descriptor)


@boundary
def backup_store(
    root: Path,
    collection: str,
    destination: Path,
    maximum_bytes: int = MAX_BACKUP_BYTES,
    *,
    clock: Clock | None = None,
) -> BackupReport:
    maximum = integer(maximum_bytes, 1, MAX_BACKUP_BYTES, "Maximum backup bytes")
    with open_store(root, collection) as store:
        declared = store.connection.execute("SELECT coalesce(sum(size),0) FROM blob").fetchone()[0]
        pages = store.connection.execute("PRAGMA page_count").fetchone()[0]
        page_size = store.connection.execute("PRAGMA page_size").fetchone()[0]
        if declared + pages * page_size > maximum:
            raise ToolsmithError("limit", "Backup exceeds its explicit aggregate byte budget")
        validate_database(store)
        validate_objects(store)
        with (
            new_directory(destination) as target,
            child_directory(target, "objects", create=True) as objects,
        ):
            new_private(target, DATABASE_NAME, b"")
            connection = sqlite3.connect(
                f"file:/proc/self/fd/{target.descriptor}/{DATABASE_NAME}?mode=rw", uri=True
            )
            try:
                store.connection.backup(connection)
            except sqlite3.Error as error:
                raise database_failure(error) from error
            finally:
                connection.close()
            with private_file(target, DATABASE_NAME) as descriptor:
                os.fsync(descriptor)
            database = hash_private(target, DATABASE_NAME, maximum)
            total = database.content_bytes
            count = 0
            for row in store.connection.execute("SELECT id, size FROM blob ORDER BY id"):
                checksum = digest(row_text(row, "id"), "Object identity")
                size = row_integer(row, "size", MAX_FILE_BYTES)
                total += size
                if total > maximum:
                    raise ToolsmithError(
                        "limit", "Backup exceeds its explicit aggregate byte budget"
                    )
                copy_private(
                    store.objects, objects, checksum, MAX_FILE_BYTES, FileDigest(checksum, size)
                )
                count += 1
            manifest: dict[str, JsonValue] = {
                "format": 1,
                "schema_version": SCHEMA_VERSION,
                "collection": store.collection,
                "created_at": utc_now(clock or SystemClock()),
                "database_sha256": database.sha256,
                "database_bytes": database.content_bytes,
            }
            write_manifest(
                target,
                manifest,
                (
                    (row_text(row, "id"), row_integer(row, "size", MAX_FILE_BYTES))
                    for row in store.connection.execute("SELECT id, size FROM blob ORDER BY id")
                ),
            )
            return BackupReport(store.collection, SCHEMA_VERSION, count, total, True)


@boundary
def restore_store(
    backup: Path, collection: str, destination: Path, maximum_bytes: int = MAX_BACKUP_BYTES
) -> BackupReport:
    maximum = integer(maximum_bytes, 1, MAX_BACKUP_BYTES, "Maximum backup bytes")
    selected = identity(collection, "Collection")
    with private_directory(backup) as source, child_directory(source, "objects") as objects:
        if set(os.listdir(source.descriptor)) != {DATABASE_NAME, "objects", "manifest.json"}:
            raise ToolsmithError("integrity", "Backup contains unknown or missing files")
        manifest = fields(
            parse_json(
                read_private(source, "manifest.json", MAX_MANIFEST_BYTES), MAX_MANIFEST_BYTES
            ),
            {
                "format",
                "schema_version",
                "collection",
                "created_at",
                "database_sha256",
                "database_bytes",
                "objects",
            },
        )
        if (
            integer(manifest["format"], 1, 1, "Backup format") != 1
            or integer(manifest["schema_version"], SCHEMA_VERSION, SCHEMA_VERSION, "Backup schema")
            != SCHEMA_VERSION
            or manifest["collection"] != selected
        ):
            raise ToolsmithError("denied", "Backup format, schema or collection does not match")
        database = FileDigest(
            digest(manifest["database_sha256"], "Database identity"),
            integer(manifest["database_bytes"], 1, maximum, "Database bytes"),
        )
        if hash_private(source, DATABASE_NAME, maximum) != database:
            raise ToolsmithError("integrity", "Backup database identity does not match")
        entries = manifest["objects"]
        if not isinstance(entries, list):
            raise ToolsmithError("integrity", "Backup object manifest is invalid")
        expected: dict[str, int] = {}
        total = database.content_bytes
        for entry in entries:
            record = fields(entry, {"sha256", "bytes"})
            checksum = digest(record["sha256"], "Object identity")
            if checksum in expected:
                raise ToolsmithError("integrity", "Backup contains duplicate objects")
            expected[checksum] = integer(record["bytes"], 0, MAX_FILE_BYTES, "Object bytes")
            total += expected[checksum]
        if total > maximum or set(os.listdir(objects.descriptor)) != set(expected):
            raise ToolsmithError("integrity", "Backup object set or byte limit does not match")
        for checksum, size in expected.items():
            if hash_private(objects, checksum, MAX_FILE_BYTES) != FileDigest(checksum, size):
                raise ToolsmithError("integrity", "Backup object identity does not match")
        try:
            connection = sqlite3.connect(
                f"file:/proc/self/fd/{source.descriptor}/{DATABASE_NAME}?mode=ro&immutable=1",
                uri=True,
                timeout=0,
            )
            try:
                configure(connection)
                if (
                    connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                    or connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
                ):
                    raise ToolsmithError(
                        "integrity", "Backup database is not the current Toolsmith schema"
                    )
                binding = connection.execute(
                    "SELECT identity FROM collection WHERE id = 1"
                ).fetchone()
                if binding is None or binding["identity"] != selected:
                    raise ToolsmithError(
                        "denied", "Backup database belongs to a different collection"
                    )
                recorded = {
                    row_text(row, "id"): row_integer(row, "size", MAX_FILE_BYTES)
                    for row in connection.execute("SELECT id, size FROM blob")
                }
                if recorded != expected:
                    raise ToolsmithError(
                        "integrity", "Backup manifest differs from the canonical blob records"
                    )
                validate_database(Store(source, objects, objects, connection, selected))
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise database_failure(error) from error
        if hash_private(source, DATABASE_NAME, maximum) != database:
            raise ToolsmithError("conflict", "Backup database changed during validation")
        with (
            new_directory(destination) as target,
            child_directory(target, "objects", create=True) as target_objects,
            child_directory(target, "tmp", create=True) as temporary,
        ):
            for checksum, size in expected.items():
                copy_private(
                    objects, target_objects, checksum, MAX_FILE_BYTES, FileDigest(checksum, size)
                )
            staged = ".stage-" + uuid4().hex + ".tmp"
            try:
                copy_private(source, temporary, DATABASE_NAME, maximum, database)
                os.rename(
                    DATABASE_NAME,
                    staged,
                    src_dir_fd=temporary.descriptor,
                    dst_dir_fd=temporary.descriptor,
                )
                os.rename(
                    staged,
                    DATABASE_NAME,
                    src_dir_fd=temporary.descriptor,
                    dst_dir_fd=target.descriptor,
                )
                os.fsync(target.descriptor)
                os.fsync(temporary.descriptor)
            finally:
                for name in (staged, DATABASE_NAME):
                    with suppress(FileNotFoundError):
                        os.unlink(name, dir_fd=temporary.descriptor)
        return BackupReport(selected, SCHEMA_VERSION, len(expected), total, True)
