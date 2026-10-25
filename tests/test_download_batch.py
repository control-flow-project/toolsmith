import asyncio
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from conftest import ControlledClock
from test_http import FixedResolver, RecordedTransport, plain

from toolsmith.acquisition.batch import DownloadRequest, download_batch
from toolsmith.acquisition.budgets import (
    BudgetPolicy,
    inspect_budget,
    reserve_budget,
    settle_budget,
)
from toolsmith.acquisition.client import HttpPolicy
from toolsmith.acquisition.configuration import configure_budget
from toolsmith.acquisition.transport import Response
from toolsmith.clock import Clock
from toolsmith.result import Failure, Success, unwrap


def request(root: Path, identity: str, group: str, interval: float = 0) -> DownloadRequest:
    return DownloadRequest(
        identity,
        f"https://{group}.example.com/{identity}",
        root / f"{identity}.txt",
        HttpPolicy((f"{group}.example.com",)),
        BudgetPolicy(group, 86400, 10_000, 128 * 1024 * 1024, 10_000, 128 * 1024 * 1024, interval),
    )


@pytest.mark.parametrize("same_group", [True, False])
def test_conflicting_batch_budgets_fail_before_any_request(
    tmp_path: Path, clock: ControlledClock, same_group: bool
) -> None:
    first = request(tmp_path, "first", "one")
    second = request(tmp_path, "second", "one" if same_group else "two")
    second = replace(second, budget=replace(second.budget, task_requests=99))
    transport = RecordedTransport([plain()])
    result = download_batch(
        (first, second),
        tmp_path / "network",
        "assignment",
        clock=clock,
        resolver=FixedResolver(),
        transport=transport,
    )
    assert isinstance(result, Failure)
    assert transport.urls == [] and not (tmp_path / "network").exists()


def test_batch_downloads_more_than_two_hundred_selected_items(
    tmp_path: Path, clock: ControlledClock
) -> None:
    requests = tuple(request(tmp_path, str(number), "publisher") for number in range(250))
    transport = RecordedTransport([plain() for _ in requests])
    batch = unwrap(
        download_batch(
            requests,
            tmp_path / "network",
            "assignment",
            clock=clock,
            resolver=FixedResolver(),
            transport=transport,
        )
    )
    assert batch.complete and len(batch.items) == 250
    assert len(transport.urls) == 250
    assert all(isinstance(item.result, Success) for item in batch.items)
    assert requests[-1].destination.read_bytes() == b"useful words"


def test_batch_requires_current_explicit_approval_for_configured_state(
    tmp_path: Path, clock: ControlledClock
) -> None:
    selected = request(tmp_path, "approved", "one")
    network = tmp_path / "network"
    configured = unwrap(
        configure_budget(network, (selected.budget,), {"approval": "reviewed"}, clock=clock)
    )
    transport = RecordedTransport([plain()])
    rejected = unwrap(
        download_batch(
            (selected,),
            network,
            "assignment",
            clock=clock,
            resolver=FixedResolver(),
            transport=transport,
        )
    )
    assert isinstance(rejected.items[0].result, Failure) and transport.urls == []
    approved = replace(selected, configuration_digest=configured.digest)
    completed = unwrap(
        download_batch(
            (approved,),
            network,
            "assignment",
            clock=clock,
            resolver=FixedResolver(),
            transport=transport,
        )
    )
    assert completed.complete and len(transport.urls) == 1


def test_distinct_groups_overlap_but_each_group_is_serial_and_spaced(
    tmp_path: Path, clock: ControlledClock
) -> None:
    class ParallelTransport:
        def __init__(self) -> None:
            self.other_started = asyncio.Event()
            self.starts: list[tuple[str, float]] = []
            self.active: set[str] = set()
            self.overlapped = False

        async def get_async(
            self,
            url: str,
            addresses: tuple[str, ...],
            maximum_bytes: int,
            deadline: float,
            selected_clock: Clock,
        ) -> Response:
            host = urlsplit(url).hostname or ""
            assert host not in self.active
            self.active.add(host)
            self.starts.append((host, selected_clock.monotonic()))
            try:
                if url.endswith("/first"):
                    await self.other_started.wait()
                else:
                    self.overlapped = self.overlapped or len(self.active) > 1
                    self.other_started.set()
                return plain()
            finally:
                self.active.remove(host)

    transport = ParallelTransport()
    requests = (
        request(tmp_path, "first", "one", 10),
        request(tmp_path, "second", "one", 10),
        request(tmp_path, "other", "two", 10),
    )
    batch = unwrap(
        download_batch(
            requests,
            tmp_path / "network",
            "assignment",
            clock=clock,
            resolver=FixedResolver(),
            transport=transport,
        )
    )
    assert batch.complete and transport.overlapped
    times = [instant for host, instant in transport.starts if host == "one.example.com"]
    assert len(times) == 2 and times[1] - times[0] >= 10


def test_upstream_cooldown_is_local_to_its_group(tmp_path: Path, clock: ControlledClock) -> None:
    class CoolingTransport:
        async def get_async(
            self,
            url: str,
            addresses: tuple[str, ...],
            maximum_bytes: int,
            deadline: float,
            selected_clock: Clock,
        ) -> Response:
            if "one.example.com" in url:
                return Response(429, (("Retry-After", "60"),), b"", 0)
            return plain()

    requests = (
        request(tmp_path, "limited", "one"),
        request(tmp_path, "later", "one"),
        request(tmp_path, "available", "two"),
    )
    batch = unwrap(
        download_batch(
            requests,
            tmp_path / "network",
            "assignment",
            clock=clock,
            resolver=FixedResolver(),
            transport=CoolingTransport(),
        )
    )
    assert not batch.complete
    assert isinstance(batch.items[0].result, Failure) and batch.items[0].result.code == "deferred"
    assert batch.items[1].attempted_requests == 0
    assert isinstance(batch.items[2].result, Success)


@pytest.mark.parametrize("restriction", ["cooldown", "quota"])
def test_existing_upstream_or_quota_deferral_does_not_wait_and_request(
    tmp_path: Path, clock: ControlledClock, restriction: str
) -> None:
    selected = request(tmp_path, "later", "one")
    if restriction == "quota":
        selected = replace(
            selected, budget=replace(selected.budget, period_seconds=5, group_requests=1)
        )
    network = tmp_path / "network"
    held = unwrap(reserve_budget(network, selected.budget, "earlier", 100, clock=clock))
    unwrap(
        settle_budget(
            network,
            selected.budget,
            held,
            0,
            3 if restriction == "cooldown" else 0,
            clock=clock,
        )
    )
    started = clock.monotonic()
    transport = RecordedTransport([plain()])
    batch = unwrap(
        download_batch(
            (selected,),
            network,
            "assignment",
            clock=clock,
            resolver=FixedResolver(),
            transport=transport,
        )
    )
    assert not batch.complete
    assert isinstance(batch.items[0].result, Failure)
    assert batch.items[0].result.code == "deferred"
    assert batch.items[0].attempted_requests == 0
    assert transport.urls == []
    assert clock.monotonic() == started
    assert not selected.destination.exists()


def test_separate_batches_wait_for_local_spacing_within_the_request_deadline(
    tmp_path: Path, clock: ControlledClock
) -> None:
    transport = RecordedTransport([plain(), plain()])
    started = clock.monotonic()
    for identity in ("first", "second"):
        selected = request(tmp_path, identity, "one", 5)
        completed = unwrap(
            download_batch(
                (selected,),
                tmp_path / "network",
                "assignment",
                clock=clock,
                resolver=FixedResolver(),
                transport=transport,
            )
        )
        assert completed.complete and completed.items[0].attempted_requests == 1
    assert clock.monotonic() - started == 5
    assert len(transport.urls) == 2


def test_existing_download_is_not_requested_again(tmp_path: Path, clock: ControlledClock) -> None:
    existing = request(tmp_path, "existing", "one")
    existing.destination.write_bytes(b"saved")
    transport = RecordedTransport([])
    batch = unwrap(
        download_batch(
            (existing,),
            tmp_path / "network",
            "assignment",
            clock=clock,
            resolver=FixedResolver(),
            transport=transport,
        )
    )
    assert not batch.complete and batch.items[0].attempted_requests == 0
    assert transport.urls == [] and existing.destination.read_bytes() == b"saved"


def test_duplicate_inputs_fail_before_any_network_request(
    tmp_path: Path, clock: ControlledClock
) -> None:
    same = request(tmp_path, "same", "one")
    transport = RecordedTransport([])
    result = download_batch(
        (same, same),
        tmp_path / "network",
        "assignment",
        clock=clock,
        resolver=FixedResolver(),
        transport=transport,
    )
    assert isinstance(result, Failure) and transport.urls == []


def test_shared_group_slot_prevents_another_process_from_overlapping(
    tmp_path: Path, clock: ControlledClock
) -> None:
    selected = request(tmp_path, "first", "one", 10)
    root = tmp_path / "network"
    first = unwrap(
        reserve_budget(root, selected.budget, "first-task", 100, clock=clock, deadline_seconds=30)
    )
    clock.advance(11)
    blocked = reserve_budget(
        root, selected.budget, "other-task", 100, clock=clock, deadline_seconds=30
    )
    assert isinstance(blocked, Failure) and blocked.code == "deferred"
    assert blocked.retry_after_seconds == 19
    unwrap(settle_budget(root, selected.budget, first, 50, clock=clock))
    assert isinstance(
        reserve_budget(root, selected.budget, "other-task", 100, clock=clock), Success
    )


def test_interrupted_group_recovers_after_deadline_without_refunding_unknown_usage(
    tmp_path: Path, clock: ControlledClock
) -> None:
    selected = request(tmp_path, "first", "one")
    root = tmp_path / "network"
    unwrap(
        reserve_budget(root, selected.budget, "assignment", 100, clock=clock, deadline_seconds=30)
    )
    clock.advance(31)
    unwrap(reserve_budget(root, selected.budget, "assignment", 100, clock=clock))
    status = unwrap(inspect_budget(root, selected.budget, "assignment", clock=clock))
    assert status.group_requests == 2 and status.group_bytes == 200
    assert status.pending_reservations == 1


def test_wall_clock_forward_does_not_release_an_active_request_early(
    tmp_path: Path, clock: ControlledClock
) -> None:
    selected = request(tmp_path, "first", "one")
    root = tmp_path / "network"
    unwrap(
        reserve_budget(root, selected.budget, "assignment", 100, clock=clock, deadline_seconds=30)
    )
    clock.current_wall += 3600
    blocked = reserve_budget(root, selected.budget, "assignment", 100, clock=clock)
    assert isinstance(blocked, Failure) and blocked.code == "deferred"
    assert blocked.retry_after_seconds == 30
    clock.advance(31)
    assert isinstance(
        reserve_budget(root, selected.budget, "assignment", 100, clock=clock), Success
    )
