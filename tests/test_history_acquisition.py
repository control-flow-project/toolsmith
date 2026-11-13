"""Source-category contracts, not individual provider response simulations."""

import json
from datetime import date
from pathlib import Path

import pytest

from toolsmith.acquisition.history import (
    Acquisition,
    DateRange,
    NativeRequest,
    Record,
    Totals,
    calendar_months,
    decide,
    decode,
    frontier,
    inspect,
    pack,
    read_record,
    subtract,
    write_record,
)
from toolsmith.result import Failure, ToolsmithError, unwrap
from toolsmith.validation import canonical_json


def scope(first: str = "2026-10-01", last: str = "2026-10-31") -> DateRange:
    return DateRange(date.fromisoformat(first), date.fromisoformat(last))


def request(
    *, discovery: bool = False, due: bool = True, fresh_after: str | None = None
) -> NativeRequest:
    return NativeRequest(
        "native-key",
        "source",
        "item",
        {"url": "https://example.com/report.csv", "format": "csv"},
        scope(),
        discovery,
        due,
        fresh_after=fresh_after,
    )


def acquired(*, failed: bool = False, provisional: bool = False) -> Acquisition:
    if failed:
        return Acquisition(
            "native-key", "source", "item", "2026-11-01T00:00:00Z", "failed", reason="HTTP 500"
        )
    return Acquisition(
        "native-key",
        "source",
        "item",
        "2026-11-01T00:00:00Z",
        "provisional" if provisional else "complete",
        ("snapshot",),
        (scope(),),
        bytes=200,
        requests=1,
        elapsed_seconds=0.2,
    )


def test_overlap_holes_and_native_bulk() -> None:
    gaps = subtract(
        scope(),
        (
            scope("2026-10-05", "2026-10-07"),
            scope("2026-10-07", "2026-10-10"),
            scope("2026-09-01", "2026-10-02"),
        ),
    )
    assert gaps == (scope("2026-10-11", "2026-10-31"), scope("2026-10-03", "2026-10-04"))
    assert pack(scope(), gaps, maximum_days=15) == (
        scope("2026-10-17", "2026-10-31"),
        scope("2026-10-03", "2026-10-16"),
    )
    assert subtract(scope(), (scope(),)) == ()


def test_leap_month_and_shared_frontier() -> None:
    span = scope("2024-02-28", "2024-03-02")
    assert calendar_months(span) == (
        scope("2024-03-01", "2024-03-02"),
        scope("2024-02-28", "2024-02-29"),
    )
    assert calendar_months(span, whole=True)[1] == scope("2024-02-01", "2024-02-29")
    assert frontier(span, block_days=3) == (
        scope("2024-02-29", "2024-03-02"),
        scope("2024-02-28", "2024-02-28"),
    )


@pytest.mark.parametrize("format", ["json", "csv", "xml", "zip", "pdf", "xls"])
def test_transport_container_is_orthogonal(format: str) -> None:
    native = NativeRequest(
        "file-key",
        "publisher",
        "immutable-report",
        {"url": "https://example.com/report", "format": format},
    )
    assert decide(native, None).action == "download"
    assert (
        decide(
            native,
            Acquisition(
                "file-key",
                "publisher",
                "immutable-report",
                "2026-11-01T00:00:00Z",
                "complete",
                ("snapshot",),
            ),
        ).action
        == "reuse"
    )


def test_provisional_cutoff_and_failed_retry() -> None:
    assert decide(request(), acquired()).action == "reuse"
    assert (
        decide(request(fresh_after="2026-11-02T00:00:00+05:30"), acquired(provisional=True)).action
        == "refresh"
    )
    assert decide(request(), acquired(failed=True)).action == "download"
    assert decide(request(due=False), None).outcome == "not-yet-due"
    assert decide(request(), acquired(), retry=True).action == "refresh"


def test_discovery_unknown_count_and_bounded_readonly_inspection() -> None:
    pending = decide(request(discovery=True), None)
    report = inspect((pending, decide(request(), acquired())), limit=1)
    assert report["known_requests"] == 1
    assert report["additional_discovery_requests"] is None
    assert report["next_offset"] == 1
    entries = report["entries"]
    assert isinstance(entries, list) and len(entries) == 1
    canonical_json(report)


def test_identity_mismatch_rejected() -> None:
    with pytest.raises(ToolsmithError):
        decide(NativeRequest("different", "source", "item", {}), acquired())


def test_current_records_atomic_immutable_and_predecessor_rejection(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    record = Record("request", "native-key", {"scope": {"start": "2026-10-01"}, "snapshot": "same"})
    unwrap(write_record(path, record, immutable=True))
    unwrap(write_record(path, record, immutable=True))
    assert unwrap(read_record(path)) == record
    assert isinstance(
        write_record(path, Record("request", "native-key", {"changed": True}), immutable=True),
        Failure,
    )
    before = path.read_bytes()
    assert json.loads(before)["contract"] == "toolsmith.acquisition.history"
    with pytest.raises(ToolsmithError):
        decode(b'{"scope":"old bare format"}')
    changed = json.loads(before)
    changed["payload"]["snapshot"] = "different"
    with pytest.raises(ToolsmithError):
        decode(json.dumps(changed).encode())
    assert path.read_bytes() == before


def test_outcomes_account_without_hiding_unknown_measurements() -> None:
    totals = Totals()
    totals.add(decide(request(), None), acquired())
    totals.add(decide(request(), acquired()), None)
    totals.add(decide(request(), None), None)
    report = totals.report(wall_seconds=0.5)
    assert report["requests"] == 1 and report["reused"] == 1
    assert report["request_measurements_complete"] is False
    assert report["critical"] is True


def test_half_open_time_gaps_and_timezone_equivalence() -> None:
    from datetime import datetime

    from toolsmith.acquisition.history import TimeRange, pack_time, subtract_time

    def times(first: str, last: str) -> TimeRange:
        return TimeRange(datetime.fromisoformat(first), datetime.fromisoformat(last))

    whole = times("2026-11-12T09:00:00+05:30", "2026-11-12T12:00:00+05:30")
    covered = times("2026-11-12T03:30:00Z", "2026-11-12T04:30:00Z")
    gap = times("2026-11-12T10:00:00+05:30", "2026-11-12T12:00:00+05:30")
    assert subtract_time(whole, (covered,)) == (gap,)
    assert len(pack_time(whole, (gap,), maximum_seconds=3600)) == 2
    native = NativeRequest("time", "source", "item", {}, whole)
    acquired_time = Acquisition(
        "time", "source", "item", "2026-11-12T12:00:00+05:30", "complete", ("snapshot",), (covered,)
    )
    assert decide(native, acquired_time).missing == (gap,)
    with pytest.raises(ToolsmithError):
        decide(
            native,
            Acquisition(
                "time",
                "source",
                "item",
                "2026-11-12T12:00:00+05:30",
                "complete",
                ("snapshot",),
                (scope(),),
            ),
        )


def test_completed_enumeration_has_known_zero_additional_requests() -> None:
    from dataclasses import replace

    native = request(discovery=True)
    complete = replace(acquired(), discovery_complete=True)
    report = inspect((decide(native, complete),))
    assert report["known_requests"] == 0
    assert report["additional_discovery_requests"] == 0


def test_canonical_ledger_inputs_attempts_and_coverage(tmp_path: Path) -> None:
    from toolsmith.acquisition.history import Attempt, Coverage, Ledger

    root = tmp_path / "history"
    ledger = Ledger(root)
    value = acquired()
    unwrap(ledger.save(value))
    assert unwrap(ledger.lookup(value.source, value.item, value.identity)) == value
    assert unwrap(ledger.inputs(value.source, value.item)) == (value,)
    unwrap(ledger.cover(Coverage("source", "item", "window", scope(), {"originals": ["snapshot"]})))
    assert unwrap(ledger.coverage("source", "item"))[0].scope == scope()
    unwrap(
        ledger.attempt(
            Attempt(
                "native-key",
                "source",
                "item",
                "old",
                "2026-11-02T00:00:00Z",
                "discovery",
                "discovery-unknown",
                "Incomplete publisher index",
            )
        )
    )
    attempts = unwrap(ledger.attempts("source", "item", "native-key"))
    assert decide(request(), value, attempts=attempts, assignment="old").action == "reuse"
    assert decide(request(), value, attempts=attempts, assignment="new").action == "refresh"
    unwrap(
        ledger.attempt(
            Attempt(
                "native-key",
                "source",
                "item",
                "new",
                "2026-11-03T00:00:00Z",
                "discovery",
                "complete",
                "Enumerated",
            )
        )
    )
    assert (
        decide(
            request(),
            value,
            attempts=unwrap(ledger.attempts("source", "item", "native-key")),
            assignment="third",
        ).action
        == "reuse"
    )
    with pytest.raises(ToolsmithError):
        unwrap(ledger.save(acquired(failed=True)))


def test_shared_frontier_runs_fifteen_daily_files_with_one_bulk_request() -> None:
    import asyncio
    from datetime import timedelta

    from toolsmith.acquisition.history import Expansion, WorkItem, run_frontiers_async

    events: list[tuple[str, date]] = []
    whole = scope("2026-10-01", "2026-10-30")
    items = []
    for i in range(30):
        day = whole.start + timedelta(days=i)
        items.append(
            WorkItem(
                "day-" + str(day),
                "daily",
                NativeRequest(str(day), "daily", "file", {}, DateRange(day, day)),
                day,
            )
        )
    for i in (0, 15):
        first = whole.start + timedelta(days=i)
        last = first + timedelta(days=14)
        items.append(
            WorkItem(
                "bulk-" + str(last),
                "bulk",
                NativeRequest(str(last), "bulk", "range", {}, DateRange(first, last)),
                last,
            )
        )

    async def operation(batch: tuple[WorkItem[date], ...]) -> Expansion[date]:
        events.extend((value.group, value.payload) for value in batch)
        return Expansion()

    result = unwrap(asyncio.run(run_frontiers_async(tuple(items), operation, block_days=15)))
    assert result["handled_work"] == 32
    assert result["frontier_waves"] == 2
    first_old = next(i for i, (_, day) in enumerate(events) if day <= date(2026, 10, 15))
    assert first_old == 16
    assert sum(group == "daily" for group, _ in events[:16]) == 15
    assert sum(group == "bulk" for group, _ in events[:16]) == 1


def test_discovery_parent_withdraws_old_child_before_payload_execution() -> None:
    import asyncio

    from toolsmith.acquisition.history import Expansion, WorkItem, run_frontiers_async

    seen: list[str] = []
    parent = WorkItem("parent", "publisher", request(discovery=True), "parent")
    old = WorkItem("old", "publisher", request(), "old")
    child = WorkItem("child", "publisher", request(), "child")

    async def operation(batch: tuple[WorkItem[str], ...]) -> Expansion[str]:
        seen.extend(value.key for value in batch)
        return Expansion((child,), ("old",)) if batch[0].key == "parent" else Expansion()

    result = unwrap(asyncio.run(run_frontiers_async((old, parent), operation)))
    assert seen == ["parent", "child"]
    assert result["pending_work"] == 0


def test_interrupted_batch_leaves_exact_unhandled_work() -> None:
    import asyncio

    from toolsmith.acquisition.history import Expansion, WorkItem, run_frontiers_async

    a, b = WorkItem("a", "source", request(), "a"), WorkItem("b", "source", request(), "b")

    async def operation(batch: tuple[WorkItem[str], ...]) -> Expansion[str]:
        return Expansion(finished=(batch[0].key,), stop=True)

    result = unwrap(asyncio.run(run_frontiers_async((a, b), operation)))
    assert result["handled_work"] == 1 and result["pending_work"] == 1


def test_history_record_cli_uses_same_current_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from toolsmith.cli import main

    path = tmp_path / "record.json"
    unwrap(write_record(path, Record("input", "source/item/request", {"snapshot": "retained"})))
    before = {str(p): p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    assert main(["--json", "history", "record", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["value"] == {"snapshot": "retained"}
    assert {str(p): p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == before


def test_refresh_of_enumerated_index_has_unknown_new_children() -> None:
    from dataclasses import replace

    result = inspect(
        (
            decide(
                request(discovery=True), replace(acquired(), discovery_complete=True), refresh=True
            ),
        )
    )
    assert result["known_requests"] == 1
    assert result["additional_discovery_requests"] is None


def test_absolute_time_range_handles_repeated_dst_hour() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from toolsmith.acquisition.history import TimeRange

    zone = ZoneInfo("America/New_York")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    last = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
    selected = TimeRange(first, last)
    assert (selected.end - selected.start).total_seconds() == 3600


def test_gap_keeps_specific_failure_reason_and_deduplicates_native_requests() -> None:
    from toolsmith.acquisition.history import Attempt

    attempt = Attempt(
        "native-key",
        "source",
        "item",
        "old",
        "2026-11-02T00:00:00Z",
        "acquisition",
        "unavailable",
        "Publisher returned404",
    )
    decision = decide(request(), acquired(), attempts=(attempt,), assignment="new")
    assert decision.outcome == "unavailable"
    assert decision.reason == "Publisher returned404"
    assert inspect((decision, decision))["known_requests"] == 1


def test_packed_window_keeps_real_holes_and_reuses_different_native_captures() -> None:
    from toolsmith.acquisition.history import plan_windows

    completed = (scope("2026-10-05", "2026-10-10"), scope("2026-10-20", "2026-10-25"))
    plan = plan_windows(scope(), completed, maximum_days=31)[0]
    assert plan.native == scope()
    assert plan.missing == (
        scope("2026-10-26", "2026-10-31"),
        scope("2026-10-11", "2026-10-19"),
        scope("2026-10-01", "2026-10-04"),
    )
    native = NativeRequest("new-request", "source", "item", {}, scope(), expected=plan.missing)
    existing = Acquisition(
        "different-wider-native-request",
        "source",
        "item",
        "2026-11-01T00:00:00Z",
        "complete",
        ("snapshot",),
        (scope(),),
    )
    reused = decide(native, None, available=(existing,))
    assert reused.action == "reuse" and reused.retained is None
    assert reused.missing == ()
    assert inspect((reused,))["known_requests"] == 0
    assert decide(native, None, available=(existing,), refresh=True).action == "download"


def test_gap_observations_are_typed_persisted_and_only_report_unresolved_dates(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from toolsmith.acquisition.history import Gap, Ledger

    missing = scope("2026-10-31", "2026-10-31")
    original = replace(
        acquired(),
        complete=(scope("2026-10-01", "2026-10-30"),),
        unresolved=(Gap(missing, "unavailable", "Provider returned no observations"),),
    )
    ledger = Ledger(tmp_path / "ledger")
    unwrap(ledger.save(original))
    assert unwrap(ledger.lookup("source", "item", "native-key")) == original
    report = inspect((decide(request(), original, available=(original,)),))
    entries = report["entries"]
    assert isinstance(entries, list)
    row = entries[0]
    assert isinstance(row, dict)
    assert len(row["gap_observations"]) == 1
    assert row["gap_observations"][0]["outcome"] == "unavailable"
    canonical_json(report)


def test_frontier_callback_filesystem_failure_is_typed_and_preserves_handled_work() -> None:
    import asyncio

    from toolsmith.acquisition.history import Expansion, WorkItem, run_frontiers_async

    async def operation(batch: tuple[WorkItem[str], ...]) -> Expansion[str]:
        raise OSError("Controlled storage failure after original preservation")

    result = asyncio.run(
        run_frontiers_async((WorkItem("one", "source", request(), "one"),), operation)
    )
    assert isinstance(result, Failure)
    assert result.code == "io"


def test_frontier_without_progress_returns_a_failure_instead_of_spinning() -> None:
    import asyncio

    from toolsmith.acquisition.history import Expansion, WorkItem, run_frontiers_async

    async def operation(batch: tuple[WorkItem[str], ...]) -> Expansion[str]:
        return Expansion(finished=())

    result = asyncio.run(
        run_frontiers_async((WorkItem("one", "source", request(), "one"),), operation)
    )
    assert isinstance(result, Failure)
    assert result.code == "invalid_input"


def test_withdrawn_handled_work_has_separate_active_and_lifetime_counts() -> None:
    import asyncio

    from toolsmith.acquisition.history import Expansion, WorkItem, run_frontiers_async

    parent = WorkItem("parent", "publisher", request(discovery=True), "parent")
    child = WorkItem("child", "publisher", request(), "child")
    later = WorkItem("later", "publisher", request(discovery=True), "later")
    seen: list[str] = []

    async def operation(batch: tuple[WorkItem[str], ...]) -> Expansion[str]:
        seen.extend(value.key for value in batch)
        if batch[0].key == "parent":
            return Expansion(items=(child,))
        if batch[0].key == "child":
            return Expansion(items=(later,))
        return Expansion(withdraw=("child",))

    result = unwrap(asyncio.run(run_frontiers_async((parent,), operation)))
    assert seen == ["parent", "child", "later"]
    assert result["known_work"] == result["handled_work"] == 2
    assert result["handled_work_total"] == 3
    assert result["pending_work"] == 0
