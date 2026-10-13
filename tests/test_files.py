import os
from pathlib import Path

from toolsmith.files import read_bytes, write_new_bytes
from toolsmith.result import Failure, unwrap
from toolsmith.storage.artifacts import export_file, inspect_file, put_file, read_file


def test_regular_reads_reject_symlink_pipe_and_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"real content")
    linked = tmp_path / "link"
    linked.symlink_to(source)
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    assert unwrap(read_bytes(source)) == b"real content"
    assert isinstance(read_bytes(linked), Failure)
    assert isinstance(read_bytes(pipe), Failure)
    assert isinstance(read_bytes(tmp_path / ".." / "source"), Failure)
    assert isinstance(read_bytes(source, 3), Failure)


def test_export_never_overwrites(tmp_path: Path) -> None:
    destination = tmp_path / "out"
    assert unwrap(write_new_bytes(destination, b"first"))["exported"]
    repeated = write_new_bytes(destination, b"second")
    assert isinstance(repeated, Failure) and repeated.code == "conflict"
    assert destination.read_bytes() == b"first"
    assert not list(tmp_path.glob(".stage-*"))


def test_private_files_deduplicate_and_detect_corruption(store: Path, tmp_path: Path) -> None:
    first = unwrap(put_file(store, "sample", b"same bytes", "one.txt", "text/plain", "one"))
    second = unwrap(put_file(store, "sample", b"same bytes", "two.txt", "text/plain", "two"))
    assert first.version != second.version
    assert first.content_sha256 == second.content_sha256
    assert len(list((store / "objects").iterdir())) == 1
    assert unwrap(put_file(store, "sample", b"same bytes", "one.txt", "text/plain", "one")).reused
    assert isinstance(
        put_file(store, "sample", b"changed", "one.txt", "text/plain", "one"), Failure
    )
    assert isinstance(inspect_file(store, "other", first.version), Failure)
    assert isinstance(read_file(store, "other", first.version), Failure)
    destination = tmp_path / "export"
    unwrap(export_file(store, "sample", first.version, destination))
    assert destination.read_bytes() == b"same bytes"
    (store / "objects" / first.content_sha256).write_bytes(b"changed")
    corrupt = read_file(store, "sample", first.version)
    assert isinstance(corrupt, Failure) and corrupt.code == "integrity"


def test_private_store_permissions_and_object_symlinks(store: Path, tmp_path: Path) -> None:
    from toolsmith.storage.database import inspect_store

    store.chmod(0o755)
    result = inspect_store(store, "sample")
    assert isinstance(result, Failure) and result.code == "denied"
    store.chmod(0o700)
    reference = unwrap(
        put_file(store, "sample", b"private", "one", "application/octet-stream", "one")
    )
    object_path = store / "objects" / reference.content_sha256
    object_path.unlink()
    target = tmp_path / "elsewhere"
    target.write_bytes(b"private")
    object_path.symlink_to(target)
    assert isinstance(read_file(store, "sample", reference.version), Failure)
