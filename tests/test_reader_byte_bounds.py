"""Explicit source-byte bounds preserve defaults and independent structure/output limits."""

import json
from pathlib import Path

import pytest

from toolsmith.cli import main
from toolsmith.readers import (
    XmlLimits,
    inspect_html,
    read_html,
    read_text,
    read_xml,
    read_xml_records,
)
from toolsmith.readers.html_dom import parse_html
from toolsmith.result import Failure, ToolsmithError, unwrap

MIB = 1024 * 1024


def padded_html(size: int = 5 * MIB, body: bytes = b"<main>Published data</main>") -> bytes:
    return (
        b'<html><head><meta name="padding" content="'
        + b"x" * size
        + b'"></head>'
        + body
        + b"</html>"
    )


def test_html_explicit_eight_mib_uses_the_same_parser_with_unchanged_default() -> None:
    original = padded_html()
    assert isinstance(inspect_html(original), Failure)
    assert isinstance(read_html(original), Failure)
    observed = unwrap(inspect_html(original, maximum_bytes=8 * MIB))
    assert observed.text == "Published data"
    assert len(observed.metadata[0].content) == 5 * MIB
    assert unwrap(read_html(original, maximum_bytes=8 * MIB)).parts[0].text == "Published data"
    assert parse_html(original, maximum_bytes=8 * MIB).tag == "root"


@pytest.mark.parametrize("maximum", [0, -1, True, 8 * MIB + 1])
def test_html_explicit_bound_is_validated_at_every_reader_boundary(maximum: int) -> None:
    original = b"<main>Public data</main>"
    assert isinstance(inspect_html(original, maximum_bytes=maximum), Failure)
    assert isinstance(read_html(original, maximum_bytes=maximum), Failure)
    with pytest.raises(ToolsmithError):
        parse_html(original, maximum_bytes=maximum)


def test_explicit_html_bytes_do_not_relax_access_password_structure_or_output() -> None:
    denied = padded_html(body=b"<title>Access denied</title><main>Not a report</main>")
    assert isinstance(inspect_html(denied, maximum_bytes=8 * MIB), Failure)
    assert isinstance(read_html(denied, maximum_bytes=8 * MIB), Failure)
    password = padded_html(
        body=b'<main>Public data</main><div role="dialog" aria-modal="true"><input type="password"></div>'
    )
    assert unwrap(inspect_html(password, maximum_bytes=8 * MIB)).password_controls
    assert isinstance(read_html(password, maximum_bytes=8 * MIB), Failure)
    for original in (
        b"<main>" + b"<p>x</p>" * 50_001 + b"</main>",
        b"<div>" * 128 + b"data" + b"</div>" * 128,
    ):
        assert isinstance(inspect_html(original, maximum_bytes=8 * MIB), Failure)
    text = b"<main>" + b"x" * (4 * MIB + 1) + b"</main>"
    assert isinstance(read_html(text, maximum_bytes=8 * MIB), Failure)
    oversized = b"<main>" + b"x" * (8 * MIB) + b"</main>"
    assert isinstance(inspect_html(oversized, maximum_bytes=8 * MIB), Failure)


def test_xml_explicit_144_mib_crosses_the_shared_utf8_ceiling_without_changing_defaults() -> None:
    original = b'<root><row value="exact"/></root>' + b" " * (128 * MIB + 1)
    assert isinstance(read_xml(original), Failure)
    selected = XmlLimits(maximum_bytes=144 * MIB)
    assert unwrap(read_xml(original, selected)).nodes == 2
    records = unwrap(
        read_xml_records(original, "row", lambda row: row.attributes["value"], selected)
    )
    assert records == ("exact",)
    assert (
        unwrap(read_text(original, "Exact bytes", maximum_bytes=144 * MIB))
        .parts[0]
        .text.startswith("<root>")
    )
    assert isinstance(read_xml(b"<root/>", XmlLimits(maximum_bytes=144 * MIB + 1)), Failure)
    assert isinstance(read_text(b"data", "Title", maximum_bytes=144 * MIB + 1), Failure)
    assert isinstance(read_xml(b"<!DOCTYPE root><root/>", selected), Failure)
    assert isinstance(
        read_xml(b"<root><row/></root>", XmlLimits(maximum_bytes=144 * MIB, maximum_nodes=1)),
        Failure,
    )


def test_cli_passes_explicit_byte_bounds_to_the_same_readers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = padded_html()
    source = tmp_path / "source.html"
    source.write_bytes(original)
    for reader in ("html", "html-links"):
        assert main(["--json", "read", reader, str(source)]) != 0
        assert json.loads(capsys.readouterr().out)["ok"] is False
        assert main(["--json", "read", reader, str(source), "--maximum-bytes", str(8 * MIB)]) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True
    source.write_bytes(b"<root/>")
    assert main(["--json", "read", "xml", str(source), "--maximum-bytes", str(144 * MIB)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["root"]["name"] == "root"
    source.write_bytes(b"text")
    assert (
        main(
            [
                "--json",
                "read",
                "text",
                str(source),
                "--title",
                "Bounded",
                "--maximum-bytes",
                str(144 * MIB),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["result"]["parts"][0]["text"] == "text"
