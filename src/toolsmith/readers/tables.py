import csv
import io
import stat
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from toolsmith.compression import expand_gzip
from toolsmith.readers.text import decode_text
from toolsmith.result import Result, Success, ToolsmithError, boundary, unwrap
from toolsmith.validation import integer, text

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
type TableFormat = Literal["csv", "zip-csv", "gzip-csv"]


@dataclass(frozen=True)
class Projection:
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    scanned: int
    matched: int
    truncated: bool


@boundary
def decode_table(content: bytes, format_name: TableFormat = "csv") -> str:
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_INPUT_BYTES:
        raise ToolsmithError("limit", "Table input must contain 1 byte through 32 MiB")
    expanded = content
    try:
        if format_name == "zip-csv":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) != 1:
                    raise ToolsmithError("invalid_input", "Select a ZIP with exactly one CSV file")
                member = members[0]
                mode = member.external_attr >> 16
                if (
                    member.is_dir()
                    or "/" in member.filename
                    or "\\" in member.filename
                    or not member.filename.lower().endswith(".csv")
                    or member.flag_bits & 1
                    or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                    or any(
                        ord(character) < 32 or ord(character) == 127
                        for character in member.filename
                    )
                    or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or member.file_size > MAX_EXPANDED_BYTES
                ):
                    raise ToolsmithError("denied", "CSV archive contains an unsafe member")
                with archive.open(member) as stream:
                    expanded = stream.read(MAX_EXPANDED_BYTES + 1)
        elif format_name == "gzip-csv":
            expanded = unwrap(expand_gzip(content, MAX_EXPANDED_BYTES))
        elif format_name != "csv":
            raise ToolsmithError("invalid_input", "Choose csv, zip-csv or gzip-csv")
        output = decode_text(expanded, MAX_EXPANDED_BYTES)
        if output.lstrip().lower().startswith(("<html", "<!doctype html")):
            raise ToolsmithError("invalid_input", "Response contains HTML, not CSV data")
        return output
    except (
        ValueError,
        zipfile.BadZipFile,
        EOFError,
        NotImplementedError,
        RuntimeError,
    ) as error:
        raise ToolsmithError("invalid_input", "CSV archive is malformed") from error


def validated_rows(
    body: str, header_row: int, required_columns: tuple[str, ...], maximum_rows: int
) -> Iterator[dict[str, str]]:
    text(body, MAX_EXPANDED_BYTES, "Table text")
    ordinal = integer(header_row, 1, 2**63 - 1, "Header row")
    maximum = integer(maximum_rows, 1, 2**63 - 1, "Maximum rows")
    if not isinstance(required_columns, tuple) or len(required_columns) > 256:
        raise ToolsmithError("invalid_input", "Supply bounded required column names")
    for name in required_columns:
        text(name, 1024, "Column name")
    stream = io.StringIO(body)
    for _ in range(ordinal - 1):
        if not stream.readline():
            raise ToolsmithError("invalid_input", "Header row is beyond the table")
    beginning = stream.tell()
    sample = stream.read(4096)
    stream.seek(beginning)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",|\t")
        reader = csv.DictReader(stream, dialect=dialect, strict=True)
        headers = reader.fieldnames
        if (
            not headers
            or len(headers) > 256
            or len(set(headers)) != len(headers)
            or any(not name.strip() or len(name.encode()) > 1024 for name in headers)
        ):
            raise ToolsmithError(
                "invalid_input", "Table headers are missing, duplicate or excessive"
            )
        if any(name not in headers for name in required_columns):
            raise ToolsmithError("not_found", "Requested column is absent from the table")
        for number, row in enumerate(reader, 1):
            if number > maximum:
                raise ToolsmithError("limit", "Table exceeds its explicit row budget")
            if None in row or any(value is None for value in row.values()):
                raise ToolsmithError("invalid_input", "CSV row does not match the header width")
            yield {
                key: value for key, value in row.items() if key is not None and value is not None
            }
    except csv.Error as error:
        raise ToolsmithError("invalid_input", "CSV delimiter, field or row is malformed") from error


def iter_table_rows(
    body: str,
    *,
    header_row: int = 1,
    required_columns: tuple[str, ...] = (),
    maximum_rows: int = 1_000_000,
) -> Iterator[Result[dict[str, str]]]:
    try:
        for row in validated_rows(body, header_row, required_columns, maximum_rows):
            yield Success(row)
    except ToolsmithError as error:
        yield error.failure


@boundary
def project_table(
    body: str,
    columns: tuple[str, ...],
    filters: dict[str, str],
    maximum_records: int = 20,
    *,
    header_row: int = 1,
    maximum_rows: int = 1_000_000,
) -> Projection:
    maximum = integer(maximum_records, 1, 1000, "Maximum records")
    if (
        not isinstance(columns, tuple)
        or not all(isinstance(column, str) for column in columns)
        or not 1 <= len(columns) <= 256
        or len(set(columns)) != len(columns)
    ):
        raise ToolsmithError("invalid_input", "Supply distinct bounded projection columns")
    if not isinstance(filters, dict) or len(filters) > 256:
        raise ToolsmithError("invalid_input", "Supply bounded exact-match filters")
    for key, value in filters.items():
        text(key, 1024, "Filter column")
        text(value, 65536, "Filter value", allow_empty=True)
    selected: list[dict[str, str]] = []
    matched, scanned = 0, 0
    for row in validated_rows(
        body, header_row, tuple(dict.fromkeys((*columns, *filters))), maximum_rows
    ):
        scanned += 1
        if all(row[key].strip() == value for key, value in filters.items()):
            matched += 1
            if len(selected) < maximum:
                selected.append({column: row[column] for column in columns})
    return Projection(columns, tuple(selected), scanned, matched, matched > maximum)
