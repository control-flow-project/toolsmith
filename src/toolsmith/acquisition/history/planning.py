"""The single reuse decision used by execution and read-only inspection."""

from datetime import datetime

from toolsmith.result import ToolsmithError

from .contracts import Acquisition, Action, Decision, NativeRequest
from .ledger import Attempt
from .ranges import DateRange, TimeRange, subtract, subtract_time


def decide(
    request: NativeRequest,
    retained: Acquisition | None,
    *,
    refresh: bool = False,
    retry: bool = False,
    attempts: tuple[Attempt, ...] = (),
    assignment: str | None = None,
    available: tuple[Acquisition, ...] = (),
) -> Decision:
    if (
        not isinstance(request, NativeRequest)
        or type(refresh) is not bool
        or type(retry) is not bool
    ):
        raise ToolsmithError(
            "invalid_input", "Supply a typed request and Boolean refresh/retry intent"
        )
    if retained is not None and (
        not isinstance(retained, Acquisition)
        or (request.identity, request.source, request.item)
        != (retained.identity, retained.source, retained.item)
    ):
        raise ToolsmithError(
            "integrity", "Retained acquisition differs from the exact native input"
        )
    latest: Attempt | None = None
    if attempts:
        if assignment is None or any(
            (value.identity, value.source, value.item)
            != (request.identity, request.source, request.item)
            for value in attempts
        ):
            raise ToolsmithError(
                "integrity", "Retry attempts differ from this assignment/native request"
            )
        latest = max(attempts, key=lambda v: datetime.fromisoformat(v.observed_at))
        retry |= (
            latest.assignment != assignment
            and latest.outcome != "complete"
            and (
                retained is None
                or datetime.fromisoformat(latest.observed_at)
                >= datetime.fromisoformat(retained.observed_at)
            )
        )
    if (
        refresh
        and retained is not None
        and assignment is not None
        and retained.assignment == assignment
    ):
        refresh = False
    if not isinstance(available, tuple) or any(
        not isinstance(v, Acquisition) or (v.source, v.item) != (request.source, request.item)
        for v in available
    ):
        raise ToolsmithError(
            "integrity", "Coverage originals differ from their selected source/item"
        )
    covered = tuple(span for value in available for span in value.complete) + (
        () if retained is None else retained.complete
    )
    extents = (
        (() if request.scope is None else (request.scope,))
        if request.expected is None
        else request.expected
    )
    gaps: tuple[DateRange | TimeRange, ...] = ()
    for extent in extents:
        if isinstance(extent, DateRange):
            if any(not isinstance(v, DateRange) for v in covered):
                raise ToolsmithError(
                    "integrity", "Calendar coverage cannot substitute for time coverage"
                )
            gaps += subtract(extent, tuple(v for v in covered if isinstance(v, DateRange)))
        else:
            if any(not isinstance(v, TimeRange) for v in covered):
                raise ToolsmithError(
                    "integrity", "Time coverage cannot substitute for calendar coverage"
                )
            gaps += subtract_time(extent, tuple(v for v in covered if isinstance(v, TimeRange)))
    if not request.due:
        return Decision(
            request, "blocked", "not-yet-due", request.reason or "Not yet published", retained, gaps
        )
    if request.scope is not None and not gaps and available and not refresh and not retry:
        return Decision(
            request,
            "reuse",
            "complete",
            "Requested gaps are covered by retained native originals",
            retained,
            gaps,
            available,
        )
    if retained is not None and not refresh and not retry:
        fresh = request.fresh_after is None or datetime.fromisoformat(
            retained.observed_at
        ) >= datetime.fromisoformat(request.fresh_after)
        if fresh and retained.outcome in {"complete", "provisional"} and retained.originals:
            # Exact retained response can be reused even where it does not prove
            # exhaustive historical coverage. That distinction remains in gaps.
            return Decision(
                request,
                "reuse",
                retained.outcome,
                "Retained native original",
                retained,
                gaps,
                available,
            )
    outcome = "missing" if retained is None else retained.outcome
    if latest is not None and latest.outcome != "complete":
        outcome = latest.outcome
    action: Action = "discover" if request.discovery else "download"
    reason = request.reason or (
        "No retained native original" if retained is None else "Refresh retained native observation"
    )
    if retry and latest is not None:
        reason = latest.reason
    if retained is not None and (refresh or retry or request.fresh_after is not None):
        action = "refresh"
    return Decision(request, action, outcome, reason, retained, gaps, available)


def inspect(
    decisions: tuple[Decision, ...], *, limit: int = 100, offset: int = 0
) -> dict[str, object]:
    from dataclasses import asdict

    from toolsmith.validation import integer

    integer(limit, 1, 1000, "Inspection page size")
    integer(offset, 0, 2**63 - 1, "Inspection offset")
    if not isinstance(decisions, tuple) or any(
        not isinstance(value, Decision) for value in decisions
    ):
        raise ToolsmithError("invalid_input", "Supply typed acquisition decisions")
    rows = []
    counts: dict[str, int] = {}
    for position, value in enumerate(decisions):
        counts[value.action] = counts.get(value.action, 0) + 1
        if offset <= position < offset + limit:
            row = asdict(value)
            observations = []
            unique = {
                (v.source, v.item, v.identity, v.observed_at, v.originals): v
                for v in (*value.available, *(() if value.retained is None else (value.retained,)))
            }
            for original in sorted(
                unique.values(), key=lambda v: datetime.fromisoformat(v.observed_at), reverse=True
            ):
                for gap in original.unresolved:
                    if gap.scope is not None and not any(
                        isinstance(v, type(gap.scope))
                        and v.start <= gap.scope.end
                        and v.end >= gap.scope.start
                        for v in value.missing
                    ):
                        continue
                    observations.append(
                        {
                            "scope": None
                            if gap.scope is None
                            else {
                                "start": gap.scope.start.isoformat(),
                                "end": gap.scope.end.isoformat(),
                            },
                            "outcome": gap.outcome,
                            "reason": gap.reason,
                            "observed_at": original.observed_at,
                            "originals": list(original.originals),
                        }
                    )
            row["gap_observations"] = observations

            row["available"] = [
                {
                    "identity": v.identity,
                    "source": v.source,
                    "item": v.item,
                    "originals": list(v.originals),
                    "complete": [
                        {"start": span.start.isoformat(), "end": span.end.isoformat()}
                        for span in v.complete
                    ],
                }
                for v in value.available
            ]
            native = row["request"]
            native["expected"] = (
                None
                if value.request.expected is None
                else [
                    {"start": span.start.isoformat(), "end": span.end.isoformat()}
                    for span in value.request.expected
                ]
            )
            native["scope"] = (
                None
                if value.request.scope is None
                else {"start": str(value.request.scope.start), "end": str(value.request.scope.end)}
            )
            row["missing"] = [
                {"start": str(gap.start), "end": str(gap.end)} for gap in value.missing
            ]
            if value.retained is not None:
                row["retained"]["unresolved"] = [
                    {
                        "scope": None
                        if gap.scope is None
                        else {
                            "start": gap.scope.start.isoformat(),
                            "end": gap.scope.end.isoformat(),
                        },
                        "outcome": gap.outcome,
                        "reason": gap.reason,
                    }
                    for gap in value.retained.unresolved
                ]
                row["retained"]["complete"] = [
                    {"start": str(gap.start), "end": str(gap.end)}
                    for gap in value.retained.complete
                ]
                row["retained"]["provisional"] = [
                    {"start": str(gap.start), "end": str(gap.end)}
                    for gap in value.retained.provisional
                ]
            rows.append(row)
    return {
        "total": len(decisions),
        "actions": counts,
        "known_requests": len(
            {
                (
                    value.request.source,
                    value.request.item,
                    value.request.identity,
                    value.request.fresh_after,
                )
                for value in decisions
                if value.action not in {"reuse", "blocked"}
            }
        ),
        "additional_discovery_requests": None
        if any(
            value.request.discovery
            and value.action != "blocked"
            and not (
                value.action == "reuse"
                and value.retained is not None
                and value.retained.discovery_complete
            )
            for value in decisions
        )
        else 0,
        "entries": rows,
        "next_offset": offset + limit if offset + limit < len(decisions) else None,
    }
