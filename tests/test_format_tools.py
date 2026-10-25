import gzip
import json
import stat
import zipfile
from pathlib import Path

import pytest

from toolsmith.acquisition.urls import resolve_urls
from toolsmith.archives import list_archive
from toolsmith.cli import main
from toolsmith.result import Failure, unwrap


def test_url_batches_resolve_relative_links_without_dropping_query_identity() -> None:
    values = unwrap(
        resolve_urls(
            "https://example.com/section/index",
            ("../story?edition=one", "/story?edition=two", "https://elsewhere.example/item"),
        )
    )
    assert [unwrap(value.result) for value in values] == [
        "https://example.com/story?edition=one",
        "https://example.com/story?edition=two",
        "https://elsewhere.example/item",
    ]
    assert [value.index for value in values] == [0, 1, 2]


def test_bad_links_are_individual_failures_and_do_not_echo_secrets() -> None:
    values = unwrap(
        resolve_urls(
            "https://example.com/",
            (
                "/good",
                "javascript:alert(1)",
                "https://user:private@example.com/",
                "/story?access_token=private",
            ),
        )
    )
    assert unwrap(values[0].result) == "https://example.com/good"
    assert all(isinstance(value.result, Failure) for value in values[1:])
    assert "private" not in repr(values)


def test_url_cli_uses_the_batch_library(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "links.json"
    source.write_text('["/one","/two"]')
    assert main(["--json", "url", "resolve", "https://example.com/", "--file", str(source)]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["result"][1]["result"]["value"] == "https://example.com/two"


def test_archive_listing_and_member_read_are_generic_and_file_oriented(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, destination = tmp_path / "files.zip", tmp_path / "selected.xml"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("folder/", b"")
        archive.writestr("folder/feed.xml", b"<root/>")
    entries = unwrap(list_archive(source))
    assert [(entry.name, entry.is_directory) for entry in entries] == [
        ("folder", True),
        ("folder/feed.xml", False),
    ]
    assert (
        main(
            [
                "--json",
                "archive",
                "read",
                str(source),
                "folder/feed.xml",
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert destination.read_bytes() == b"<root/>"


def test_archive_listing_rejects_link_and_unsafe_members(tmp_path: Path) -> None:
    source = tmp_path / "link.zip"
    with zipfile.ZipFile(source, "w") as archive:
        item = zipfile.ZipInfo("symlink")
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(item, "/etc/passwd")
    assert isinstance(list_archive(source), Failure)
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../outside", "bad")
    assert isinstance(list_archive(source), Failure)


def test_invalid_archive_is_a_typed_failure(tmp_path: Path) -> None:
    source = tmp_path / "invalid.zip"
    source.write_bytes(b"not zip")
    assert isinstance(list_archive(source), Failure)


def test_gzip_cli_expands_into_a_new_file_with_an_explicit_bound(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, destination = tmp_path / "feed.gz", tmp_path / "feed.xml"
    source.write_bytes(gzip.compress(b"<root/>"))
    assert (
        main(
            [
                "--json",
                "decompress",
                "gzip",
                str(source),
                "--destination",
                str(destination),
                "--maximum-bytes",
                "100",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert destination.read_bytes() == b"<root/>"
    assert (
        main(["--json", "decompress", "gzip", str(source), "--destination", str(destination)]) == 4
    )
    assert json.loads(capsys.readouterr().out)["ok"] is False
