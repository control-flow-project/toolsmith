import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from toolsmith.acquisition.budgets import (
    MAX_STATE_BYTES,
    BudgetPolicy,
    boot_identity,
    common_definition,
    configuration_digest,
    load,
    policies_by_group,
    records,
    save,
    scope,
)
from toolsmith.clock import Clock, SystemClock
from toolsmith.files import (
    absolute_path,
    directory_lock,
    private_directory,
    private_file,
    read_descriptor,
)
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import JsonValue, canonical_json, integer, json_value, parse_json


@dataclass(frozen=True)
class Configuration:
    value: JsonValue
    digest: str


def observed(value: JsonValue) -> Configuration:
    return Configuration(value, configuration_digest(value))


@boundary
def inspect_configuration(root: Path) -> Configuration | None:
    try:
        selected = private_directory(root)
        with selected as directory:
            if "budget.json" not in os.listdir(directory.descriptor):
                return None
            try:
                with (
                    directory_lock(directory, shared=True),
                    private_file(directory, "budget.json") as descriptor,
                ):
                    state = parse_json(
                        read_descriptor(descriptor, MAX_STATE_BYTES), MAX_STATE_BYTES
                    )
                    if (
                        not isinstance(state, dict)
                        or state.get("format") != 2
                        or "configuration" not in state
                    ):
                        raise ToolsmithError(
                            "integrity", "Budget configuration requires an explicit migration"
                        )
                    return observed(state["configuration"])
            except FileNotFoundError as error:
                raise ToolsmithError(
                    "integrity", "Budget configuration lost its owned state"
                ) from error
    except FileNotFoundError:
        return None


@boundary
def configure_budget(
    root: Path,
    policies: tuple[BudgetPolicy, ...],
    configuration: JsonValue,
    *,
    previous_policies: tuple[BudgetPolicy, ...] = (),
    expected_digest: str | None = None,
    clock: Clock | None = None,
    boot: str | None = None,
) -> Configuration:
    absolute_path(root)
    replacement = policies_by_group(policies)
    value = json_value(configuration)
    actual_clock = clock or SystemClock()
    current_boot = boot or boot_identity()
    selected = next(iter(replacement.values()))
    existed = root.exists()
    with private_directory(root, create=True) as directory, directory_lock(directory):
        if "budget.json" in os.listdir(directory.descriptor):
            previous = policies_by_group(previous_policies)
            old = next(iter(previous.values()))
            state = load(directory, old, actual_clock, current_boot)
            if expected_digest != observed(state["configuration"]).digest:
                raise ToolsmithError("conflict", "Configuration differs from the reviewed version")
            for policy in previous.values():
                scope(state, policy, "configuration")
            if selected.period_seconds < old.period_seconds:
                raise ToolsmithError(
                    "conflict", "A reviewed policy change cannot shorten the charged period"
                )
            if records(state["reservations"]) and previous != replacement:
                raise ToolsmithError(
                    "conflict", "Resolve outstanding reservations before changing budget limits"
                )
            for group, record in tuple(records(state["groups"]).items()):
                current = records(record)
                if group in replacement:
                    current["definition"] = hashlib.sha256(
                        canonical_json(replacement[group])
                    ).hexdigest()
                elif any(
                    integer(amount, 0, 2**63 - 1, "Usage")
                    for amount in records(current["usage"]).values()
                ):
                    raise ToolsmithError(
                        "conflict", "A charged group cannot be removed before period rollover"
                    )
                else:
                    del records(state["groups"])[group]
            state["common"] = common_definition(selected)
        else:
            if existed or expected_digest is not None or previous_policies:
                raise ToolsmithError("conflict", "Reviewed configuration no longer exists")
            state = load(directory, selected, actual_clock, current_boot)
        for policy in replacement.values():
            scope(state, policy, "configuration")
        state["configuration"] = value
        save(directory, state)
    return observed(value)


@boundary
def check_budget(
    root: Path,
    policies: tuple[BudgetPolicy, ...],
    *,
    clock: Clock | None = None,
    boot: str | None = None,
) -> int:
    selected = policies_by_group(policies)
    with (
        private_directory(root) as directory,
        directory_lock(directory, shared=True),
    ):
        if "budget.json" not in os.listdir(directory.descriptor):
            raise ToolsmithError("integrity", "Persistent quota state is missing")
        state = load(
            directory,
            next(iter(selected.values())),
            clock or SystemClock(),
            boot or boot_identity(),
        )
        for policy in selected.values():
            scope(state, policy, "configuration")
        return len(records(state["reservations"]))
