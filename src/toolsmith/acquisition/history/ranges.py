"""Inclusive calendar coverage and native request packing, without I/O."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from toolsmith.result import ToolsmithError
from toolsmith.validation import integer


@dataclass(frozen=True, order=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if type(self.start) is not date or type(self.end) is not date or self.end < self.start:
            raise ToolsmithError("invalid_input", "Select an ordered pair of calendar dates")

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


def subtract(scope: DateRange, covered: tuple[DateRange, ...]) -> tuple[DateRange, ...]:
    """Newest-first disjoint gaps; clipping/overlap never invents completion."""
    if not isinstance(scope, DateRange) or not isinstance(covered, tuple):
        raise ToolsmithError("invalid_input", "Supply a range and tuple of completed ranges")
    if any(not isinstance(span, DateRange) for span in covered):
        raise ToolsmithError("invalid_input", "Coverage must contain typed ranges")
    missing = [scope]
    for span in sorted(covered):
        remaining = []
        for gap in missing:
            if span.end < gap.start or span.start > gap.end:
                remaining.append(gap)
                continue
            if gap.start < span.start:
                remaining.append(DateRange(gap.start, span.start - timedelta(days=1)))
            if span.end < gap.end:
                remaining.append(DateRange(span.end + timedelta(days=1), gap.end))
        missing = remaining
    return tuple(reversed(missing))


def dates(scope: DateRange) -> tuple[date, ...]:
    if not isinstance(scope, DateRange):
        raise ToolsmithError("invalid_input", "Supply typed calendar coverage")
    return tuple(scope.start + timedelta(days=i) for i in range((scope.end - scope.start).days + 1))


def pack(
    scope: DateRange,
    missing: tuple[DateRange, ...],
    *,
    maximum_days: int,
    anchor: Literal["start", "end"] = "end",
) -> tuple[DateRange, ...]:
    """Fewest bounded requests, newest first, with covered edges trimmed.

    Interior completed dates may be bridged to save requests. A native adapter
    can instead use calendar_months for indivisible monthly publisher files.
    """
    maximum = integer(maximum_days, 1, 36500, "Native request days")
    if (
        not isinstance(scope, DateRange)
        or not isinstance(missing, tuple)
        or any(not isinstance(span, DateRange) for span in missing)
    ):
        raise ToolsmithError("invalid_input", "Supply typed request scope and missing ranges")
    if anchor not in {"start", "end"}:
        raise ToolsmithError("invalid_input", "Choose the native start or end request anchor")
    if anchor == "start":

        def mirror(day: date) -> date:
            return date.fromordinal(date.max.toordinal() + 1 - day.toordinal())

        flipped = DateRange(mirror(scope.end), mirror(scope.start))
        spans = tuple(DateRange(mirror(v.end), mirror(v.start)) for v in missing)
        packed = pack(flipped, spans, maximum_days=maximum)
        return tuple(reversed(tuple(DateRange(mirror(v.end), mirror(v.start)) for v in packed)))
    pending = sorted(
        DateRange(max(scope.start, gap.start), min(scope.end, gap.end))
        for gap in missing
        if gap.end >= scope.start and gap.start <= scope.end
    )
    output = []
    while pending:
        last = pending[-1].end
        first = max(scope.start, last - timedelta(days=maximum - 1))
        selected = [gap for gap in pending if gap.end >= first]
        actual_first = max(first, selected[0].start)
        output.append(DateRange(actual_first, last))
        left = []
        for gap in pending:
            if gap.start >= actual_first:
                continue
            left.append(DateRange(gap.start, min(gap.end, actual_first - timedelta(days=1))))
        pending = left
    return tuple(output)


def calendar_months(scope: DateRange, *, whole: bool = False) -> tuple[DateRange, ...]:
    if not isinstance(scope, DateRange) or type(whole) is not bool:
        raise ToolsmithError("invalid_input", "Whole native month intent must be Boolean")
    output = []
    until = scope.end
    while until >= scope.start:
        first = until.replace(day=1)
        output.append(
            DateRange(
                first if whole else max(first, scope.start),
                until.replace(day=monthrange(until.year, until.month)[1]) if whole else until,
            )
        )
        if first == date.min:
            break
        until = first - timedelta(days=1)
    return tuple(output)


def frontier(scope: DateRange, *, block_days: int) -> tuple[DateRange, ...]:
    """Shared backward coordination blocks; never a provider request-size limit."""
    return pack(scope, (scope,), maximum_days=block_days)


@dataclass(frozen=True, order=True)
class TimeRange:
    """Half-open absolute-time coverage [start,end); timezone-aware throughout."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.start, datetime)
            or not isinstance(self.end, datetime)
            or self.start.utcoffset() is None
            or self.end.utcoffset() is None
        ):
            raise ToolsmithError("invalid_input", "Time ranges require ordered aware instants")
        object.__setattr__(self, "start", self.start.astimezone(UTC))
        object.__setattr__(self, "end", self.end.astimezone(UTC))
        if self.start >= self.end:
            raise ToolsmithError(
                "invalid_input", "Time ranges require increasing absolute instants"
            )


def subtract_time(scope: TimeRange, covered: tuple[TimeRange, ...]) -> tuple[TimeRange, ...]:
    if (
        not isinstance(scope, TimeRange)
        or not isinstance(covered, tuple)
        or any(not isinstance(v, TimeRange) for v in covered)
    ):
        raise ToolsmithError("invalid_input", "Supply typed half-open time coverage")
    missing = [scope]
    for span in sorted(covered):
        remaining = []
        for gap in missing:
            if span.end <= gap.start or span.start >= gap.end:
                remaining.append(gap)
            else:
                if gap.start < span.start:
                    remaining.append(TimeRange(gap.start, span.start))
                if span.end < gap.end:
                    remaining.append(TimeRange(span.end, gap.end))
        missing = remaining
    return tuple(reversed(missing))


def pack_time(
    scope: TimeRange, missing: tuple[TimeRange, ...], *, maximum_seconds: float
) -> tuple[TimeRange, ...]:
    from toolsmith.validation import number

    seconds = number(maximum_seconds, 0.000001, 36500 * 86400, "Native request seconds")
    if (
        not isinstance(scope, TimeRange)
        or not isinstance(missing, tuple)
        or any(not isinstance(v, TimeRange) for v in missing)
    ):
        raise ToolsmithError("invalid_input", "Supply typed half-open time gaps")
    pending = sorted(
        TimeRange(max(scope.start, v.start), min(scope.end, v.end))
        for v in missing
        if v.end > scope.start and v.start < scope.end
    )
    result = []
    while pending:
        last = pending[-1].end
        first = max(scope.start, last - timedelta(seconds=seconds))
        selected = [v for v in pending if v.end > first]
        actual = max(first, selected[0].start)
        result.append(TimeRange(actual, last))
        pending = [TimeRange(v.start, min(v.end, actual)) for v in pending if v.start < actual]
    return tuple(result)


@dataclass(frozen=True)
class WindowPlan:
    native: DateRange
    missing: tuple[DateRange, ...]


def plan_windows(
    scope: DateRange,
    covered: tuple[DateRange, ...],
    *,
    maximum_days: int,
    anchor: Literal["start", "end"] = "end",
) -> tuple[WindowPlan, ...]:
    gaps = subtract(scope, covered)
    result = []
    for native in pack(scope, gaps, maximum_days=maximum_days, anchor=anchor):
        missing = tuple(
            DateRange(max(native.start, v.start), min(native.end, v.end))
            for v in gaps
            if v.end >= native.start and v.start <= native.end
        )
        result.append(WindowPlan(native, missing))
    return tuple(result)
