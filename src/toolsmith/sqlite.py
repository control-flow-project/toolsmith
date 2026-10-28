import os
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from toolsmith.files import check_private, component, new_private, private_directory
from toolsmith.result import ToolsmithError
from toolsmith.validation import number, text


def connect_database(
    path: Path, *, create: bool = False, write: bool = False, timeout_seconds: float = 0
) -> sqlite3.Connection:
    """Validate metadata without closing an ordinary descriptor on an open database."""
    if type(create) is not bool or type(write) is not bool:
        raise ToolsmithError("invalid_input", "Database creation/write intent must be Boolean")
    timeout = number(timeout_seconds, 0, 60, "Database lock timeout")
    if not hasattr(os, "O_PATH"):
        raise ToolsmithError(
            "unavailable", "Safe database metadata inspection requires Linux O_PATH"
        )
    name = component(path.name)
    with private_directory(path.parent) as directory:
        flags = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(name, flags, dir_fd=directory.descriptor)
        except FileNotFoundError:
            if not create:
                raise
            new_private(directory, name, b"")
            descriptor = os.open(name, flags, dir_fd=directory.descriptor)
        try:
            expected = check_private(descriptor)
            uri = f"file:/proc/self/fd/{directory.descriptor}/{quote(name, safe='')}" + (
                "?mode=rw" if write or create else "?mode=ro"
            )
            connection = sqlite3.connect(uri, uri=True, timeout=timeout)
            try:
                observed = os.stat(name, dir_fd=directory.descriptor, follow_symlinks=False)
                if (expected.st_dev, expected.st_ino) != (observed.st_dev, observed.st_ino):
                    raise ToolsmithError("denied", "Database identity changed during opening")
            except BaseException:
                connection.close()
                raise
            return connection
        finally:
            # O_PATH does not remove this process's POSIX record locks. Ordinary
            # open/close here would silently unlock existing SQLite connections.
            os.close(descriptor)


def execute(
    connection: sqlite3.Connection, statement: str, parameters: Mapping[str, object] | None = None
) -> sqlite3.Cursor:
    if parameters is not None and not isinstance(parameters, Mapping):
        raise ToolsmithError("invalid_input", "SQL parameters must be a named mapping")
    cursor = connection.cursor()
    cursor.row_factory = None
    return (
        cursor.execute(statement)
        if parameters is None
        else cursor.execute(statement, dict(parameters))
    )


@contextmanager
def transaction(
    connection: sqlite3.Connection, name: str, *, write: bool = False
) -> Iterator[None]:
    if not isinstance(connection, sqlite3.Connection):
        raise ToolsmithError("invalid_input", "Supply an explicit caller-owned SQLite connection")
    selected = text(name, 120, "Transaction name").replace('"', '""')
    try:
        if write and execute(connection, "PRAGMA foreign_keys").fetchone()[0] != 1:
            raise ToolsmithError("denied", "Caller must enable foreign keys before index writes")
        owned = not connection.in_transaction
        connection.execute('SAVEPOINT "' + selected + '"')
        try:
            yield
            connection.execute('RELEASE "' + selected + '"')
        except BaseException:
            if owned:
                connection.rollback()
            elif connection.in_transaction:
                connection.execute('ROLLBACK TO "' + selected + '"')
                connection.execute('RELEASE "' + selected + '"')
            raise
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", 0) & 255
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise ToolsmithError("deferred", "Caller-owned database is busy", 0.1) from error
        raise ToolsmithError("integrity", "Index schema, query or transaction failed") from error


@contextmanager
def open_database(
    path: Path, *, create: bool = False, write: bool = False
) -> Iterator[sqlite3.Connection]:
    with private_directory(path.parent):
        try:
            connection = connect_database(path, create=create, write=write)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA busy_timeout = 0")
                connection.execute("PRAGMA synchronous = FULL")
                if not write and not create:
                    connection.execute("PRAGMA query_only = ON")
                yield connection
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ToolsmithError(
                "integrity", "The explicit index database operation failed"
            ) from error
