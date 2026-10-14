import hashlib
from dataclasses import dataclass
from pathlib import Path

from toolsmith.acquisition.budgets import (
    BudgetPolicy,
    Reservation,
    inspect_budget,
    reserve_budget,
    settle_budget,
)
from toolsmith.acquisition.policy import SourcePolicy, validate_policy
from toolsmith.clock import Clock
from toolsmith.result import boundary, unwrap
from toolsmith.validation import canonical_json, json_value


@dataclass(frozen=True)
class LimitStatus:
    group: str
    window_started: float
    requests: int
    reserved_bytes: int
    next_request_at: float | None


def policy_hash(policy: SourcePolicy) -> str:
    return hashlib.sha256(canonical_json(json_value(validate_policy(policy)))).hexdigest()


def budget_policy(policy: SourcePolicy) -> BudgetPolicy:
    checked = validate_policy(policy)
    return BudgetPolicy(
        checked.group,
        checked.window_seconds,
        checked.window_requests,
        checked.window_bytes,
        10000,
        64 * 1024 * 1024 * 1024,
        checked.minimum_interval_seconds,
        policy_hash(checked),
    )


@boundary
def inspect_limits(root: Path, policy: SourcePolicy, *, clock: Clock | None = None) -> LimitStatus:
    observed = unwrap(inspect_budget(root, budget_policy(policy), "http", clock=clock))
    return LimitStatus(
        observed.group,
        observed.period_started,
        observed.group_requests,
        observed.group_bytes,
        observed.next_request_at,
    )


def reserve(root: Path, policy: SourcePolicy, clock: Clock) -> Reservation:
    return unwrap(
        reserve_budget(
            root,
            budget_policy(policy),
            "http",
            policy.maximum_response_bytes,
            clock=clock,
        )
    )


def settle(
    root: Path,
    policy: SourcePolicy,
    clock: Clock,
    reservation: Reservation,
    actual_bytes: int,
    cooldown_seconds: float | None = 0,
) -> None:
    unwrap(
        settle_budget(
            root,
            budget_policy(policy),
            reservation,
            actual_bytes,
            cooldown_seconds,
            clock=clock,
        )
    )
