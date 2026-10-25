import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from toolsmith.result import ToolsmithError
from toolsmith.sqlite import connect_database, open_database
from toolsmith.storage.database import open_store


def competing_writer(path: Path) -> str:
    script = (
        "import sqlite3,sys\n"
        "c=sqlite3.connect(sys.argv[1],timeout=0)\n"
        "try:\n c.execute('BEGIN IMMEDIATE');print('acquired');c.rollback()\n"
        "except sqlite3.OperationalError as e:\n print(e.sqlite_errorname)\n"
        "finally:\n c.close()\n"
    )
    return subprocess.run(
        [sys.executable, "-c", script, str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    ).stdout.strip()


@pytest.mark.parametrize("entrypoint", ["connection", "index", "archive"])
def test_secondary_connection_preserves_existing_sqlite_process_locks(
    store: Path, entrypoint: str
) -> None:
    path = store / "toolsmith.sqlite3"
    with closing(sqlite3.connect(path)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        assert competing_writer(path) == "SQLITE_BUSY"
        if entrypoint == "archive":
            with open_store(store, "sample"):
                pass
        elif entrypoint == "index":
            with open_database(path):
                pass
        else:
            with closing(connect_database(path)):
                pass
        assert competing_writer(path) == "SQLITE_BUSY"
        writer.rollback()
    assert competing_writer(path) == "acquired"


def test_database_filename_is_encoded_as_one_literal_uri_leaf(tmp_path: Path) -> None:
    path = tmp_path / "report?#.sqlite3"
    with closing(connect_database(path, create=True, write=True)) as connection:
        connection.execute("CREATE TABLE value(id INTEGER)")
        connection.commit()
    assert path.is_file() and not (tmp_path / "report").exists()
    with closing(connect_database(path)) as connection:
        assert connection.execute("SELECT count(*) FROM value").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO value VALUES (1)")


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "permissions", "fifo"])
def test_metadata_descriptor_keeps_private_regular_unaliased_file_checks(
    tmp_path: Path, unsafe: str
) -> None:
    path = tmp_path / "database.sqlite3"
    with closing(connect_database(path, create=True, write=True)):
        pass
    alias = tmp_path / "alias"
    if unsafe == "symlink":
        path.rename(alias)
        path.symlink_to(alias)
    elif unsafe == "hardlink":
        os.link(path, alias)
    elif unsafe == "permissions":
        path.chmod(0o644)
    else:
        path.unlink()
        os.mkfifo(path, 0o600)
    with pytest.raises(ToolsmithError) as rejected:
        connect_database(path)
    assert rejected.value.failure.code == "denied"
