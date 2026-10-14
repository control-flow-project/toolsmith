import json
from pathlib import Path
from unittest.mock import patch

import pytest

from toolsmith.acquisition.client import FetchResponse
from toolsmith.cli import main
from toolsmith.result import Success


def test_caller_owned_lexical_cli_uses_no_text_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database, sources = tmp_path / "application.sqlite3", tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            [
                {"reference": "page:1", "text": "Restricted Payments mean dividends"},
                {"reference": "page:2", "text": "Restricted transactions and other Payments"},
            ]
        )
    )
    common = ["--json", "search", "lexical"]
    assert main(common + ["init", "--database", str(database)]) == 0
    capsys.readouterr()
    assert main(common + ["index", "--database", str(database), "--sources", str(sources)]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result == {"indexed": 2, "unchanged": 0, "remaining": 0}
    assert (
        main(
            common
            + [
                "query",
                '"Restricted Payments"',
                "--database",
                str(database),
                "--sources",
                str(sources),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert len(result["hits"]) == 1 and result["hits"][0]["reference"] == "page:1"
    assert main(common + ["check", "--database", str(database), "--sources", str(sources)]) == 0
    capsys.readouterr()
    assert not list(tmp_path.rglob("objects")) and not (tmp_path / "toolsmith.sqlite3").exists()
    references = tmp_path / "references.json"
    references.write_text('["page:1","missing"]')
    assert (
        main(common + ["status", "--database", str(database), "--references", str(references)]) == 0
    )
    states = json.loads(capsys.readouterr().out)["result"]
    assert states[0]["digest"] is not None and states[1]["digest"] is None


def test_generic_raw_http_cli_returns_receipt_and_explicit_file_without_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy, budget = tmp_path / "http.json", tmp_path / "budget.json"
    policy.write_text('{"hosts":["example.com"]}')
    budget.write_text(
        '{"group":"public","period_seconds":60,"group_requests":5,"group_bytes":10485760,"task_requests":3,"task_bytes":5242880}'
    )
    response = FetchResponse(
        "https://example.com/", "text/plain", b"response", 1, 8, "2026-10-14T00:00:00+00:00"
    )
    with patch("toolsmith.cli.commands.fetch_http", return_value=Success(response)):
        assert (
            main(
                [
                    "--json",
                    "http",
                    "request",
                    "https://example.com/",
                    "--policy",
                    str(policy),
                    "--budget-policy",
                    str(budget),
                    "--network-state",
                    str(tmp_path / "quotas"),
                    "--task",
                    "task",
                    "--destination",
                    str(tmp_path / "response.txt"),
                ]
            )
            == 0
        )
    receipt = json.loads(capsys.readouterr().out)["result"]
    assert receipt["content_bytes"] == 8 and "content" not in receipt
    assert (tmp_path / "response.txt").read_bytes() == b"response"
    assert str(tmp_path) not in str(receipt)
    assert not list(tmp_path.rglob("*.sqlite3"))


def test_read_table_and_json_cli_call_generic_readers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    table = tmp_path / "table.csv"
    table.write_bytes(b"Name,Value\nA,10\nA,20\nB,30\n")
    assert (
        main(
            [
                "--json",
                "read",
                "table",
                str(table),
                "--column",
                "Value",
                "--filter",
                "Name=A",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["scanned"] == 3 and result["matched"] == 2 and result["truncated"]
    document = tmp_path / "input.json"
    document.write_bytes(b'{"field":1}')
    assert main(["--json", "read", "json", str(document)]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == {"field": 1}
