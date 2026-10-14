import hashlib
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from toolsmith.archives import MemberDigest, MemberSource, pack_files, unpack_files
from toolsmith.result import Failure, unwrap


def test_generic_archive_preserves_exact_explicit_files_and_empty_pages(tmp_path: Path) -> None:
    source, page, blank = tmp_path / "source", tmp_path / "page", tmp_path / "blank"
    source.write_bytes(b"original")
    page.write_text("Exact unicode clause β")
    blank.write_bytes(b"")
    report = unwrap(
        pack_files(
            (
                MemberSource("source.pdf", source),
                MemberSource("pages/page-1.txt", page),
                MemberSource("pages/page-2.txt", blank),
            ),
            tmp_path / "bundle.zip",
        )
    )
    restored = unwrap(unpack_files(tmp_path / "bundle.zip", tmp_path / "restored", report.members))
    assert restored == report
    assert (tmp_path / "restored/pages/page-1.txt").read_bytes() == page.read_bytes()
    assert (tmp_path / "restored/pages/page-2.txt").read_bytes() == b""
    assert (tmp_path / "restored").stat().st_mode & 0o777 == 0o700
    assert not list(tmp_path.glob(".stage-*"))


@pytest.mark.parametrize(
    "name", ["../outside", "/absolute", "a/../b", "a//b", "a\\b", "C:drive", "a\x00b"]
)
def test_archive_names_are_not_paths_to_existing_data(tmp_path: Path, name: str) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"bytes")
    result = pack_files((MemberSource(name, source),), tmp_path / "bundle.zip")
    assert isinstance(result, Failure)
    assert not (tmp_path / "bundle.zip").exists()


@pytest.mark.parametrize(
    "failure", ["digest", "unexpected", "symlink", "collision", "encrypted", "corrupt"]
)
def test_archive_rejection_does_not_publish_partial_files(tmp_path: Path, failure: str) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"original")
    report = unwrap(pack_files((MemberSource("expected", source),), tmp_path / "bundle.zip"))
    expected = report.members
    if failure == "digest":
        expected = (replace(expected[0], sha256="a" * 64),)
    elif failure in {"unexpected", "symlink", "encrypted"}:
        with zipfile.ZipFile(tmp_path / "bundle.zip", "w") as archive:
            entry = zipfile.ZipInfo("unexpected" if failure == "unexpected" else "expected")
            if failure == "symlink":
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o700) << 16
            archive.writestr(entry, b"original")
        if failure == "encrypted":
            content = bytearray((tmp_path / "bundle.zip").read_bytes())
            location = content.index(b"PK\x01\x02")
            content[location + 8] |= 1
            (tmp_path / "bundle.zip").write_bytes(content)
    elif failure == "collision":
        (tmp_path / "restored").mkdir()
        (tmp_path / "restored/keep").write_bytes(b"preserved")
    else:
        (tmp_path / "bundle.zip").write_bytes(b"not a ZIP")
    result = unpack_files(tmp_path / "bundle.zip", tmp_path / "restored", expected)
    assert isinstance(result, Failure)
    assert not list(tmp_path.glob(".stage-*"))
    if failure == "collision":
        assert (tmp_path / "restored/keep").read_bytes() == b"preserved"
    else:
        assert not (tmp_path / "restored").exists()


def test_archive_member_prefix_collision_and_expansion_are_explicit(tmp_path: Path) -> None:
    original = tmp_path / "source"
    original.write_bytes(b"content")
    assert isinstance(
        pack_files((MemberSource("a", original), MemberSource("a/b", original)), tmp_path / "zip"),
        Failure,
    )
    checksum = hashlib.sha256(b"content").hexdigest()
    assert isinstance(
        unpack_files(original, tmp_path / "restored", (MemberDigest("source", checksum, 7),), 1),
        Failure,
    )


def test_writer_enforces_the_same_directory_limits_as_reader(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"byte")
    names = tuple(MemberSource(f"{number:04d}/" + "a" * 1000, source) for number in range(5000))
    result = pack_files(names, tmp_path / "too-large.zip")
    assert isinstance(result, Failure) and result.code == "limit"
    assert not (tmp_path / "too-large.zip").exists()
    deep = MemberSource("/".join(["a"] * 65), source)
    assert isinstance(pack_files((deep,), tmp_path / "too-deep.zip"), Failure)
