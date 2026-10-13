import hashlib
import os
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.files import (
    MAX_FILE_BYTES,
    child_directory,
    new_directory,
    new_private,
    private_directory,
    private_file,
    read_private,
)
from toolsmith.operations.integrity import validate_database, validate_objects
from toolsmith.result import ToolsmithError, boundary
from toolsmith.storage.database import (
    APPLICATION_ID,
    DATABASE_NAME,
    MAX_DATABASE_BYTES,
    SCHEMA_VERSION,
    Store,
    configure,
    database_failure,
    open_store,
    row_integer,
    row_text,
)
from toolsmith.validation import canonical_json, digest, fields, identity, integer, parse_json

MAX_BACKUP_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class BackupReport:
    collection: str
    schema_version: int
    objects: int
    bytes: int
    verified: bool


@boundary
def backup_store(
    root: Path,
    collection: str,
    destination: Path,
    maximum_bytes: int = 256 * 1024 * 1024,
    *,
    clock: Clock | None = None,
) -> BackupReport:
    maximum = integer(maximum_bytes, 1, MAX_BACKUP_BYTES, "Maximum backup bytes")
    with open_store(root, collection) as store:
        validate_database(store)
        validate_objects(store)
        rows = store.connection.execute("SELECT id, size FROM blob ORDER BY id").fetchall()
        total = os.stat(
            DATABASE_NAME, dir_fd=store.directory.descriptor, follow_symlinks=False
        ).st_size + sum(row_integer(row, "size", MAX_FILE_BYTES) for row in rows)
        if total > maximum or len(rows) > 10_000:
            raise ToolsmithError("limit", "Backup exceeds its explicit byte or object limit")
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
            database = read_private(target, DATABASE_NAME, MAX_DATABASE_BYTES)
            records = []
            for row in rows:
                checksum = digest(row_text(row, "id"), "Object identity")
                content = read_private(store.objects, checksum, MAX_FILE_BYTES)
                new_private(objects, checksum, content)
                records.append({"sha256": checksum, "bytes": len(content)})
            manifest = {
                "format": 1,
                "schema_version": SCHEMA_VERSION,
                "collection": store.collection,
                "created_at": utc_now(clock or SystemClock()),
                "database_sha256": hashlib.sha256(database).hexdigest(),
                "database_bytes": len(database),
                "objects": records,
            }
            new_private(target, "manifest.json", canonical_json(manifest))
            os.fsync(target.descriptor)
            return BackupReport(store.collection, SCHEMA_VERSION, len(rows), total, True)


@boundary
def restore_store(
    backup: Path, collection: str, destination: Path, maximum_bytes: int = 256 * 1024 * 1024
) -> BackupReport:
    maximum = integer(maximum_bytes, 1, MAX_BACKUP_BYTES, "Maximum backup bytes")
    selected = identity(collection, "Collection")
    with private_directory(backup) as source, child_directory(source, "objects") as objects:
        if set(os.listdir(source.descriptor)) != {DATABASE_NAME, "objects", "manifest.json"}:
            raise ToolsmithError("integrity", "Backup contains unknown or missing files")
        manifest = fields(
            parse_json(read_private(source, "manifest.json", 1024 * 1024)),
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
            or integer(manifest["schema_version"], 1, SCHEMA_VERSION, "Backup schema")
            != SCHEMA_VERSION
            or manifest["collection"] != selected
        ):
            raise ToolsmithError("denied", "Backup format, schema or collection does not match")
        database = read_private(source, DATABASE_NAME, MAX_DATABASE_BYTES)
        if len(database) != integer(
            manifest["database_bytes"], 1, MAX_DATABASE_BYTES, "Database bytes"
        ) or hashlib.sha256(database).hexdigest() != digest(
            manifest["database_sha256"], "Database identity"
        ):
            raise ToolsmithError("integrity", "Backup database identity does not match")
        entries = manifest["objects"]
        if not isinstance(entries, list) or len(entries) > 10_000:
            raise ToolsmithError("integrity", "Backup object manifest is invalid")
        expected: dict[str, int] = {}
        total = len(database)
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
            content = read_private(objects, checksum, MAX_FILE_BYTES)
            if len(content) != size or hashlib.sha256(content).hexdigest() != checksum:
                raise ToolsmithError("integrity", "Backup object identity does not match")
        try:
            connection = sqlite3.connect(":memory:", timeout=0)
            try:
                connection.deserialize(database)
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
        with (
            new_directory(destination) as target,
            child_directory(target, "objects", create=True) as target_objects,
            child_directory(target, "tmp", create=True) as temporary,
        ):
            for checksum in expected:
                content = read_private(objects, checksum, MAX_FILE_BYTES)
                if hashlib.sha256(content).hexdigest() != checksum:
                    raise ToolsmithError("conflict", "Backup changed during restore")
                new_private(target_objects, checksum, content)
            staged = ".stage-" + uuid4().hex + ".tmp"
            try:
                new_private(temporary, staged, database)
                os.rename(
                    staged,
                    DATABASE_NAME,
                    src_dir_fd=temporary.descriptor,
                    dst_dir_fd=target.descriptor,
                )
                os.fsync(target.descriptor)
                os.fsync(temporary.descriptor)
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(staged, dir_fd=temporary.descriptor)
        return BackupReport(selected, SCHEMA_VERSION, len(expected), total, True)
