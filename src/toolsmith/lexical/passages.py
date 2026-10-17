import re
from dataclasses import dataclass

from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer, text


@dataclass(frozen=True)
class Region:
    start: int
    end: int


@dataclass(frozen=True)
class Match:
    region: int
    match_start: int
    match_end: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class FindReport:
    matches: tuple[Match, ...]
    total: int
    truncated: bool


@boundary
def find_text(
    body: str,
    query: str,
    maximum_records: int = 20,
    *,
    case_sensitive: bool = False,
    before: int = 250,
    after: int = 350,
    regions: tuple[Region, ...] | None = None,
) -> FindReport:
    supplied = text(body, 128 * 1024 * 1024, "Source text", allow_empty=True)
    literal = text(query, 4096, "Literal query")
    maximum = integer(maximum_records, 1, 1000, "Maximum matches")
    leading, trailing = (
        integer(before, 0, 16384, "Leading context"),
        integer(after, 0, 16384, "Trailing context"),
    )
    if not isinstance(case_sensitive, bool):
        raise ToolsmithError("invalid_input", "Case sensitivity must be Boolean")
    selected = (Region(0, len(supplied)),) if regions is None else regions
    if not isinstance(selected, tuple):
        raise ToolsmithError("invalid_input", "Supply explicit text regions")
    end_previous = 0
    for region in selected:
        if not isinstance(region, Region):
            raise ToolsmithError("invalid_input", "Supply typed source regions")
        start = integer(region.start, end_previous, len(supplied), "Region start")
        end_previous = integer(region.end, start, len(supplied), "Region end")
    pattern = re.compile(re.escape(literal), 0 if case_sensitive else re.IGNORECASE)
    matches: list[Match] = []
    total = 0
    for ordinal, region in enumerate(selected):
        for match in pattern.finditer(supplied, region.start, region.end):
            total += 1
            if len(matches) < maximum:
                start = max(region.start, match.start() - leading)
                end = min(region.end, match.end() + trailing)
                matches.append(
                    Match(ordinal, match.start(), match.end(), start, end, supplied[start:end])
                )
    return FindReport(tuple(matches), total, total > maximum)
