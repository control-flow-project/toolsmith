import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from toolsmith.clock import Clock, SystemClock
from toolsmith.files import (
    PrivateDirectory,
    directory_lock,
    private_directory,
    read_private,
    replace_private,
)
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import (
    JsonValue,
    canonical_json,
    fields,
    identity,
    integer,
    number,
    parse_json,
)

MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_BYTES = 64 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class BudgetPolicy:
    group: str
    period_seconds: float
    group_requests: int
    group_bytes: int
    task_requests: int
    task_bytes: int
    minimum_interval_seconds: float = 0
    definition: str = "explicit-budget-v1"


@dataclass(frozen=True)
class Reservation:
    identity: str
    period: str
    group: str
    task: str
    charged_bytes: int


@dataclass(frozen=True)
class BudgetStatus:
    group: str
    task: str
    period_started: float
    group_requests: int
    group_bytes: int
    task_requests: int
    task_bytes: int
    next_request_at: float | None


def validate_policy(policy: BudgetPolicy) -> BudgetPolicy:
    if not isinstance(policy, BudgetPolicy):
        raise ToolsmithError("invalid_input", "Supply an explicit typed budget policy")
    identity(policy.group, "Budget group")
    identity(policy.definition, "Policy definition")
    number(policy.period_seconds, 1, 31 * 86400, "Period seconds")
    number(policy.minimum_interval_seconds, 0, 31 * 86400, "Minimum interval")
    integer(policy.group_requests, 1, 10000, "Group requests")
    integer(policy.task_requests, 1, 10000, "Task requests")
    integer(policy.group_bytes, 1, MAX_BYTES, "Group bytes")
    integer(policy.task_bytes, 1, MAX_BYTES, "Task bytes")
    return BudgetPolicy(
        policy.group,
        number(policy.period_seconds, 1, 31 * 86400, "Period seconds"),
        policy.group_requests,
        policy.group_bytes,
        policy.task_requests,
        policy.task_bytes,
        number(policy.minimum_interval_seconds, 0, 31 * 86400, "Minimum interval"),
        policy.definition,
    )


def boot_identity() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def records(value: JsonValue, maximum: int) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or len(value) > maximum:
        raise ToolsmithError("integrity", "Budget record capacity or storage type is invalid")
    return value


def counters(value: JsonValue) -> dict[str, JsonValue]:
    output = fields(value, {"requests", "bytes"})
    requests = integer(output["requests"], 0, 10000, "Stored requests")
    used = integer(output["bytes"], 0, MAX_BYTES, "Stored bytes")
    if used and not requests:
        raise ToolsmithError("integrity", "Budget bytes have no charged request")
    return output


def common_definition(policy: BudgetPolicy) -> str:
    return hashlib.sha256(
        canonical_json((policy.period_seconds, policy.task_requests, policy.task_bytes))
    ).hexdigest()


def load(
    directory: PrivateDirectory, policy: BudgetPolicy, clock: Clock, boot: str
) -> dict[str, JsonValue]:
    wall = number(clock.wall(), 0, 2**53, "Wall time")
    monotonic = number(clock.monotonic(), 0, 2**53, "Monotonic time")
    try:
        encoded = read_private(directory, "budget.json", MAX_STATE_BYTES)
    except FileNotFoundError:
        if any(name.endswith(".json") for name in os.listdir(directory.descriptor)):
            raise ToolsmithError(
                "conflict", "Existing quota state requires an explicit reviewed migration"
            ) from None
        return {
            "format": 1,
            "common": common_definition(policy),
            "period": uuid4().hex,
            "started_wall": wall,
            "started_monotonic": monotonic,
            "elapsed_before_boot": 0,
            "last_wall": wall,
            "last_monotonic": monotonic,
            "boot": boot,
            "groups": {},
            "tasks": {},
            "reservations": {},
        }
    state = fields(
        parse_json(encoded, MAX_STATE_BYTES),
        {
            "format",
            "common",
            "period",
            "started_wall",
            "started_monotonic",
            "elapsed_before_boot",
            "last_wall",
            "last_monotonic",
            "boot",
            "groups",
            "tasks",
            "reservations",
        },
    )
    integer(state["format"], 1, 1, "Budget format")
    if state["common"] != common_definition(policy):
        raise ToolsmithError("conflict", "Shared period/task policy changed; quotas were not reset")
    identity(state["period"], "Period")
    identity(state["boot"], "Boot identity")
    began = number(state["started_wall"], 0, 2**53, "Period start")
    began_monotonic = number(state["started_monotonic"], 0, 2**53, "Period monotonic start")
    last = number(state["last_wall"], began, 2**53, "Last wall time")
    last_monotonic = number(state["last_monotonic"], began_monotonic, 2**53, "Last monotonic time")
    groups = records(state["groups"], 256)
    tasks = records(state["tasks"], 1024)
    pending = records(state["reservations"], 10000)
    group_usage: dict[str, dict[str, JsonValue]] = {}
    task_usage = {identity(key): counters(value) for key, value in tasks.items()}
    for key, value in groups.items():
        identity(key)
        group = fields(value, {"definition", "usage", "next", "cooldown"})
        identity(group["definition"], "Group policy definition")
        number(group["next"], 0, 2**53, "Next request")
        if group["cooldown"] is not None:
            number(group["cooldown"], 0, 2**53, "Cooldown")
        group_usage[key] = counters(group["usage"])
    held_groups: dict[str, list[int]] = {}
    held_tasks: dict[str, list[int]] = {}
    for key, value in pending.items():
        identity(key, "Reservation identity")
        reservation = fields(value, {"group", "task", "bytes"})
        group_name = identity(reservation["group"])
        task = identity(reservation["task"])
        charged = integer(reservation["bytes"], 1, 128 * 1024 * 1024, "Reserved bytes")
        if group_name not in group_usage or task not in task_usage:
            raise ToolsmithError("integrity", "Reservation has no charged group/task")
        for totals, selected in ((held_groups, group_name), (held_tasks, task)):
            total = totals.setdefault(selected, [0, 0])
            total[0] += 1
            total[1] += charged
    for usage, held in ((group_usage, held_groups), (task_usage, held_tasks)):
        for key, total in held.items():
            if (
                integer(usage[key]["requests"], 0, 10000, "Requests") < total[0]
                or integer(usage[key]["bytes"], 0, MAX_BYTES, "Bytes") < total[1]
            ):
                raise ToolsmithError("integrity", "Pending usage exceeds charged counters")
    for column in ("requests", "bytes"):
        if sum(
            integer(value[column], 0, MAX_BYTES, "Usage") for value in group_usage.values()
        ) != sum(integer(value[column], 0, MAX_BYTES, "Usage") for value in task_usage.values()):
            raise ToolsmithError(
                "integrity", "Group/task usage does not conserve requests and bytes"
            )
    if wall < last or state["boot"] == boot and monotonic < last_monotonic:
        current = fields(
            groups.get(
                policy.group,
                {
                    "definition": "none",
                    "usage": {"requests": 0, "bytes": 0},
                    "next": 0,
                    "cooldown": 0,
                },
            ),
            {"definition", "usage", "next", "cooldown"},
        )
        delay = (
            None
            if current["cooldown"] is None
            else max(
                last - wall,
                number(current["next"], 0, 2**53, "Next") - wall,
                number(current["cooldown"], 0, 2**53, "Cooldown") - wall,
            )
        )
        raise ToolsmithError("deferred", "Clock rollback prevents new reservations", delay)
    elapsed = wall - began
    if state["boot"] == boot:
        elapsed = min(
            elapsed,
            number(state["elapsed_before_boot"], 0, policy.period_seconds, "Retained elapsed time")
            + monotonic
            - began_monotonic,
        )
    if elapsed >= policy.period_seconds:
        for value in groups.values():
            if isinstance(value, dict):
                value["usage"] = {"requests": 0, "bytes": 0}
        state.update(
            {
                "period": uuid4().hex,
                "started_wall": wall,
                "started_monotonic": monotonic,
                "elapsed_before_boot": 0,
                "tasks": {},
                "reservations": {},
            }
        )
    elif state["boot"] != boot:
        state["started_monotonic"] = monotonic
        state["elapsed_before_boot"] = elapsed
    state.update({"last_wall": wall, "last_monotonic": monotonic, "boot": boot})
    return state


def save(directory: PrivateDirectory, state: dict[str, JsonValue]) -> None:
    encoded = canonical_json(state)
    if len(encoded) > MAX_STATE_BYTES:
        raise ToolsmithError("limit", "Persistent quota state exceeds its byte budget")
    replace_private(directory, "budget.json", encoded)


def scope(
    state: dict[str, JsonValue], policy: BudgetPolicy, task: str
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    groups, tasks = records(state["groups"], 256), records(state["tasks"], 1024)
    definition = hashlib.sha256(canonical_json(policy)).hexdigest()
    if policy.group not in groups:
        if len(groups) >= 256:
            raise ToolsmithError("limit", "Budget group capacity is exhausted")
        groups[policy.group] = {
            "definition": definition,
            "usage": {"requests": 0, "bytes": 0},
            "next": 0,
            "cooldown": 0,
        }
    group = fields(groups[policy.group], {"definition", "usage", "next", "cooldown"})
    if group["definition"] != definition:
        raise ToolsmithError("conflict", "Group policy changed; quotas were not reset")
    if task not in tasks:
        if len(tasks) >= 1024:
            raise ToolsmithError("limit", "Budget task capacity is exhausted until the next period")
        tasks[task] = {"requests": 0, "bytes": 0}
    return group, counters(tasks[task])


def status(state: dict[str, JsonValue], policy: BudgetPolicy, task: str) -> BudgetStatus:
    group, task_usage = scope(state, policy, task)
    usage = counters(group["usage"])
    return BudgetStatus(
        policy.group,
        task,
        number(state["started_wall"], 0, 2**53, "Period start"),
        integer(usage["requests"], 0, 10000, "Requests"),
        integer(usage["bytes"], 0, MAX_BYTES, "Bytes"),
        integer(task_usage["requests"], 0, 10000, "Task requests"),
        integer(task_usage["bytes"], 0, MAX_BYTES, "Task bytes"),
        None
        if group["cooldown"] is None
        else max(
            number(group["next"], 0, 2**53, "Next"), number(group["cooldown"], 0, 2**53, "Cooldown")
        ),
    )


@boundary
def inspect_budget(
    root: Path,
    policy: BudgetPolicy,
    task: str,
    *,
    clock: Clock | None = None,
    boot: str | None = None,
) -> BudgetStatus:
    checked, selected = validate_policy(policy), identity(task, "Task")
    with private_directory(root, create=True) as directory, directory_lock(directory):
        state = load(directory, checked, clock or SystemClock(), identity(boot or boot_identity()))
        result = status(state, checked, selected)
        save(directory, state)
        return result


@boundary
def reserve_budget(
    root: Path,
    policy: BudgetPolicy,
    task: str,
    maximum_bytes: int,
    *,
    clock: Clock | None = None,
    boot: str | None = None,
) -> Reservation:
    checked, selected = validate_policy(policy), identity(task, "Task")
    charged = integer(maximum_bytes, 1, 128 * 1024 * 1024, "Reservation bytes")
    actual_clock = clock or SystemClock()
    with private_directory(root, create=True) as directory, directory_lock(directory):
        state = load(directory, checked, actual_clock, identity(boot or boot_identity()))
        observed = status(state, checked, selected)
        now = actual_clock.wall()
        if observed.next_request_at is None or observed.next_request_at > now:
            raise ToolsmithError(
                "deferred",
                "Source spacing/cooldown prevents a request",
                None if observed.next_request_at is None else observed.next_request_at - now,
            )
        if (
            observed.group_requests >= checked.group_requests
            or observed.group_bytes + charged > checked.group_bytes
            or observed.task_requests >= checked.task_requests
            or observed.task_bytes + charged > checked.task_bytes
        ):
            raise ToolsmithError(
                "deferred",
                "Group or task allowance is exhausted",
                max(0.1, observed.period_started + checked.period_seconds - now),
            )
        pending = records(state["reservations"], 10000)
        if len(pending) >= 10000:
            raise ToolsmithError("limit", "Reservation capacity is exhausted")
        reservation = Reservation(
            uuid4().hex, identity(state["period"]), checked.group, selected, charged
        )
        group, task_usage = scope(state, checked, selected)
        usage = counters(group["usage"])
        for counter in (usage, task_usage):
            counter["requests"] = integer(counter["requests"], 0, 9999, "Requests") + 1
            counter["bytes"] = integer(counter["bytes"], 0, MAX_BYTES - charged, "Bytes") + charged
        group["usage"] = usage
        group["next"] = now + checked.minimum_interval_seconds
        pending[reservation.identity] = {
            "group": reservation.group,
            "task": reservation.task,
            "bytes": charged,
        }
        records(state["groups"], 256)[checked.group] = group
        records(state["tasks"], 1024)[selected] = task_usage
        save(directory, state)
        return reservation


@boundary
def settle_budget(
    root: Path,
    policy: BudgetPolicy,
    reservation: Reservation,
    actual_bytes: int,
    cooldown_seconds: float | None = 0,
    *,
    clock: Clock | None = None,
    boot: str | None = None,
) -> bool:
    checked = validate_policy(policy)
    if not isinstance(reservation, Reservation) or reservation.group != checked.group:
        raise ToolsmithError("invalid_input", "Reservation belongs to another budget group")
    identity(reservation.identity)
    identity(reservation.period)
    identity(reservation.task)
    charged = integer(reservation.charged_bytes, 1, 128 * 1024 * 1024, "Charged bytes")
    used = integer(actual_bytes, 0, charged, "Actual bytes")
    actual_clock = clock or SystemClock()
    now = actual_clock.wall()
    cooldown = (
        None if cooldown_seconds is None else number(cooldown_seconds, 0, 2**53 - now, "Cooldown")
    )
    with private_directory(root) as directory, directory_lock(directory):
        state = load(directory, checked, actual_clock, identity(boot or boot_identity()))
        group, task_usage = scope(state, checked, reservation.task)
        if cooldown is None:
            group["cooldown"] = None
        elif group["cooldown"] is not None and cooldown:
            group["cooldown"] = max(number(group["cooldown"], 0, 2**53, "Cooldown"), now + cooldown)
        pending = records(state["reservations"], 10000)
        completed = False
        if state["period"] == reservation.period and reservation.identity in pending:
            if pending[reservation.identity] != {
                "group": reservation.group,
                "task": reservation.task,
                "bytes": charged,
            }:
                raise ToolsmithError(
                    "conflict", "Reservation identity does not match its persisted charge"
                )
            pending.pop(reservation.identity)
            usage = counters(group["usage"])
            for counter in (usage, task_usage):
                counter["bytes"] = (
                    integer(counter["bytes"], charged, MAX_BYTES, "Bytes") - charged + used
                )
            group["usage"] = usage
            records(state["tasks"], 1024)[reservation.task] = task_usage
            completed = True
        records(state["groups"], 256)[checked.group] = group
        save(directory, state)
        return completed
