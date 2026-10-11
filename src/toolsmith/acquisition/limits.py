import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from toolsmith.acquisition.policy import SourcePolicy, validate_policy
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
    integer,
    json_value,
    number,
    parse_json,
)


@dataclass(frozen=True)
class LimitStatus:
    group: str
    window_started: float
    requests: int
    reserved_bytes: int
    next_request_at: float | None


@dataclass(frozen=True)
class Reservation:
    identity: str
    window_started: float
    charged_bytes: int


def state_name(policy: SourcePolicy) -> str:
    return hashlib.sha256(policy.group.encode()).hexdigest() + ".json"


def policy_hash(policy: SourcePolicy) -> str:
    return hashlib.sha256(canonical_json(json_value(validate_policy(policy)))).hexdigest()


def load_state(
    directory: PrivateDirectory, policy: SourcePolicy, now: float
) -> dict[str, JsonValue]:
    try:
        raw = read_private(directory, state_name(policy), 65_536)
    except FileNotFoundError:
        return {
            "format": 1,
            "policy": policy_hash(policy),
            "started": now,
            "requests": 0,
            "bytes": 0,
            "next": 0,
            "cooldown": 0,
            "reservations": {},
        }
    state = fields(
        parse_json(raw, 65_536),
        {"format", "policy", "started", "requests", "bytes", "next", "cooldown", "reservations"},
    )
    integer(state["format"], 1, 1, "Limit format")
    if state["policy"] != policy_hash(policy):
        raise ToolsmithError(
            "conflict",
            "Source limit state is bound to a different policy; changing a policy cannot silently reset quotas",
        )
    for key in ("started", "next"):
        number(state[key], 0, 2**53, "Stored limit time")
    if state["cooldown"] is not None:
        number(state["cooldown"], 0, 2**53, "Stored cooldown time")
    integer(state["requests"], 0, 10_000, "Stored requests")
    integer(state["bytes"], 0, 1024 * 16 * 1024 * 1024, "Stored byte reservations")
    reservations = state["reservations"]
    if (
        not isinstance(reservations, dict)
        or len(reservations) > 10_000
        or not all(
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= policy.maximum_response_bytes
            for value in reservations.values()
        )
    ):
        raise ToolsmithError("integrity", "Stored source reservations are invalid")
    started = number(state["started"], 0, 2**53, "Window start")
    if now >= started + policy.window_seconds:
        state.update({"started": now, "requests": 0, "bytes": 0, "reservations": {}})
    return state


def limit_status(policy: SourcePolicy, state: dict[str, JsonValue]) -> LimitStatus:
    return LimitStatus(
        policy.group,
        number(state["started"], 0, 2**53, "Window start"),
        integer(state["requests"], 0, 10_000, "Requests"),
        integer(state["bytes"], 0, 1024 * 16 * 1024 * 1024, "Reserved bytes"),
        None
        if state["cooldown"] is None
        else max(
            number(state["next"], 0, 2**53, "Next request"),
            number(state["cooldown"], 0, 2**53, "Cooldown"),
        ),
    )


@boundary
def inspect_limits(root: Path, policy: SourcePolicy, *, clock: Clock | None = None) -> LimitStatus:
    checked = validate_policy(policy)
    with private_directory(root, create=True) as directory, directory_lock(directory):
        return limit_status(
            checked, load_state(directory, checked, (clock or SystemClock()).wall())
        )


def reserve(root: Path, policy: SourcePolicy, clock: Clock) -> Reservation:
    now = clock.wall()
    with private_directory(root, create=True) as directory, directory_lock(directory):
        state = load_state(directory, policy, now)
        status = limit_status(policy, state)
        if status.next_request_at is None:
            raise ToolsmithError(
                "deferred",
                "Upstream cooldown has no representable end; operator review is required",
            )
        if status.next_request_at > now:
            raise ToolsmithError(
                "deferred",
                "Source pacing or cooldown prevents an immediate request",
                status.next_request_at - now,
            )
        if (
            status.requests >= policy.window_requests
            or status.reserved_bytes + policy.maximum_response_bytes > policy.window_bytes
        ):
            raise ToolsmithError(
                "deferred",
                "Shared source request or byte allowance is exhausted",
                max(0.1, status.window_started + policy.window_seconds - now),
            )
        reservation = uuid4().hex
        pending = state["reservations"]
        if not isinstance(pending, dict):
            raise ToolsmithError("integrity", "Source reservations are invalid")
        pending[reservation] = policy.maximum_response_bytes
        state.update(
            {
                "requests": status.requests + 1,
                "bytes": status.reserved_bytes + policy.maximum_response_bytes,
                "next": now + policy.minimum_interval_seconds,
            }
        )
        encoded = canonical_json(state)
        if len(encoded) > 65_536:
            raise ToolsmithError(
                "limit", "Source reservation record is full until the current window ends"
            )
        replace_private(directory, state_name(policy), encoded)
        return Reservation(reservation, status.window_started, policy.maximum_response_bytes)


def settle(
    root: Path,
    policy: SourcePolicy,
    clock: Clock,
    reservation: Reservation,
    actual_bytes: int,
    cooldown_seconds: float | None = 0,
) -> None:
    used = integer(actual_bytes, 0, reservation.charged_bytes, "Actual response bytes")
    now = number(clock.wall(), 0, 2**53, "Current time")
    cooldown = (
        None
        if cooldown_seconds is None
        else number(cooldown_seconds, 0, 2**53 - now, "Cooldown seconds")
    )
    with private_directory(root) as directory, directory_lock(directory):
        state = load_state(directory, policy, now)
        if cooldown is None:
            state["cooldown"] = None
        elif cooldown and state["cooldown"] is not None:
            state["cooldown"] = max(number(state["cooldown"], 0, 2**53, "Cooldown"), now + cooldown)
        pending = state["reservations"]
        if not isinstance(pending, dict):
            raise ToolsmithError("integrity", "Source reservations are invalid")
        if state["started"] == reservation.window_started and reservation.identity in pending:
            charged = integer(
                pending.pop(reservation.identity), 0, policy.maximum_response_bytes, "Reservation"
            )
            state["bytes"] = (
                integer(state["bytes"], charged, 1024 * 16 * 1024 * 1024, "Reserved bytes")
                - charged
                + used
            )
        replace_private(directory, state_name(policy), canonical_json(state))
