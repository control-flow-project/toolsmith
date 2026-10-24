import json
import os
from pathlib import Path
from typing import cast

import pytest

from toolsmith.cli import main
from toolsmith.validation import JsonValue


def output(capture: pytest.CaptureFixture[str]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], json.loads(capture.readouterr().out))


def test_html_links_output_goes_to_a_private_file_with_a_compact_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, destination = tmp_path / "page.html", tmp_path / "page.json"
    source.write_text('<html><title>Index</title><a href="/entry">Company result</a></html>')
    assert main(["--json", "--output", str(destination), "read", "html-links", str(source)]) == 0
    receipt = output(capsys)
    assert receipt["ok"] is True
    assert "Company result" not in json.dumps(receipt)
    saved = json.loads(destination.read_bytes())
    assert saved["result"]["links"][0]["target"] == "/entry"
    assert saved["result"]["links"][0]["label"] == "Company result"
    assert os.stat(destination).st_mode & 0o077 == 0


def test_xml_cli_preserves_all_repeated_elements(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "feed.xml"
    source.write_text("<root><item>one</item><item>two</item></root>")
    assert main(["--json", "read", "xml", str(source)]) == 0
    value = output(capsys)
    result = value["result"]
    assert isinstance(result, dict) and result["nodes"] == 3


def test_jsonl_cli_reads_every_record(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "items.jsonl"
    source.write_text('{"number":1}\n{"number":2}\n')
    assert main(["--json", "read", "jsonl", str(source)]) == 0
    assert output(capsys)["result"] == [{"number": 1}, {"number": 2}]


def test_output_never_overwrites_an_existing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, destination = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text('{"new":true}')
    destination.write_text("original")
    assert main(["--json", "--output", str(destination), "read", "json", str(source)]) != 0
    assert output(capsys)["ok"] is False
    assert destination.read_text() == "original"


def test_failed_read_does_not_publish_a_result_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, destination = tmp_path / "invalid.xml", tmp_path / "output.json"
    source.write_text("<root>")
    assert main(["--json", "--output", str(destination), "read", "xml", str(source)]) == 2
    assert output(capsys)["ok"] is False
    assert not destination.exists()
