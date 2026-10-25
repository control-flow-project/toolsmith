import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from toolsmith.clock import Clock, SystemClock
from toolsmith.result import ToolsmithError, async_boundary
from toolsmith.validation import text


@dataclass(frozen=True)
class Bucket[Item]:
    id: str
    items: tuple[Item, ...]
    minimum_interval_seconds: float


@dataclass(frozen=True)
class BucketResult[Value]:
    id: str
    items: tuple[Value, ...]


@async_boundary
async def run_buckets_async[Item, Value](
    buckets: tuple[Bucket[Item], ...],
    operation: Callable[[Item], Awaitable[Value]],
    *,
    clock: Clock | None = None,
) -> tuple[BucketResult[Value], ...]:
    if not isinstance(buckets, tuple) or not callable(operation):
        raise ToolsmithError("invalid_input", "Supply typed buckets and an asynchronous operation")
    identities: set[str] = set()
    for bucket in buckets:
        if not isinstance(bucket, Bucket) or not isinstance(bucket.items, tuple):
            raise ToolsmithError("invalid_input", "Supply typed buckets with tuple inputs")
        identity = text(bucket.id, 300, "Bucket id")
        if identity in identities:
            raise ToolsmithError("invalid_input", "Bucket ids must be unique")
        pacing = bucket.minimum_interval_seconds
        if (
            isinstance(pacing, bool)
            or not isinstance(pacing, (int, float))
            or not math.isfinite(pacing)
            or pacing < 0
        ):
            raise ToolsmithError("invalid_input", "Bucket spacing must be finite and nonnegative")
        identities.add(identity)
    selected_clock = clock or SystemClock()

    async def run_bucket(bucket: Bucket[Item]) -> BucketResult[Value]:
        values: list[Value] = []
        ready = selected_clock.monotonic()
        for item in bucket.items:
            while (remaining := ready - selected_clock.monotonic()) > 0:
                await selected_clock.wait(remaining)
            started = selected_clock.monotonic()
            ready = started + bucket.minimum_interval_seconds
            values.append(await operation(item))
        return BucketResult(bucket.id, tuple(values))

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(run_bucket(bucket)) for bucket in buckets]
    return tuple(task.result() for task in tasks)
