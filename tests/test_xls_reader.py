import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from toolsmith.cli import main
from toolsmith.readers.xls import MAXIMUM_XLS_BYTES, read_xls
from toolsmith.result import Failure, unwrap

FIXTURE = Path(__file__).parent / "fixtures" / "typed-cells.xls"


def test_actual_biff_cells_keep_binary_precision_formats_and_date_mode() -> None:
    sheet = unwrap(read_xls(FIXTURE.read_bytes()))
    assert sheet.sheet_names == ("Measurements", "Notes")
    assert (sheet.name, sheet.total_rows, sheet.total_columns, sheet.date_mode) == (
        "Measurements",
        4,
        2,
        0,
    )
    assert sheet.merged_cells == ((0, 1, 0, 2),)
    amount, date = sheet.rows[2]
    assert amount.kind == "number"
    assert amount.value == str(Decimal.from_float(30.1))
    assert amount.value != "30.1"
    assert amount.number_format == "0.00"
    assert (date.kind, date.value) == ("date", "46321")
    assert "yyyy" in date.number_format
    assert sheet.rows[3][1].value == "0"
    assert sheet.next_row is None


def test_paging_and_sheet_selection_are_explicit() -> None:
    content = FIXTURE.read_bytes()
    first = unwrap(read_xls(content, limit=2))
    assert first.next_row == 2 and len(first.rows) == 2
    final = unwrap(read_xls(content, start=2, limit=2))
    assert final.next_row is None and final.rows[0][0].kind == "number"
    other = unwrap(read_xls(content, sheet=1))
    assert other.rows[0][0].value == "No currency inferred."


@pytest.mark.parametrize(
    "options",
    [
        {"sheet": 2},
        {"start": 4},
        {"limit": 0},
        {"sheet": -1},
        {"maximum_cells": 1},
        {"maximum_text_bytes": 1},
    ],
)
def test_invalid_ranges_or_budgets_fail_without_partial_success(options: dict[str, int]) -> None:
    assert isinstance(read_xls(FIXTURE.read_bytes(), **options), Failure)


def test_bad_and_oversized_input_and_missing_optional_dependency() -> None:
    for value in (b"", b"not an XLS", b"PK\x03\x04not an XLSX"):
        assert isinstance(read_xls(value), Failure)
    result = read_xls(b"x" * (MAXIMUM_XLS_BYTES + 1))
    assert isinstance(result, Failure) and result.code == "limit"
    with patch("toolsmith.readers.xls.import_module", side_effect=ImportError):
        result = read_xls(FIXTURE.read_bytes())
    assert isinstance(result, Failure) and result.code == "unavailable"


def test_cli_calls_identical_reader(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--json", "read", "xls", str(FIXTURE), "--start", "2", "--limit", "1"]) == 0
    value = json.loads(capsys.readouterr().out)["result"]
    assert value["rows"][0][0]["value"] == str(Decimal.from_float(30.1))
    assert value["next_row"] == 3


def test_truncated_ole_container_is_an_expected_failure() -> None:
    content = FIXTURE.read_bytes()
    for length in (8, 16, 32, 256, 512, 1024, 2048, 3000):
        result = read_xls(content[:length])
        assert isinstance(result, Failure) and result.code == "invalid_input"
