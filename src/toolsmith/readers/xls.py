"""Explicit, in-process BIFF workbook reading; no display-value inference."""

import io
import math
import struct
from dataclasses import dataclass
from decimal import Decimal
from importlib import import_module
from typing import Literal, Protocol, cast

from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer

MAXIMUM_XLS_BYTES = 32 * 1024 * 1024
type XlsCellKind = Literal["empty", "text", "number", "date", "boolean", "error", "blank"]


class Cell(Protocol):
    ctype: int
    value: object
    xf_index: int


class Format(Protocol):
    format_str: str


class ExtendedFormat(Protocol):
    format_key: int


class Sheet(Protocol):
    name: str
    nrows: int
    ncols: int
    merged_cells: list[tuple[int, int, int, int]]

    def cell(self, row: int, column: int) -> Cell: ...


class Book(Protocol):
    nsheets: int
    datemode: int
    xf_list: list[ExtendedFormat]
    format_map: dict[int, Format]

    def sheet_names(self) -> list[str]: ...
    def sheet_by_index(self, index: int) -> Sheet: ...
    def release_resources(self) -> None: ...


class CompoundErrors(Protocol):
    CompDocError: type[Exception]


class Backend(Protocol):
    compdoc: CompoundErrors
    XLRDError: type[Exception]

    def open_workbook(
        self,
        *,
        file_contents: bytes,
        logfile: io.StringIO,
        formatting_info: bool,
        on_demand: bool,
        use_mmap: bool,
    ) -> Book: ...


@dataclass(frozen=True)
class XlsCell:
    kind: XlsCellKind
    value: str | bool | int | None
    number_format: str


@dataclass(frozen=True)
class XlsSheet:
    sheet_names: tuple[str, ...]
    sheet: int
    name: str
    date_mode: int
    total_rows: int
    total_columns: int
    start: int
    rows: tuple[tuple[XlsCell, ...], ...]
    next_row: int | None
    merged_cells: tuple[tuple[int, int, int, int], ...]


def read_cell(cell: Cell, book: Book) -> XlsCell:
    kinds: tuple[XlsCellKind, ...] = (
        "empty",
        "text",
        "number",
        "date",
        "boolean",
        "error",
        "blank",
    )
    if cell.ctype not in range(len(kinds)):
        raise ToolsmithError("invalid_input", "Workbook has an unknown cell type")
    kind = kinds[cell.ctype]
    value = cell.value
    if kind in {"empty", "blank"}:
        selected: str | bool | int | None = None
    elif kind == "text" and isinstance(value, str):
        selected = value
    elif kind in {"number", "date"} and isinstance(value, float) and math.isfinite(value):
        # Exact stored binary64, deliberately not a rounded/displayed decimal.
        selected = str(Decimal.from_float(value))
    elif kind == "boolean" and isinstance(value, int) and value in {0, 1}:
        selected = bool(value)
    elif kind == "error" and isinstance(value, int):
        selected = value
    else:
        raise ToolsmithError("invalid_input", "Workbook has an invalid typed cell value")
    try:
        number_format = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
    except (IndexError, KeyError) as error:
        raise ToolsmithError("invalid_input", "Workbook has an invalid cell format") from error
    return XlsCell(kind, selected, number_format)


@boundary
def read_xls(
    content: bytes,
    sheet: int = 0,
    start: int = 0,
    limit: int = 1000,
    *,
    maximum_cells: int = 100_000,
    maximum_text_bytes: int = 4 * 1024 * 1024,
) -> XlsSheet:
    """Read a bounded row page, retaining source formats and exact binary numbers.

    Date values remain serials with the workbook's date mode. Formula results are
    the stored cached values; formulas are neither extracted nor recalculated.
    """
    if not isinstance(content, bytes) or not content:
        raise ToolsmithError("invalid_input", "XLS input must be nonempty bytes")
    if len(content) > MAXIMUM_XLS_BYTES:
        raise ToolsmithError("limit", "XLS input exceeds the 32 MiB limit")
    if not content.startswith(
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", b"\x09\x00", b"\x09\x02", b"\x09\x04", b"\x09\x08")
    ):
        raise ToolsmithError("invalid_input", "Input has no OLE/BIFF workbook header")
    number = integer(sheet, 0, 65535, "Workbook sheet")
    first = integer(start, 0, 65535, "First XLS row")
    count = integer(limit, 1, 65536, "XLS rows per read")
    cells = integer(maximum_cells, 1, 16_777_216, "XLS output cells")
    text_bytes = integer(maximum_text_bytes, 1, 32 * 1024 * 1024, "XLS output text bytes")
    try:
        backend = cast(Backend, import_module("xlrd"))
    except ImportError as error:
        raise ToolsmithError(
            "unavailable", "XLS reading requires the optional xls dependency"
        ) from error
    book: Book | None = None
    try:
        book = backend.open_workbook(
            file_contents=content,
            logfile=io.StringIO(),
            formatting_info=True,
            on_demand=True,
            use_mmap=False,
        )
        if number >= book.nsheets:
            raise ToolsmithError("invalid_input", "Requested XLS sheet is outside the workbook")
        selected = book.sheet_by_index(number)
        if first >= selected.nrows and (first != 0 or selected.nrows != 0):
            raise ToolsmithError("invalid_input", "Requested XLS row is outside the sheet")
        end = min(selected.nrows, first + count)
        if (end - first) * selected.ncols > cells:
            raise ToolsmithError(
                "limit", "Selected XLS rows exceed the cell budget; read fewer rows"
            )
        rows: list[tuple[XlsCell, ...]] = []
        used = 0
        for row in range(first, end):
            values = tuple(
                read_cell(selected.cell(row, column), book) for column in range(selected.ncols)
            )
            used += sum(
                len((str(value.value) + value.number_format).encode("utf-8")) for value in values
            )
            if used > text_bytes:
                raise ToolsmithError(
                    "limit", "Selected XLS rows exceed the text budget; read fewer rows"
                )
            rows.append(values)
        return XlsSheet(
            tuple(book.sheet_names()),
            number,
            selected.name,
            book.datemode,
            selected.nrows,
            selected.ncols,
            first,
            tuple(rows),
            end if end < selected.nrows else None,
            tuple(selected.merged_cells),
        )
    except (
        backend.XLRDError,
        backend.compdoc.CompDocError,
        struct.error,
        ValueError,
        IndexError,
        KeyError,
        EOFError,
        UnicodeError,
    ) as error:
        raise ToolsmithError(
            "invalid_input", "XLS workbook cannot be read or requires a password"
        ) from error
    finally:
        if book is not None:
            book.release_resources()
