from dataclasses import dataclass
from pathlib import Path

from toolsmith.acquisition.budgets import (
    BudgetPolicy,
    common_definition,
    counters,
    load,
    records,
    save,
    scope,
    validate_policy,
)
from toolsmith.clock import Clock, SystemClock
from toolsmith.files import directory_lock, private_directory
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import JsonValue, identity, integer, number


@dataclass(frozen=True)
class Usage:
    identity: str
    requests: int
    reserved_bytes: int


@dataclass(frozen=True)
class GroupUsage:
    identity: str
    requests: int
    reserved_bytes: int
    next_request_at: float = 0
    cooldown_until: float | None = 0


@dataclass(frozen=True)
class BudgetSnapshot:
    period_seconds: float
    period_started: float
    last_observed: float
    groups: tuple[GroupUsage, ...]
    tasks: tuple[Usage, ...]


@boundary
def import_budget(
    root: Path,
    policies: tuple[BudgetPolicy, ...],
    snapshot: BudgetSnapshot,
    *,
    clock: Clock | None = None,
    boot: str,
) -> bool:
    if not isinstance(policies, tuple) or not policies or not isinstance(snapshot, BudgetSnapshot):
        raise ToolsmithError(
            "invalid_input", "Supply reviewed group policies and a typed quota snapshot"
        )
    checked = {policy.group: validate_policy(policy) for policy in policies}
    if (
        len(checked) != len(policies)
        or len({common_definition(policy) for policy in checked.values()}) != 1
    ):
        raise ToolsmithError(
            "invalid_input", "Group policies must have unique names and the same period/task limits"
        )
    selected = next(iter(checked.values()))
    if (
        number(snapshot.period_seconds, 1, 31 * 86400, "Original quota period")
        != selected.period_seconds
    ):
        raise ToolsmithError("conflict", "Quota import cannot change the original period duration")
    actual_clock = clock or SystemClock()
    now = number(actual_clock.wall(), 0, 2**53, "Current time")
    started = number(snapshot.period_started, 0, now, "Original period start")
    observed = number(snapshot.last_observed, started, now, "Last observed time")
    if now - started >= selected.period_seconds:
        raise ToolsmithError(
            "conflict", "Snapshot period already expired; supply the current reviewed counters"
        )
    if not isinstance(snapshot.groups, tuple) or not isinstance(snapshot.tasks, tuple):
        raise ToolsmithError("invalid_input", "Quota snapshot exceeds its scope bounds")
    groups: dict[str, JsonValue] = {}
    tasks: dict[str, JsonValue] = {}
    for entry in snapshot.groups:
        if not isinstance(entry, GroupUsage):
            raise ToolsmithError("invalid_input", "Supply typed group usage")
        group = identity(entry.identity)
        if group not in checked or group in groups:
            raise ToolsmithError("invalid_input", "Snapshot group is duplicate or unapproved")
        usage = counters({"requests": entry.requests, "bytes": entry.reserved_bytes})
        next_request = number(entry.next_request_at, 0, 2**53, "Next request")
        cooldown = (
            None
            if entry.cooldown_until is None
            else number(entry.cooldown_until, 0, 2**53, "Cooldown")
        )
        groups[group] = {"usage": usage, "next": next_request, "cooldown": cooldown}
    for task_entry in snapshot.tasks:
        if not isinstance(task_entry, Usage):
            raise ToolsmithError("invalid_input", "Supply typed task usage")
        task = identity(task_entry.identity)
        if task in tasks:
            raise ToolsmithError("invalid_input", "Snapshot tasks must be unique")
        tasks[task] = counters(
            {"requests": task_entry.requests, "bytes": task_entry.reserved_bytes}
        )
    for column in ("requests", "bytes"):
        group_total = sum(
            integer(counters(value["usage"])[column], 0, 2**63 - 1, "Usage")
            for value in groups.values()
            if isinstance(value, dict)
        )
        task_total = sum(
            integer(counters(value)[column], 0, 2**63 - 1, "Usage") for value in tasks.values()
        )
        if group_total != task_total:
            raise ToolsmithError(
                "integrity", "Imported group/task usage must conserve charged requests and bytes"
            )
    with private_directory(root, create=True) as directory, directory_lock(directory):
        import os

        if set(os.listdir(directory.descriptor)) - {".lock"}:
            raise ToolsmithError("conflict", "Quota import requires an empty new state directory")
        state = load(directory, selected, actual_clock, identity(boot))
        for group_name in groups:
            scope(state, checked[group_name], "import")
            group_record = records(state["groups"])[group_name]
            if not isinstance(group_record, dict) or not isinstance(groups[group_name], dict):
                raise ToolsmithError("integrity", "Imported group state is malformed")
            value = groups[group_name]
            if isinstance(value, dict):
                group_record.update(value)
        state["tasks"] = tasks
        state["started_wall"] = started
        state["last_wall"] = max(observed, now)
        monotonic = actual_clock.monotonic()
        state["started_monotonic"] = monotonic
        state["elapsed_before_boot"] = now - started
        save(directory, state)
    return True
