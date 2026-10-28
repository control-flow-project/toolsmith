import math
import random
import sqlite3
import struct
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

from toolsmith.result import ToolsmithError
from toolsmith.semantic.profile import pack_vector
from toolsmith.semantic.vector import load_vector_extension


@pytest.mark.parametrize(
    "values",
    [
        (1, 2, 3, 4),
        (128, 255, 256, 10000),
        (None, 1, 2, 3, 4),
        (None, -9, 128, 256, 10000),
        (None, 1.0, 1.5, 2.0),
        (-(2**63), -(2**31), 0, 2**31, 2**63 - 1),
        (None, 1.0, 1.5, 2.0, "1"),
        (),
    ],
)
def test_integer_membership_matches_sqlite_for_every_metadata_representation(
    values: tuple[object, ...],
) -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        load_vector_extension(connection)
        connection.execute("CREATE VIRTUAL TABLE vectors USING vec1(vector, selected)")
        connection.execute(
            "INSERT INTO vectors(cmd,arg) VALUES('rebuild','{index:\"flat\",distance:\"cos\"}')"
        )
        connection.execute("CREATE TABLE ordinary (id INTEGER PRIMARY KEY, selected)")
        vector = struct.pack("<384f", 1.0, *([0.0] * 383))
        for ordinal, value in enumerate(values, 1):
            connection.execute(
                "INSERT INTO vectors(rowid,vector,selected) VALUES (:rowid,:vector,:selected)",
                {"rowid": ordinal, "vector": vector, "selected": value},
            )
            connection.execute(
                "INSERT INTO ordinary VALUES (:ordinal,:value)",
                {"ordinal": ordinal, "value": value},
            )
        connection.execute("CREATE TABLE allowed (id)")
        connection.executemany(
            "INSERT INTO allowed VALUES (:value)",
            (
                {"value": value}
                for value in (
                    -(2**63),
                    -(2**31),
                    1,
                    1,
                    2,
                    128,
                    255,
                    256,
                    2**31 - 1,
                    2**31,
                    2**63 - 1,
                )
            ),
        )
        expected = {
            row[0]
            for row in connection.execute(
                "SELECT id FROM ordinary WHERE selected IN (SELECT id FROM allowed)"
            )
        }
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT rowid FROM vectors(:vector, '{K:100}') WHERE selected IN (SELECT id FROM allowed)",
                {"vector": vector},
            )
        }
        assert actual == expected
        connection.execute("DELETE FROM allowed")
        assert (
            connection.execute(
                "SELECT rowid FROM vectors(:vector, '{K:100}') WHERE selected IN (SELECT id FROM allowed)",
                {"vector": vector},
            ).fetchall()
            == []
        )


def test_exact_native_ranking_matches_independent_double_precision_oracle() -> None:
    generator = random.Random(17017)
    vectors = []
    for _ in range(400):
        values = tuple(generator.uniform(-1, 1) for _ in range(384))
        norm = math.sqrt(math.fsum(value * value for value in values))
        vectors.append(pack_vector(tuple(value / norm for value in values)))
    query = vectors[-1]
    query_values = struct.unpack("<384f", query)

    def score(vector: bytes) -> float:
        values = struct.unpack("<384f", vector)
        return math.fsum(
            left * right for left, right in zip(query_values, values, strict=True)
        ) / math.sqrt(
            math.fsum(value * value for value in values)
            * math.fsum(value * value for value in query_values)
        )

    expected = sorted(range(len(vectors)), key=lambda ordinal: -score(vectors[ordinal]))[:20]
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.enable_load_extension(False)
        load_vector_extension(connection)
        connection.execute("CREATE VIRTUAL TABLE vectors USING vec1(vector)")
        connection.execute(
            "INSERT INTO vectors(cmd,arg) VALUES('rebuild','{index:\"flat\",distance:\"cos\"}')"
        )
        connection.executemany(
            "INSERT INTO vectors(rowid,vector) VALUES (:rowid,:vector)",
            ({"rowid": rowid, "vector": vector} for rowid, vector in enumerate(vectors)),
        )
        actual = connection.execute(
            "SELECT rowid, distance FROM vectors(:query, '{K:20}')", {"query": query}
        ).fetchall()
        assert [row[0] for row in actual] == expected
        assert all(abs(1 - row[1] - score(vectors[row[0]])) < 0.000001 for row in actual)
        assert "single-threaded" in connection.execute("SELECT vec1_info()").fetchone()[0]
        with pytest.raises(sqlite3.OperationalError, match="not authorized"):
            connection.execute("SELECT load_extension('not-allowed')")


def test_native_integer_sets_compose_with_multiple_in_and_range_predicates() -> None:
    vector = struct.pack("<384f", 1.0, *([0.0] * 383))
    with closing(sqlite3.connect(":memory:")) as connection:
        load_vector_extension(connection)
        connection.execute("CREATE VIRTUAL TABLE vectors USING vec1(vector, first_key, second_key)")
        connection.execute(
            "INSERT INTO vectors(cmd,arg) VALUES('rebuild','{index:\"flat\",distance:\"cos\"}')"
        )
        connection.execute("CREATE TABLE ordinary (id INTEGER PRIMARY KEY, first_key, second_key)")
        for number in range(1, 65):
            values = {"id": number, "first_key": number % 5, "second_key": number % 7}
            connection.execute("INSERT INTO ordinary VALUES (:id,:first_key,:second_key)", values)
            connection.execute(
                "INSERT INTO vectors(rowid, first_key, second_key, vector) VALUES (:id,:first_key,:second_key,:vector)",
                {**values, "vector": vector},
            )
        condition = "first_key IN (1,3,4) AND second_key IN (2,3) AND first_key >= 2"
        expected = {
            row[0] for row in connection.execute("SELECT id FROM ordinary WHERE " + condition)
        }
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT rowid FROM vectors(:vector, '{K:100}') WHERE " + condition,
                {"vector": vector},
            )
        }
        assert actual == expected and expected


@pytest.mark.parametrize("initial", ("default", "disabled", "c_api", "sql_and_c_api"))
def test_native_loader_restores_the_callers_initial_configuration(initial: str) -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        if initial == "disabled":
            connection.enable_load_extension(False)
        elif initial == "c_api":
            connection.enable_load_extension(False)
            connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, True)
        elif initial == "sql_and_c_api":
            connection.enable_load_extension(True)
        enabled = connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
        with pytest.raises(sqlite3.OperationalError) as before:
            connection.execute("SELECT load_extension('not-allowed')")
        load_vector_extension(connection)
        assert connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION) == enabled
        with pytest.raises(sqlite3.OperationalError) as after:
            connection.execute("SELECT load_extension('not-allowed')")
        assert str(after.value) == str(before.value)
        load_vector_extension(connection)
        assert connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION) == enabled


def test_uncommitted_native_inserts_are_visible_and_rollback_keeps_earlier_rows() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        load_vector_extension(connection)
        connection.execute("CREATE VIRTUAL TABLE vectors USING vec1(vector)")
        connection.execute(
            "INSERT INTO vectors(cmd,arg) VALUES('rebuild','{index:\"flat\",distance:\"cos\"}')"
        )
        vector = struct.pack("<384f", 1.0, *([0.0] * 383))
        connection.execute(
            "INSERT INTO vectors(rowid,vector) VALUES(1,:vector)", {"vector": vector}
        )
        connection.commit()
        connection.execute("SAVEPOINT nested")
        connection.execute(
            "INSERT INTO vectors(rowid,vector) VALUES(2,:vector)", {"vector": vector}
        )
        assert {
            row[0]
            for row in connection.execute(
                "SELECT rowid FROM vectors(:vector, '{K:10}')", {"vector": vector}
            )
        } == {1, 2}
        connection.execute("ROLLBACK TO nested")
        connection.execute("RELEASE nested")
        assert {
            row[0]
            for row in connection.execute(
                "SELECT rowid FROM vectors(:vector, '{K:10}')", {"vector": vector}
            )
        } == {1}


@pytest.mark.parametrize("enabled", (False, True))
def test_failed_native_load_restores_c_api_and_never_enables_sql(
    tmp_path: Path, enabled: bool
) -> None:
    (tmp_path / "_vec1.so").write_bytes(b"Invalid native library")
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.enable_load_extension(False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, enabled)
        with (
            patch("toolsmith.semantic.vector.files", return_value=tmp_path),
            pytest.raises(ToolsmithError) as failure,
        ):
            load_vector_extension(connection)
        assert failure.value.failure.code == "unavailable"
        assert connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION) == enabled
        with pytest.raises(sqlite3.OperationalError, match="not authorized"):
            connection.execute("SELECT load_extension('not-allowed')")


@pytest.mark.parametrize(
    "observed",
    (
        "version 0.8 (AVX2, single-threaded)",
        "version 0.8 (AVX2, multi-threaded, toolsmith-native-1)",
        "version 0.7 (Scalar, single-threaded, toolsmith-native-1)",
    ),
)
def test_preloaded_extensions_without_the_owned_native_contract_are_rejected(observed: str) -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.create_function("vec1_info", 0, lambda: observed)
        with pytest.raises(ToolsmithError) as failure:
            load_vector_extension(connection)
        assert failure.value.failure.code == "unavailable"
