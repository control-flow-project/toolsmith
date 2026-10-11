import re
from dataclasses import dataclass
from pathlib import Path

from toolsmith.result import ToolsmithError, boundary
from toolsmith.storage.database import open_store, row_integer, row_optional_text, row_text
from toolsmith.validation import digest, integer, parse_json, text


@dataclass(frozen=True)
class Citation:
    collection: str
    item: str
    version: str
    part: int
    physical_page: int | None
    start: int
    end: int
    text: str
    title: str
    method: str
    source_url: str | None
    published_at: str | None
    observed_at: str | None
    recorded_at: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SearchHit:
    collection: str
    item: str
    version: str
    part: int
    physical_page: int | None
    start: int
    end: int
    text: str
    title: str
    rank: float


@boundary
def read_citation(
    root: Path, collection: str, version: str, part: int, start: int = 0, length: int = 1200
) -> Citation:
    selected = digest(version, "Text version")
    ordinal = integer(part, 1, 1000, "Part")
    offset = integer(start, 0, 4 * 1024 * 1024, "Start character")
    maximum = integer(length, 1, 16_384, "Character count")
    with open_store(root, collection) as store:
        row = store.connection.execute(
            "SELECT v.*, p.ordinal, p.physical_page, p.text, p.warnings FROM text_version v JOIN part p ON p.version_id = v.id WHERE v.id = ? AND p.ordinal = ?",
            (selected, ordinal),
        ).fetchone()
        if row is None:
            raise ToolsmithError("not_found", "Exact citation version and part were not found")
        body = row_text(row, "text", 4 * 1024 * 1024)
        if offset > len(body):
            raise ToolsmithError("invalid_input", "Citation starts beyond the retained part")
        warnings = parse_json(row_text(row, "warnings", 65_536).encode())
        if not isinstance(warnings, list) or not all(isinstance(value, str) for value in warnings):
            raise ToolsmithError("integrity", "Stored citation warnings are invalid")
        page = row["physical_page"]
        return Citation(
            store.collection,
            row_text(row, "item_id"),
            selected,
            ordinal,
            None if page is None else integer(page, 1, 1_000_000, "Physical page"),
            offset,
            min(offset + maximum, len(body)),
            body[offset : offset + maximum],
            row_text(row, "title"),
            row_text(row, "method"),
            row_optional_text(row, "source_url"),
            row_optional_text(row, "published_at"),
            row_optional_text(row, "observed_at"),
            row_text(row, "recorded_at"),
            tuple(text(value, 1024, "Warning") for value in warnings),
        )


@boundary
def search_text(
    root: Path, collection: str, query: str, maximum_records: int = 20, offset: int = 0
) -> tuple[SearchHit, ...]:
    selected = text(query, 2048, "Search query")
    tokens = re.findall(r"[^\W_]+", selected, flags=re.UNICODE)
    if not tokens or len(tokens) > 32:
        raise ToolsmithError("invalid_input", "Lexical queries require one to 32 literal terms")
    expression = " AND ".join('"' + token + '"' for token in tokens)
    maximum = integer(maximum_records, 1, 100, "Maximum records")
    start = integer(offset, 0, 1_000_000, "Offset")
    with open_store(root, collection) as store:
        rows = store.connection.execute(
            "SELECT v.item_id, v.id AS version, v.title, p.ordinal, p.physical_page, c.start_offset, c.end_offset, c.text, bm25(chunk_search) AS rank FROM chunk_search JOIN chunk c ON c.id = chunk_search.rowid JOIN part p ON p.id = c.part_id JOIN text_version v ON v.id = p.version_id JOIN item i ON i.latest_version = v.id WHERE chunk_search MATCH ? ORDER BY rank, v.id, p.ordinal, c.start_offset LIMIT ? OFFSET ?",
            (expression, maximum, start),
        ).fetchall()
        return tuple(
            SearchHit(
                store.collection,
                row_text(row, "item_id"),
                row_text(row, "version"),
                row_integer(row, "ordinal"),
                None
                if row["physical_page"] is None
                else integer(row["physical_page"], 1, 1_000_000, "Physical page"),
                row_integer(row, "start_offset"),
                row_integer(row, "end_offset"),
                row_text(row, "text", 8192),
                row_text(row, "title"),
                float(row["rank"]),
            )
            for row in rows
        )
