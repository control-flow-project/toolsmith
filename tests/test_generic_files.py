import hashlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from toolsmith.files import copy_file, hash_file
from toolsmith.result import Failure, unwrap


def test_streaming_accepts_explicit_native_int64_budgets(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"selected bytes")
    expected = unwrap(hash_file(source, 2**63 - 1))
    assert unwrap(copy_file(source, tmp_path / "copy", 2**63 - 1)) == expected
    assert expected.content_bytes == len(b"selected bytes")


def test_large_file_copy_is_streamed_exact_and_private(tmp_path: Path) -> None:
    source = tmp_path / "large.pdf"
    with source.open("wb") as stream:
        for _block in range(300):
            stream.write(b"source evidence\n" * 4096)
    sizes: list[int] = []
    read = os.read

    def recording(descriptor: int, count: int) -> bytes:
        sizes.append(count)
        return read(descriptor, count)

    with patch("toolsmith.files.os.read", side_effect=recording):
        result = unwrap(copy_file(source, tmp_path / "copy.pdf", 512 * 1024 * 1024))
    assert result == unwrap(hash_file(source, 512 * 1024 * 1024))
    assert result.content_bytes == source.stat().st_size
    assert result.sha256 == hashlib.sha256((tmp_path / "copy.pdf").read_bytes()).hexdigest()
    assert max(sizes) <= 65536
    assert (tmp_path / "copy.pdf").stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".stage-*"))


def test_streaming_rejects_changed_input_and_leaves_no_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"a" * 100000)
    read = os.read
    changed = False

    def mutate(descriptor: int, count: int) -> bytes:
        nonlocal changed
        result = read(descriptor, count)
        if not changed:
            changed = True
            with source.open("ab") as writer:
                writer.write(b"changed")
        return result

    with patch("toolsmith.files.os.read", side_effect=mutate):
        failure = copy_file(source, tmp_path / "output", 200000)
    assert isinstance(failure, Failure) and failure.code == "conflict"
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".stage-*"))


@pytest.mark.parametrize("kind", ["symlink", "fifo", "oversized", "collision"])
def test_streaming_never_overwrites_or_reads_special_input(tmp_path: Path, kind: str) -> None:
    source, output = tmp_path / "source", tmp_path / "output"
    if kind == "fifo":
        os.mkfifo(source)
    elif kind == "symlink":
        source.symlink_to(tmp_path / "missing")
    else:
        source.write_bytes(b"input")
    if kind == "collision":
        output.write_bytes(b"preserved")
    result = copy_file(source, output, 1 if kind == "oversized" else 100)
    assert isinstance(result, Failure)
    assert not list(tmp_path.glob(".stage-*"))
    if kind == "collision":
        assert output.read_bytes() == b"preserved"
    else:
        assert not output.exists()
