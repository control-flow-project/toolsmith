import gzip
import os
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch

from toolsmith.files import copy_file
from toolsmith.readers.tables import decode_table
from toolsmith.result import Failure, unwrap


def test_512_mib_original_uses_bounded_streaming_and_exact_byte_limits(tmp_path: Path) -> None:
    source = tmp_path / "original"
    size = 512 * 1024 * 1024
    with source.open("wb") as stream:
        stream.truncate(size)
        stream.seek(size - 7)
        stream.write(b"content")
    read = os.read
    largest = 0

    def bounded_read(descriptor: int, count: int) -> bytes:
        nonlocal largest
        largest = max(largest, count)
        return read(descriptor, count)

    with patch("toolsmith.files.os.read", side_effect=bounded_read):
        copied = unwrap(copy_file(source, tmp_path / "copy", size))
    assert copied.content_bytes == size and largest <= 65536
    with (tmp_path / "copy").open("rb") as reader:
        reader.seek(size - 7)
        assert reader.read() == b"content"
    denied = copy_file(source, tmp_path / "too-small", size - 1)
    assert isinstance(denied, Failure) and denied.code == "limit"
    assert not (tmp_path / "too-small").exists()


def test_tabular_decompression_bomb_does_not_return_a_prefix() -> None:
    bomb = gzip.compress(b"a" * (64 * 1024 * 1024 + 1))
    result = decode_table(bomb, "gzip-csv")
    assert isinstance(result, Failure) and result.code == "limit"


def test_zip_csv_rejects_encryption_and_symlink_member(tmp_path: Path) -> None:
    source = tmp_path / "csv.zip"
    with zipfile.ZipFile(source, "w") as archive:
        member = zipfile.ZipInfo("source.csv")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o600) << 16
        archive.writestr(member, b"Name,Value\nA,10\n")
    assert isinstance(decode_table(source.read_bytes(), "zip-csv"), Failure)
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("source.csv", b"Name,Value\nA,10\n")
    data = bytearray(source.read_bytes())
    marker = data.index(b"PK\x01\x02")
    data[marker + 8] |= 1
    assert isinstance(decode_table(bytes(data), "zip-csv"), Failure)
