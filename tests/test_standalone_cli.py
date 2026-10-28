import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest
from semantic_support import FixtureEncoder

from toolsmith.acquisition.client import FetchResponse
from toolsmith.cli import main
from toolsmith.result import Success


@pytest.mark.parametrize("engine", ("lexical", "semantic"))
def test_query_rejects_superseded_source_body_controls(
    engine: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "--json",
                "search",
                engine,
                "query",
                "question",
                "--database",
                str(tmp_path / "application.sqlite3"),
                "--scope",
                "permitted",
                "--sources",
                str(tmp_path / "sources.json"),
            ]
        )
        == 2
    )
    assert not json.loads(capsys.readouterr().out)["ok"]
    assert not list(tmp_path.iterdir())


def test_cli_rejects_removed_deterministic_html_table_reader(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--json", "read", "html-tables", str(tmp_path / "source.html")]) == 2
    assert not json.loads(capsys.readouterr().out)["ok"]
    assert not list(tmp_path.iterdir())


def test_cli_index_batch_can_select_from_more_than_10000_explicit_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database, sources = tmp_path / "application.sqlite3", tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            [{"reference": f"entry:{number}", "text": "retained text"} for number in range(10_001)]
        )
    )
    common = ["--json", "search", "lexical"]
    assert main(common + ["init", "--database", str(database)]) == 0
    capsys.readouterr()
    assert (
        main(
            common
            + ["index", "--database", str(database), "--sources", str(sources), "--limit", "1"]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert result == {"indexed": 1, "unchanged": 0, "remaining": 10_000}


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
                "--scope",
                "lexical_document",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert len(result["hits"]) == 1 and result["hits"][0]["reference"] == "page:1"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "CREATE TABLE canonical (reference TEXT PRIMARY KEY, text_digest TEXT NOT NULL, text TEXT NOT NULL)"
        )
        for entry in json.loads(sources.read_text()):
            import hashlib

            connection.execute(
                "INSERT INTO canonical VALUES (:reference,:value,:text)",
                {
                    "reference": entry["reference"],
                    "value": hashlib.sha256(entry["text"].encode()).hexdigest(),
                    "text": entry["text"],
                },
            )
    assert main(common + ["check", "--database", str(database), "--scope", "canonical"]) == 0
    capsys.readouterr()
    assert not list(tmp_path.rglob("objects")) and not (tmp_path / "toolsmith.sqlite3").exists()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "CREATE VIEW requested AS SELECT reference, text_digest FROM lexical_document WHERE reference = 'page:1' UNION ALL SELECT 'missing', '"
            + "b" * 64
            + "'"
        )
    assert main(common + ["status", "--database", str(database), "--scope", "requested"]) == 0
    states = json.loads(capsys.readouterr().out)["result"]
    assert states == {"entries": 2, "indexed": 1, "missing": 1, "stale": 0}


def test_semantic_cli_status_uses_index_owned_profile_validation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "application.sqlite3"
    common = ["--json", "search", "semantic"]
    assert main(common + ["init", "--database", str(database)]) == 0
    capsys.readouterr()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("INSERT INTO embedding_profile VALUES ('invalid', '{}')")
    assert (
        main(common + ["status", "--database", str(database), "--scope", "embedding_document"]) == 9
    )
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "integrity"


def test_semantic_cli_uses_the_library_query_byte_and_token_bounds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "application.sqlite3"
    common = ["--json", "search", "semantic"]
    assert main(common + ["init", "--database", str(database)]) == 0
    capsys.readouterr()
    query = "wet" + " " * 3000
    with patch("toolsmith.semantic.load_model", return_value=Success(FixtureEncoder())):
        assert (
            main(
                common
                + [
                    "query",
                    query,
                    "--database",
                    str(database),
                    "--scope",
                    "embedding_document",
                    "--model-directory",
                    str(tmp_path / "model"),
                ]
            )
            == 0
        )
    assert json.loads(capsys.readouterr().out)["result"]["candidates"] == 0


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


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "relative"])
def test_http_destination_is_rejected_before_any_fetch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    policy, budget = tmp_path / "http.json", tmp_path / "budget.json"
    policy.write_text('{"hosts":["example.com"]}')
    budget.write_text(
        '{"group":"public","period_seconds":60,"group_requests":5,"group_bytes":10485760,"task_requests":3,"task_bytes":5242880}'
    )
    destination = tmp_path / "response.txt"
    if kind == "file":
        destination.write_bytes(b"preserved")
    elif kind == "directory":
        destination.mkdir()
    elif kind == "symlink":
        destination.symlink_to(tmp_path / "missing")
    else:
        destination = Path("relative-response.txt")
    response = FetchResponse(
        "https://example.com/", "text/plain", b"response", 1, 8, "2026-10-25T00:00:00+00:00"
    )
    with patch("toolsmith.cli.commands.fetch_http", return_value=Success(response)) as fetch:
        code = main(
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
                str(destination),
            ]
        )
    assert code == (2 if kind == "relative" else 4)
    assert json.loads(capsys.readouterr().out)["error"]["code"] == (
        "invalid_input" if kind == "relative" else "conflict"
    )
    fetch.assert_not_called()
    assert not (tmp_path / "quotas").exists()
    if kind == "file":
        assert destination.read_bytes() == b"preserved"
    elif kind == "directory":
        assert destination.is_dir() and not list(destination.iterdir())
    elif kind == "symlink":
        assert destination.is_symlink() and not (tmp_path / "missing").exists()


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
