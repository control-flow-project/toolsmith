import ast
import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest

from toolsmith.result import ToolsmithError
from toolsmith.sqlite import execute


def test_named_parameters_preserve_repeated_names_and_nulls() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        row = execute(
            connection,
            "SELECT :identity, :identity, :optional",
            {"identity": "entry", "optional": None},
        ).fetchone()
        assert row == ("entry", "entry", None)
        with pytest.raises(sqlite3.ProgrammingError):
            execute(connection, "SELECT :required", {"other": "entry"})


@pytest.mark.parametrize("parameters", ((), ("entry",), ["entry"], "entry"))
def test_query_owner_rejects_positional_parameters(parameters: object) -> None:
    with (
        closing(sqlite3.connect(":memory:")) as connection,
        pytest.raises(ToolsmithError, match="named mapping"),
    ):
        execute(connection, "SELECT :identity", cast(Mapping[str, object], parameters))


def test_authored_sql_has_no_positional_placeholders() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for folder in ("src", "tests", "scripts", "examples"):
        for path in sorted((root / folder).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    value = node.value
                    sql = re.match(
                        r"\s*(?:SELECT|INSERT|UPDATE|DELETE|WITH|VALUES|WHERE|LIMIT|OFFSET)\b",
                        value,
                        re.I,
                    )
                    if (
                        sql
                        and chr(63) in value
                        and not value.lstrip().startswith(("import ", "from "))
                    ):
                        violations.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not violations, "Positional SQL placeholders: " + ", ".join(violations)


def test_documented_python_examples_use_named_sql() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for path in sorted((root / "docs").rglob("*.md")):
        for number, block in enumerate(
            re.findall(r"```(?:python|py)\n(.*?)```", path.read_text(), re.S), 1
        ):
            for node in ast.walk(ast.parse(block)):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and re.match(
                        r"\s*(?:SELECT|INSERT|UPDATE|DELETE|WITH|VALUES|WHERE|LIMIT|OFFSET)\b",
                        node.value,
                        re.I,
                    )
                    and chr(63) in node.value
                ):
                    violations.append(f"{path.relative_to(root)}:block {number}:{node.lineno}")
    assert not violations, "Positional SQL in documented examples: " + ", ".join(violations)
