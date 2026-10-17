import hashlib
from dataclasses import replace
from pathlib import Path
from typing import cast

from conftest import ControlledClock
from test_generic_budgets import policy

from toolsmith.acquisition.budget_import import BudgetSnapshot, GroupUsage, Usage, import_budget
from toolsmith.acquisition.budgets import (
    BudgetPolicy,
    inspect_budget,
    reserve_budget,
    settle_budget,
)
from toolsmith.acquisition.configuration import (
    check_budget,
    configure_budget,
    inspect_configuration,
)
from toolsmith.files import directory_lock, private_directory
from toolsmith.result import Failure, unwrap
from toolsmith.validation import canonical_json


def test_configuration_and_charged_policy_update_are_atomic(tmp_path: Path) -> None:
    root = tmp_path / "quota"
    clock = ControlledClock()
    original = policy()
    saved = unwrap(
        configure_budget(root, (original,), {"hosts": ["example.com"]}, clock=clock, boot="boot-a")
    )
    held = unwrap(
        reserve_budget(
            root,
            original,
            "task",
            100,
            clock=clock,
            boot="boot-a",
            expected_configuration_digest=saved.digest,
        )
    )
    unwrap(settle_budget(root, original, held, 40, clock=clock, boot="boot-a"))
    before = (root / "budget.json").read_bytes()
    changed = replace(original, group_bytes=original.group_bytes + 100)
    denied = configure_budget(
        root,
        (changed,),
        {"hosts": []},
        previous_policies=(original,),
        expected_digest="0" * 64,
        clock=clock,
        boot="boot-a",
    )
    assert isinstance(denied, Failure)
    assert (root / "budget.json").read_bytes() == before
    current = unwrap(
        configure_budget(
            root,
            (changed,),
            {"hosts": ["next.example.com"]},
            previous_policies=(original,),
            expected_digest=saved.digest,
            clock=clock,
            boot="boot-a",
        )
    )
    assert current.digest == hashlib.sha256(canonical_json(current.value)).hexdigest()
    assert unwrap(inspect_configuration(root)) == current
    status = unwrap(inspect_budget(root, changed, "task", clock=clock, boot="boot-a"))
    assert (status.group_requests, status.group_bytes, status.task_bytes) == (1, 40, 40)
    before_audit = (root / "budget.json").read_bytes()
    assert unwrap(check_budget(root, (changed,), clock=clock, boot="boot-a")) == 0
    assert (root / "budget.json").read_bytes() == before_audit


def test_lost_state_and_shortened_period_never_reset_usage(tmp_path: Path) -> None:
    root = tmp_path / "quota"
    clock = ControlledClock()
    selected = policy()
    saved = unwrap(configure_budget(root, (selected,), {}, clock=clock, boot="boot-a"))
    shortened = replace(selected, period_seconds=selected.period_seconds - 1)
    before = (root / "budget.json").read_bytes()
    assert isinstance(
        configure_budget(
            root,
            (shortened,),
            {},
            previous_policies=(selected,),
            expected_digest=saved.digest,
            clock=clock,
            boot="boot-a",
        ),
        Failure,
    )
    assert (root / "budget.json").read_bytes() == before
    (root / "budget.json").unlink()
    assert isinstance(check_budget(root, (selected,), clock=clock, boot="boot-a"), Failure)
    assert isinstance(configure_budget(root, (selected,), {}, clock=clock, boot="boot-a"), Failure)
    assert not (root / "budget.json").exists()


def test_invalid_policy_objects_are_rejected_before_creating_any_state(tmp_path: Path) -> None:
    root = tmp_path / "quota"
    malformed = cast(tuple[BudgetPolicy, ...], (None,))
    assert isinstance(configure_budget(root, malformed, {}), Failure)
    assert not root.exists()
    assert isinstance(configure_budget(Path("relative"), (policy(),), {}), Failure)


def test_configuration_reads_and_audits_share_the_writer_lock_without_writes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "quota"
    clock = ControlledClock()
    selected = policy()
    saved = unwrap(configure_budget(root, (selected,), {}, clock=clock, boot="boot-a"))
    before = (root / "budget.json").read_bytes()
    with private_directory(root) as directory, directory_lock(directory):
        for result in (
            inspect_configuration(root),
            check_budget(root, (selected,), clock=clock, boot="boot-a"),
        ):
            assert isinstance(result, Failure) and result.code == "deferred"
    assert unwrap(inspect_configuration(root)) == saved
    assert (root / "budget.json").read_bytes() == before
    assert not (root / ".lock").exists()
    missing = tmp_path / "missing"
    assert unwrap(inspect_configuration(missing)) is None
    assert not missing.exists()


def test_reservation_requires_the_exact_current_application_configuration(tmp_path: Path) -> None:
    root = tmp_path / "quota"
    clock = ControlledClock()
    selected = policy()
    saved = unwrap(
        configure_budget(
            root, (selected,), {"hosts": ["original.example"]}, clock=clock, boot="boot-a"
        )
    )
    before = (root / "budget.json").read_bytes()
    assert isinstance(
        reserve_budget(root, selected, "task", 40, clock=clock, boot="boot-a"), Failure
    )
    assert (root / "budget.json").read_bytes() == before
    current = unwrap(
        configure_budget(
            root,
            (selected,),
            {"hosts": ["changed.example"]},
            previous_policies=(selected,),
            expected_digest=saved.digest,
            clock=clock,
            boot="boot-a",
        )
    )
    before = (root / "budget.json").read_bytes()
    stale = reserve_budget(
        root,
        selected,
        "task",
        40,
        clock=clock,
        boot="boot-a",
        expected_configuration_digest=saved.digest,
    )
    assert isinstance(stale, Failure) and stale.code == "conflict"
    assert (root / "budget.json").read_bytes() == before
    held = unwrap(
        reserve_budget(
            root,
            selected,
            "task",
            40,
            clock=clock,
            boot="boot-a",
            expected_configuration_digest=current.digest,
        )
    )
    unwrap(settle_budget(root, selected, held, 25, clock=clock, boot="boot-a"))
    assert (
        unwrap(inspect_budget(root, selected, "task", clock=clock, boot="boot-a")).task_bytes == 25
    )


def test_pending_charges_and_retired_groups_survive_configuration_changes(tmp_path: Path) -> None:
    root = tmp_path / "quota"
    clock = ControlledClock()
    selected = policy()
    saved = unwrap(configure_budget(root, (selected,), {}, clock=clock, boot="boot-a"))
    held = unwrap(
        reserve_budget(
            root,
            selected,
            "task",
            100,
            clock=clock,
            boot="boot-a",
            expected_configuration_digest=saved.digest,
        )
    )
    before = (root / "budget.json").read_bytes()
    for replacement in ((replace(selected, group_bytes=2000),), (policy("other"),)):
        rejected = configure_budget(
            root,
            replacement,
            {},
            previous_policies=(selected,),
            expected_digest=saved.digest,
            clock=clock,
            boot="boot-a",
        )
        assert isinstance(rejected, Failure) and rejected.code == "conflict"
        assert (root / "budget.json").read_bytes() == before
    unwrap(settle_budget(root, selected, held, 50, clock=clock, boot="boot-a"))
    assert isinstance(
        configure_budget(
            root,
            (policy("other"),),
            {},
            previous_policies=(selected,),
            expected_digest=saved.digest,
            clock=clock,
            boot="boot-a",
        ),
        Failure,
    )
    clock.advance(selected.period_seconds)
    unwrap(
        configure_budget(
            root,
            (policy("other"),),
            {},
            previous_policies=(selected,),
            expected_digest=saved.digest,
            clock=clock,
            boot="boot-a",
        )
    )
    assert (
        unwrap(
            inspect_budget(root, policy("other"), "task", clock=clock, boot="boot-a")
        ).group_requests
        == 0
    )


def test_import_with_an_advancing_clock_preserves_a_valid_monotonic_interval(
    tmp_path: Path,
) -> None:
    class AdvancingClock(ControlledClock):
        def monotonic(self) -> float:
            self.advance(0.01)
            return self.current_monotonic

    clock = AdvancingClock()
    root = tmp_path / "quota"
    selected = policy()
    snapshot = BudgetSnapshot(
        selected.period_seconds,
        clock.wall() - 10,
        clock.wall(),
        (GroupUsage(selected.group, 1, 40),),
        (Usage("task", 1, 40),),
    )
    unwrap(import_budget(root, (selected,), snapshot, clock=clock, boot="boot-a"))
    observed = unwrap(inspect_budget(root, selected, "task", clock=clock, boot="boot-a"))
    assert observed.group_requests == observed.task_requests == 1
    assert observed.group_bytes == observed.task_bytes == 40
