"""Explicit node selection keeps the one DOM parser and independent safety budgets."""

import json
from pathlib import Path

import pytest

from toolsmith.cli import main
from toolsmith.readers import inspect_html, read_html
from toolsmith.readers.html_dom import parse_html
from toolsmith.result import Failure, ToolsmithError, unwrap


def dense_html(nodes: int) -> bytes:
    return b"<main>" + b"<br>" * (nodes - 1) + b"Exact observations</main>"


def test_explicit_node_limit_admits_dense_input_without_changing_the_default() -> None:
    original = dense_html(50_001)
    for reader in (inspect_html, read_html):
        failed = reader(original)
        assert isinstance(failed, Failure)
        assert failed.message == "HTML node budget exceeded: 50001 > 50000"
        assert not isinstance(reader(original, maximum_nodes=50_001), Failure)
        assert isinstance(reader(original, maximum_nodes=50_000), Failure)
    assert parse_html(original, maximum_nodes=50_001).tag == "root"
    assert unwrap(inspect_html(original, maximum_nodes=500_000)).text == "Exact observations"


def test_node_ceiling_is_inclusive_and_does_not_drop_a_tail_observation() -> None:
    original = dense_html(500_000)
    assert unwrap(inspect_html(original, maximum_nodes=500_000)).text == "Exact observations"
    failed = inspect_html(dense_html(500_001), maximum_nodes=500_000)
    assert isinstance(failed, Failure)
    assert failed.message == "HTML node budget exceeded: 500001 > 500000"


@pytest.mark.parametrize("maximum", [0, -1, True, 500_001])
def test_node_option_is_validated_at_each_library_boundary(maximum: int) -> None:
    for reader in (inspect_html, read_html):
        assert isinstance(reader(b"<main>Text</main>", maximum_nodes=maximum), Failure)
    with pytest.raises(ToolsmithError):
        parse_html(b"<main>Text</main>", maximum_nodes=maximum)


def test_larger_node_budget_keeps_depth_attributes_bytes_and_access_independent() -> None:
    nested = inspect_html(b"<div>" * 128 + b"Text", maximum_nodes=500_000)
    assert isinstance(nested, Failure)
    assert nested.message == "HTML nesting budget exceeded: 128 >= 128"
    attributes = inspect_html(
        b"<main " + b" ".join(f"data-{i}='x'".encode() for i in range(101)) + b">Text</main>",
        maximum_nodes=500_000,
    )
    assert isinstance(attributes, Failure)
    assert attributes.message == "HTML attribute count exceeded: 101 > 100"
    assert isinstance(
        inspect_html(dense_html(20), maximum_nodes=500_000, maximum_bytes=10), Failure
    )
    assert isinstance(
        inspect_html(b"<title>Access denied</title><main>Blocked</main>", maximum_nodes=500_000),
        Failure,
    )
    password = b'<main>Text</main><div role="dialog"><input type="password"></div>'
    assert unwrap(inspect_html(password, maximum_nodes=500_000)).password_controls
    assert isinstance(read_html(password, maximum_nodes=500_000), Failure)
    assert isinstance(
        read_html(
            b"<main>" + b"x" * (4 * 1024 * 1024 + 1) + b"</main>",
            maximum_bytes=8 * 1024 * 1024,
            maximum_nodes=500_000,
        ),
        Failure,
    )


def test_cli_html_and_html_links_use_the_explicit_node_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "dense.html"
    path.write_bytes(dense_html(50_001))
    for reader in ("html", "html-links"):
        assert main(["--json", "read", reader, str(path)]) != 0
        assert "node budget" in json.loads(capsys.readouterr().out)["error"]["message"]
        assert main(["--json", "read", reader, str(path), "--maximum-nodes", "500000"]) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True
        assert main(["--json", "read", reader, str(path), "--maximum-nodes", "500001"]) != 0
        assert json.loads(capsys.readouterr().out)["ok"] is False
