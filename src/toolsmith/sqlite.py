import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from toolsmith.files import private_directory, private_file
from toolsmith.result import ToolsmithError
from toolsmith.validation import text


def execute(
    connection: sqlite3.Connection, statement: str, parameters: tuple[object, ...] = ()
) -> sqlite3.Cursor:
    cursor = connection.cursor()
    cursor.row_factory = None
    return cursor.execute(statement, parameters)


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
    with private_directory(path.parent) as directory:
        with private_file(directory, path.name, create=create):
            pass
        uri = f"file:/proc/self/fd/{directory.descriptor}/{path.name}?mode={'rw' if write or create else 'ro'}"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=0)
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
