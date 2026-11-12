"""Finite backward-frontier coordination over caller-owned native operations."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from toolsmith.acquisition.buckets import Bucket, run_buckets_async
from toolsmith.result import ToolsmithError, async_boundary, unwrap
from toolsmith.validation import integer

from .contracts import NativeRequest


@dataclass(frozen=True)
class WorkItem[Payload]:
    key: str
    group: str
    request: NativeRequest
    payload: Payload


@dataclass(frozen=True)
class Expansion[Payload]:
    items: tuple[WorkItem[Payload], ...] = ()
    withdraw: tuple[str, ...] = ()
    finished: tuple[str, ...] | None = None
    stop: bool = False


@async_boundary
async def run_frontiers_async[Payload](
    items: tuple[WorkItem[Payload], ...],
    operation: Callable[[tuple[WorkItem[Payload], ...]], Awaitable[Expansion[Payload]]],
    *,
    block_days: int = 31,
    maximum_concurrency: int = 4,
) -> dict[str, object]:
    """All streams finish an attempted block before the shared frontier moves.

    Wide native requests run once in their newest block. Discovered children
    join the same queue. An explicit failed/unavailable outcome is handled by
    operation and does not hold other streams forever. Operations retain their
    own bounded transport/provider effects; this introduces no transport or retry.
    """
    integer(block_days, 1, 36500, "Backward coordination days")
    integer(maximum_concurrency, 1, 64, "Publisher concurrency")
    if not isinstance(items, tuple) or not callable(operation):
        raise ToolsmithError("invalid_input", "Supply finite typed work and an explicit operation")
    known: dict[str, WorkItem[Payload]] = {}
    handled: set[str] = set()

    def add(values: tuple[WorkItem[Payload], ...]) -> None:
        if not isinstance(values, tuple):
            raise ToolsmithError("invalid_input", "Discovery must return a tuple of typed work")
        for value in values:
            if (
                not isinstance(value, WorkItem)
                or not value.key
                or not value.group
                or not isinstance(value.request, NativeRequest)
            ):
                raise ToolsmithError(
                    "invalid_input", "Invalid historical work identity or native request"
                )
            old = known.get(value.key)
            if old is not None and old != value:
                raise ToolsmithError(
                    "integrity", "One work identity cannot claim competing descriptors"
                )
            known[value.key] = value

    add(items)
    waves = 0
    while pending := [value for key, value in known.items() if key not in handled]:
        dated = [value.request.scope.end for value in pending if value.request.scope is not None]
        newest = max(v.date() if isinstance(v, datetime) else v for v in dated) if dated else None
        threshold = (
            None
            if newest is None
            else max(date.min, newest - timedelta(days=min(block_days - 1, newest.toordinal() - 1)))
        )
        wave = [
            value
            for value in pending
            if value.request.scope is None
            or threshold is None
            or (
                value.request.scope.end.date()
                if isinstance(value.request.scope.end, datetime)
                else value.request.scope.end
            )
            >= threshold
        ]
        # Enumerate listing parents before scheduling any payloads from their
        # previous membership; discovery may withdraw superseded children.
        if any(value.request.discovery for value in wave):
            wave = [value for value in wave if value.request.discovery]
        groups: dict[str, list[WorkItem[Payload]]] = {}
        for value in wave:
            groups.setdefault(value.group, []).append(value)

        async def process(batch: tuple[WorkItem[Payload], ...]) -> Expansion[Payload]:
            return await operation(batch)

        buckets = tuple(Bucket(group, (tuple(batch),), 0.0) for group, batch in groups.items())
        outcomes = unwrap(
            await run_buckets_async(buckets, process, maximum_concurrency=maximum_concurrency)
        )
        stopped = False
        for outcome in outcomes:
            for expansion in outcome.items:
                if not isinstance(expansion, Expansion):
                    raise ToolsmithError("invalid_input", "Discovery must return a typed expansion")
                batch_keys = {value.key for value in groups[outcome.id]}
                finished = batch_keys if expansion.finished is None else set(expansion.finished)
                if not finished <= batch_keys:
                    raise ToolsmithError(
                        "integrity", "Completed work differs from its assigned batch"
                    )
                handled.update(finished)
                stopped |= expansion.stop
                for key in expansion.withdraw:
                    known.pop(key, None)
                add(expansion.items)
        waves += 1
        if stopped:
            break
    return {
        "known_work": len(known),
        "handled_work": len(handled),
        "pending_work": len(set(known) - handled),
        "frontier_waves": waves,
        "block_days": block_days,
    }
