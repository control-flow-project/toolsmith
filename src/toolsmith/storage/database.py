import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.files import (
    PrivateDirectory,
    child_directory,
    directory_lock,
    new_private,
    private_directory,
    private_file,
)
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import identity, integer, text

APPLICATION_ID = 1414745393
SCHEMA_VERSION = 2
MAX_DATABASE_BYTES = 128 * 1024 * 1024
DATABASE_NAME = "toolsmith.sqlite3"


@dataclass(frozen=True)
class Store:
    directory: PrivateDirectory
    objects: PrivateDirectory
    temporary: PrivateDirectory
    connection: sqlite3.Connection
    collection: str


@dataclass(frozen=True)
class StoreInfo:
    collection: str
    schema_version: int
    items: int
    text_versions: int
    files: int


def row_text(row: sqlite3.Row, key: str, maximum: int = 1024) -> str:
    value: object = row[key]
    return text(value, maximum, "Stored " + key, allow_empty=True)


def row_optional_text(row: sqlite3.Row, key: str, maximum: int = 8192) -> str | None:
    value: object = row[key]
    return None if value is None else text(value, maximum, "Stored " + key, allow_empty=True)


def row_integer(row: sqlite3.Row, key: str, maximum: int = 2**63 - 1) -> int:
    value: object = row[key]
    return integer(value, 0, maximum, "Stored " + key)


def database_failure(error: sqlite3.Error) -> ToolsmithError:
    if isinstance(error, sqlite3.OperationalError) and getattr(
        error, "sqlite_errorcode", 0
    ) & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
        return ToolsmithError("deferred", "The selected database is busy", 0.1)
    return ToolsmithError("integrity", "The selected database failed its schema or data contract")


def configure(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA trusted_schema = OFF")
    connection.execute("PRAGMA busy_timeout = 0")
    connection.execute("PRAGMA synchronous = FULL")
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    connection.execute(f"PRAGMA max_page_count = {MAX_DATABASE_BYTES // page_size}")


def info(store: Store) -> StoreInfo:
    counts = [
        store.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("item", "text_version", "file_version")
    ]
    return StoreInfo(store.collection, SCHEMA_VERSION, *counts)


@contextmanager
def open_store(root: Path, collection: str, *, write: bool = False) -> Iterator[Store]:
    selected = identity(collection, "Collection")
    with private_directory(root) as directory, directory_lock(directory, shared=not write):
        with private_file(directory, DATABASE_NAME) as descriptor:
            if os.fstat(descriptor).st_size > MAX_DATABASE_BYTES:
                raise ToolsmithError("limit", "Store database exceeds its byte limit")
        uri = f"file:/proc/self/fd/{directory.descriptor}/{DATABASE_NAME}?mode={'rw' if write else 'ro'}"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=0)
            try:
                configure(connection)
                if (
                    connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                    or connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
                ):
                    raise ToolsmithError(
                        "integrity",
                        "Not a current Toolsmith store; no fallback or automatic migration",
                    )
                binding = connection.execute(
                    "SELECT identity FROM collection WHERE id = 1"
                ).fetchone()
                if binding is None or binding["identity"] != selected:
                    raise ToolsmithError(
                        "denied", "Selected store belongs to a different collection"
                    )
                with (
                    child_directory(directory, "objects") as objects,
                    child_directory(directory, "tmp") as temporary,
                ):
                    yield Store(directory, objects, temporary, connection, selected)
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise database_failure(error) from error


@boundary
def initialize_store(root: Path, collection: str, *, clock: Clock | None = None) -> StoreInfo:
    selected = identity(collection, "Collection")
    actual_clock = clock or SystemClock()
    with private_directory(root, create=True) as directory, directory_lock(directory):
        names = set(os.listdir(directory.descriptor))
        if DATABASE_NAME in names:
            with private_file(directory, DATABASE_NAME):
                pass
        else:
            if names - {".lock", "objects", "tmp"}:
                raise ToolsmithError(
                    "conflict", "Initialization requires an empty private directory"
                )
            with (
                child_directory(directory, "objects", create=True) as objects,
                child_directory(directory, "tmp", create=True) as temporary,
            ):
                if os.listdir(objects.descriptor):
                    raise ToolsmithError(
                        "conflict", "Initialization requires an empty object directory"
                    )
                staged = ".stage-" + uuid4().hex + ".tmp"
                new_private(temporary, staged, b"")
                try:
                    connection = sqlite3.connect(
                        f"file:/proc/self/fd/{temporary.descriptor}/{staged}?mode=rw", uri=True
                    )
                    try:
                        configure(connection)
                        connection.executescript(
                            "BEGIN IMMEDIATE;\n"
                            + files("toolsmith.storage")
                            .joinpath("schema.sql")
                            .read_text(encoding="utf-8")
                            + "\n"
                            + files("toolsmith.lexical")
                            .joinpath("schema.sql")
                            .read_text(encoding="utf-8")
                            + "\n"
                            + files("toolsmith.semantic")
                            .joinpath("schema.sql")
                            .read_text(encoding="utf-8")
                        )
                        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                        connection.execute(
                            "INSERT INTO collection (id, identity, created_at) VALUES (1, ?, ?)",
                            (selected, utc_now(actual_clock)),
                        )
                        connection.commit()
                    except sqlite3.Error as error:
                        raise database_failure(error) from error
                    finally:
                        connection.close()
                    with private_file(temporary, staged) as descriptor:
                        os.fsync(descriptor)
                    os.rename(
                        staged,
                        DATABASE_NAME,
                        src_dir_fd=temporary.descriptor,
                        dst_dir_fd=directory.descriptor,
                    )
                    os.fsync(directory.descriptor)
                    os.fsync(temporary.descriptor)
                finally:
                    with suppress(FileNotFoundError):
                        os.unlink(staged, dir_fd=temporary.descriptor)
    with open_store(root, selected) as store:
        return info(store)


@boundary
def inspect_store(root: Path, collection: str) -> StoreInfo:
    with open_store(root, collection) as store:
        return info(store)
