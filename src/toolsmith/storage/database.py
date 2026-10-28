import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager, suppress
from dataclasses import dataclass
from functools import cache
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
from toolsmith.semantic.vector import load_vector_extension
from toolsmith.sqlite import connect_database
from toolsmith.validation import identity, integer, text

APPLICATION_ID = 1414745393
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
    if sqlite3.sqlite_version_info < (3, 44, 0):
        raise ToolsmithError(
            "unavailable", "SQLite 3.44 or newer is required for native FTS integrity verification"
        )
    load_vector_extension(connection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA trusted_schema = OFF")
    connection.execute("PRAGMA busy_timeout = 0")
    connection.execute("PRAGMA synchronous = FULL")


@cache
def schema_sql() -> str:
    return "\n".join(
        files("toolsmith." + owner).joinpath("schema.sql").read_text(encoding="utf-8")
        for owner in ("storage", "lexical", "semantic")
    )


def schema_records(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    return tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT GLOB 'sqlite_*' ORDER BY type, name"
        )
    )


@cache
def expected_schema() -> tuple[tuple[object, ...], ...]:
    with closing(sqlite3.connect(":memory:")) as connection:
        configure(connection)
        connection.executescript(schema_sql())
        return schema_records(connection)


def validate_schema(connection: sqlite3.Connection) -> None:
    if schema_records(connection) != expected_schema():
        raise ToolsmithError("integrity", "Database structure does not match the Toolsmith schema")


def info(store: Store) -> StoreInfo:
    counts = [
        store.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("item", "text_version", "file_version")
    ]
    return StoreInfo(store.collection, *counts)


@contextmanager
def open_store(root: Path, collection: str, *, write: bool = False) -> Iterator[Store]:
    selected = identity(collection, "Collection")
    with private_directory(root) as directory, directory_lock(directory, shared=not write):
        try:
            connection = connect_database(root / DATABASE_NAME, write=write)
            try:
                configure(connection)
                if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                    raise ToolsmithError("integrity", "Database is not a Toolsmith store")
                validate_schema(connection)
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
            with closing(connect_database(root / DATABASE_NAME)):
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
                        connection.executescript("BEGIN IMMEDIATE;\n" + schema_sql())
                        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                        connection.execute(
                            "INSERT INTO collection (id, identity, created_at) VALUES (1, :identity, :created_at)",
                            {"identity": selected, "created_at": utc_now(actual_clock)},
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
