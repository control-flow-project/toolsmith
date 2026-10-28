import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import ControlledClock
from test_http import FixedResolver, RecordedTransport, plain

from toolsmith.acquisition.budget_import import BudgetSnapshot, GroupUsage, Usage, import_budget
from toolsmith.acquisition.budgets import (
    BudgetPolicy,
    inspect_budget,
    reserve_budget,
    reserve_budget_async,
    settle_budget,
)
from toolsmith.acquisition.client import HttpPolicy, fetch_http
from toolsmith.acquisition.transport import Response
from toolsmith.result import Failure, ToolsmithError, unwrap


def policy(group: str = "source") -> BudgetPolicy:
    return BudgetPolicy(group, 60, 10, 1000, 3, 300)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_active_reservation_covers_the_actual_operation_deadline_without_refunding_unknown_usage(
    tmp_path: Path, clock: ControlledClock, asynchronous: bool
) -> None:
    selected = replace(policy(), period_seconds=600)
    root = tmp_path / "deadline"
    reservation = (
        asyncio.run(
            reserve_budget_async(
                root, selected, "task", 100, clock=clock, boot="boot-a", deadline_seconds=120
            )
        )
        if asynchronous
        else reserve_budget(
            root, selected, "task", 100, clock=clock, boot="boot-a", deadline_seconds=120
        )
    )
    first = unwrap(reservation)
    clock.advance(60)
    blocked = reserve_budget(
        root, selected, "task", 100, clock=clock, boot="boot-a", deadline_seconds=1
    )
    assert isinstance(blocked, Failure) and blocked.code == "deferred"
    assert blocked.retry_after_seconds == 60
    clock.advance(60)
    unwrap(
        reserve_budget(root, selected, "task", 100, clock=clock, boot="boot-a", deadline_seconds=1)
    )
    observed = unwrap(inspect_budget(root, selected, "task", clock=clock, boot="boot-a"))
    assert observed.group_requests == observed.task_requests == 2
    assert observed.group_bytes == observed.task_bytes == 200
    assert observed.pending_reservations == 1
    assert not unwrap(settle_budget(root, selected, first, 0, clock=clock, boot="boot-a"))
    retained = unwrap(inspect_budget(root, selected, "task", clock=clock, boot="boot-a"))
    assert retained.group_bytes == retained.task_bytes == 200


@pytest.mark.parametrize("deadline", [0, 120.001, float("inf"), True])
def test_reservation_deadline_outside_the_explicit_bound_is_rejected_before_io(
    tmp_path: Path, clock: ControlledClock, deadline: float
) -> None:
    root = tmp_path / "invalid-deadline"
    sync = reserve_budget(
        root, policy(), "task", 100, clock=clock, boot="boot-a", deadline_seconds=deadline
    )
    asynchronous = asyncio.run(
        reserve_budget_async(
            root, policy(), "task", 100, clock=clock, boot="boot-a", deadline_seconds=deadline
        )
    )
    for result in (sync, asynchronous):
        assert isinstance(result, Failure) and result.code == "invalid_input"
    assert not root.exists()


def test_group_and_task_counts_are_controlled_by_state_bytes_not_old_record_caps(
    tmp_path: Path, clock: ControlledClock
) -> None:
    policies = tuple(
        BudgetPolicy(f"group-{number}", 60, 2000, 2000, 2000, 2000) for number in range(300)
    )
    groups = (
        GroupUsage(policies[0].group, 1200, 1200),
        *(GroupUsage(selected.group, 0, 0) for selected in policies[1:]),
    )
    tasks = tuple(Usage(f"task-{number}", 1, 1) for number in range(1200))
    snapshot = BudgetSnapshot(60, clock.wall(), clock.wall(), groups, tasks)
    root = tmp_path / "large-state"
    unwrap(import_budget(root, policies, snapshot, clock=clock, boot="boot-a"))
    unwrap(reserve_budget(root, policies[0], "new-task", 1, clock=clock, boot="boot-a"))
    observed = unwrap(inspect_budget(root, policies[0], "new-task", clock=clock, boot="boot-a"))
    assert observed.group_requests == observed.group_bytes == 1201
    assert observed.task_requests == observed.task_bytes == 1


def test_usage_above_old_request_and_byte_ceilings_preserves_accounting(
    tmp_path: Path, clock: ControlledClock
) -> None:
    bytes_used = 65 * 1024**3
    selected = BudgetPolicy("source", 60, 1_000_000, 2**50, 1_000_000, 2**50)
    snapshot = BudgetSnapshot(
        60,
        clock.wall() - 1,
        clock.wall(),
        (GroupUsage("source", 10001, bytes_used),),
        (Usage("task", 10001, bytes_used),),
    )
    root = tmp_path / "large-counters"
    unwrap(import_budget(root, (selected,), snapshot, clock=clock, boot="boot-a"))
    reservation = unwrap(reserve_budget(root, selected, "task", 128, clock=clock, boot="boot-a"))
    observed = unwrap(inspect_budget(root, selected, "task", clock=clock, boot="boot-a"))
    assert observed.group_requests == observed.task_requests == 10002
    assert observed.group_bytes == observed.task_bytes == bytes_used + 128
    unwrap(settle_budget(root, selected, reservation, 64, clock=clock, boot="boot-a"))
    assert (
        unwrap(inspect_budget(root, selected, "task", clock=clock, boot="boot-a")).task_bytes
        == bytes_used + 64
    )


def test_group_and_task_allowances_are_shared_across_transports(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "quotas"
    first = unwrap(reserve_budget(root, policy(), "assignment", 100, clock=clock, boot="boot-a"))
    unwrap(settle_budget(root, policy(), first, 20, clock=clock, boot="boot-a"))
    unwrap(
        reserve_budget(
            root, policy("browser-source"), "assignment", 100, clock=clock, boot="boot-a"
        )
    )
    unwrap(reserve_budget(root, policy(), "assignment", 100, clock=clock, boot="boot-a"))
    blocked = reserve_budget(
        root, policy("third-source"), "assignment", 10, clock=clock, boot="boot-a"
    )
    assert isinstance(blocked, Failure) and blocked.code == "deferred"
    observed = unwrap(inspect_budget(root, policy(), "assignment", clock=clock, boot="boot-a"))
    assert observed.group_requests == 2 and observed.group_bytes == 120
    assert observed.task_requests == 3 and observed.task_bytes == 220
    assert not unwrap(settle_budget(root, policy(), first, 20, clock=clock, boot="boot-a"))


def test_reboot_does_not_reset_period_and_clock_rollback_is_denied(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "quotas"
    unwrap(reserve_budget(root, policy(), "task", 100, clock=clock, boot="boot-a"))
    clock.advance(10)
    clock.current_monotonic = 2
    after = unwrap(inspect_budget(root, policy(), "task", clock=clock, boot="boot-b"))
    assert after.task_bytes == 100 and after.task_requests == 1
    clock.advance(50)
    assert (
        unwrap(inspect_budget(root, policy(), "task", clock=clock, boot="boot-b")).task_requests
        == 0
    )
    clock.advance(-1)
    assert isinstance(
        reserve_budget(root, policy(), "task", 100, clock=clock, boot="boot-b"), Failure
    )


def test_unknown_usage_policy_changes_and_cooldowns_cannot_reset_allowances(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "quotas"
    reservation = unwrap(reserve_budget(root, policy(), "task", 100, clock=clock, boot="boot-a"))
    observed = unwrap(inspect_budget(root, policy(), "task", clock=clock, boot="boot-a"))
    assert observed.task_bytes == 100
    assert isinstance(
        inspect_budget(
            root, replace(policy(), group_requests=9), "task", clock=clock, boot="boot-a"
        ),
        Failure,
    )
    unwrap(settle_budget(root, policy(), reservation, 20, None, clock=clock, boot="boot-a"))
    clock.advance(600)
    observed = unwrap(inspect_budget(root, policy(), "task", clock=clock, boot="boot-a"))
    assert observed.group_requests == 0 and observed.next_request_at is None
    assert isinstance(
        reserve_budget(root, policy(), "task", 100, clock=clock, boot="boot-a"), Failure
    )


@pytest.mark.parametrize("corruption", ["counter", "reservation", "conservation"])
def test_budget_state_corruption_is_not_accepted(
    tmp_path: Path, clock: ControlledClock, corruption: str
) -> None:
    root = tmp_path / "quotas"
    reservation = unwrap(reserve_budget(root, policy(), "task", 100, clock=clock, boot="boot-a"))
    state = json.loads((root / "budget.json").read_bytes())
    if corruption == "counter":
        state["groups"]["source"]["usage"]["requests"] = 0
    elif corruption == "reservation":
        state["reservations"][reservation.identity]["bytes"] = 999
    else:
        state["tasks"]["task"]["bytes"] = 20
    (root / "budget.json").write_text(json.dumps(state))
    assert isinstance(inspect_budget(root, policy(), "task", clock=clock, boot="boot-a"), Failure)


def test_independent_http_uses_canonical_routing_without_archive(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "quotas"
    transport = RecordedTransport([Response(302, (("location", "/final"),), b"", 5), plain()])
    result = unwrap(
        fetch_http(
            "https://example.com/first",
            HttpPolicy(("example.com",), maximum_response_bytes=100),
            root,
            policy(),
            "task",
            clock=clock,
            resolver=FixedResolver(),
            transport=transport,
        )
    )
    assert result.requests == 2 and result.wire_bytes == 5 + len(result.content)
    assert result.final_url == "https://example.com/final"
    assert not list(tmp_path.rglob("*.sqlite3"))
    assert not list(tmp_path.rglob("objects"))


def test_independent_http_failure_keeps_unknown_charge_and_admission_count(
    tmp_path: Path, clock: ControlledClock
) -> None:
    transport = RecordedTransport([ToolsmithError("http", "Connection lost")])
    attempts: list[int] = []
    failed = fetch_http(
        "https://example.com/",
        HttpPolicy(("example.com",), maximum_response_bytes=100),
        tmp_path / "quotas",
        policy(),
        "task",
        clock=clock,
        resolver=FixedResolver(),
        transport=transport,
        before_request=lambda: attempts.append(1),
    )
    assert isinstance(failed, Failure) and failed.code == "http"
    assert attempts == [1]
    observed = unwrap(inspect_budget(tmp_path / "quotas", policy(), "task", clock=clock))
    assert observed.group_bytes == 100 and observed.group_requests == 1


def test_quiesced_forward_quota_import_preserves_charges_and_original_period(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "imported"
    snapshot = BudgetSnapshot(
        60,
        clock.wall() - 20,
        clock.wall() - 1,
        (
            GroupUsage("source", 2, 180, clock.wall() + 2),
            GroupUsage("browser-source", 1, 100, 0, None),
        ),
        (Usage("task", 3, 280),),
    )
    unwrap(
        import_budget(
            root, (policy(), policy("browser-source")), snapshot, clock=clock, boot="boot-a"
        )
    )
    current = unwrap(inspect_budget(root, policy(), "task", clock=clock, boot="boot-a"))
    assert current.group_requests == 2 and current.task_requests == 3 and current.task_bytes == 280
    assert current.period_started == snapshot.period_started
    assert isinstance(
        reserve_budget(root, policy(), "task", 10, clock=clock, boot="boot-a"), Failure
    )
    assert (
        unwrap(
            inspect_budget(root, policy("browser-source"), "task", clock=clock, boot="boot-a")
        ).next_request_at
        is None
    )
    assert isinstance(
        import_budget(root, (policy(),), snapshot, clock=clock, boot="boot-a"), Failure
    )


def test_quota_import_rejects_nonconservation_and_shorter_period(
    tmp_path: Path, clock: ControlledClock
) -> None:
    snapshot = BudgetSnapshot(
        60, clock.wall(), clock.wall(), (GroupUsage("source", 1, 100),), (Usage("task", 1, 20),)
    )
    assert isinstance(
        import_budget(tmp_path / "mismatch", (policy(),), snapshot, clock=clock, boot="boot-a"),
        Failure,
    )
    changed = replace(snapshot, period_seconds=120)
    assert isinstance(
        import_budget(tmp_path / "shorter", (policy(),), changed, clock=clock, boot="boot-a"),
        Failure,
    )
