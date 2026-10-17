import sqlite3
import sys
from importlib.resources import files

from toolsmith.result import ToolsmithError
from toolsmith.sqlite import execute


def load_vector_extension(connection: sqlite3.Connection) -> None:
    if not isinstance(connection, sqlite3.Connection):
        raise ToolsmithError("invalid_input", "Supply a caller-owned SQLite connection")
    try:
        observed = execute(connection, "SELECT vec1_info()").fetchone()[0]
    except sqlite3.OperationalError as error:
        if "no such function: vec1_info" not in str(error):
            raise
        suffix = (
            ".dll" if sys.platform == "win32" else ".dylib" if sys.platform == "darwin" else ".so"
        )
        path = files("toolsmith.semantic").joinpath("_vec1" + suffix)
        if not path.is_file():
            raise ToolsmithError(
                "unavailable",
                "Install a built Toolsmith package with its pinned SQLite vector extension",
            ) from error
        try:
            enabled = connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
            connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, True)
            try:
                connection.load_extension(str(path))
            finally:
                connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, enabled)
        except (AttributeError, sqlite3.Error) as failure:
            raise ToolsmithError(
                "unavailable", "SQLite must support the packaged vec1 0.8 extension"
            ) from failure
        observed = execute(connection, "SELECT vec1_info()").fetchone()[0]
    if (
        not isinstance(observed, str)
        or not observed.startswith("version 0.8 (")
        or not observed.endswith(", single-threaded, toolsmith-native-1)")
    ):
        raise ToolsmithError(
            "unavailable",
            "The selected connection must use Toolsmith's pinned single-threaded vec1 0.8 build",
        )
