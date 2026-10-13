import json
import os
from pathlib import Path
from typing import cast

import pytest

from toolsmith.cli import main
from toolsmith.operations.cleanup import preview_cleanup
from toolsmith.result import unwrap
from toolsmith.storage.models import Document, TextPart
from toolsmith.storage.text import put_text
from toolsmith.validation import JsonValue, canonical_json


def output(capture: pytest.CaptureFixture[str]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], json.loads(capture.readouterr().out))


def test_cli_calls_the_library_and_formats_expected_errors(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = unwrap(
        put_text(
            store,
            "sample",
            "item",
            Document("Title", (TextPart("Part", "CLI parity words"),)),
            "text",
        )
    )
    assert (
        main(
            [
                "--json",
                "--root",
                str(store),
                "--collection",
                "sample",
                "text",
                "inspect",
                reference.version,
            ]
        )
        == 0
    )
    result = output(capsys)
    assert result["ok"] is True
    assert isinstance(result["result"], dict) and result["result"]["version"] == reference.version
    assert (
        main(
            [
                "--json",
                "--root",
                str(store),
                "--collection",
                "other",
                "text",
                "inspect",
                reference.version,
            ]
        )
        == 5
    )
    error = output(capsys)
    assert error["ok"] is False
    assert str(store) not in str(error)


def test_cli_readers_require_no_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "input.txt"
    source.write_text("plain words", encoding="utf-8")
    assert main(["--json", "read", "text", str(source), "--title", "Test"]) == 0
    result = output(capsys)
    assert result["ok"] is True
    assert main(["--json", "capabilities"]) == 0
    assert output(capsys)["ok"] is True
    assert main(["--json", "serve"]) == 2
    assert output(capsys)["ok"] is False


def test_cli_document_import_and_bounded_file_read(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    supplied = tmp_path / "document.json"
    supplied.write_text('{"title":"Title","parts":[{"label":"Part","text":"Imported"}]}')
    assert (
        main(
            [
                "--json",
                "--root",
                str(store),
                "--collection",
                "sample",
                "text",
                "put",
                str(supplied),
                "--item",
                "doc",
                "--request-id",
                "import",
            ]
        )
        == 0
    )
    assert output(capsys)["ok"] is True
    supplied.write_text('{"title":"Title","parts":[],"unexpected":true}')
    assert (
        main(
            [
                "--json",
                "--root",
                str(store),
                "--collection",
                "sample",
                "text",
                "put",
                str(supplied),
                "--item",
                "doc",
                "--request-id",
                "other",
            ]
        )
        == 2
    )
    assert output(capsys)["ok"] is False


def test_cli_cleanup_uses_the_library_plan_and_rejects_unknown_fields(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    staged = store / "tmp" / (".stage-" + "a" * 32 + ".tmp")
    staged.write_bytes(b"inactive")
    staged.chmod(0o600)
    os.utime(staged, (1, 1))
    plan = unwrap(preview_cleanup(store, "sample"))
    supplied = tmp_path / "cleanup.json"
    encoded = canonical_json(plan)
    invalid = json.loads(encoded)
    invalid["unexpected"] = True
    supplied.write_text(json.dumps(invalid))
    arguments = [
        "--json",
        "--root",
        str(store),
        "--collection",
        "sample",
        "maintenance",
        "cleanup-apply",
        str(supplied),
    ]
    assert main(arguments) == 2
    assert output(capsys)["ok"] is False and staged.exists()
    supplied.write_bytes(encoded)
    assert main(arguments) == 0
    assert output(capsys)["result"] == {"deleted": 1, "bytes": 8}
    assert not staged.exists()
