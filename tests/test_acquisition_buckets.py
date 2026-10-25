import asyncio

import pytest

from toolsmith.acquisition.buckets import Bucket, run_buckets_async
from toolsmith.result import Failure, unwrap


class ControlledClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waiting: asyncio.Queue[tuple[float, asyncio.Future[None]]] = asyncio.Queue()

    def wall(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    async def wait(self, seconds: float) -> None:
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.waiting.put_nowait((self.now + seconds, ready))
        await ready


def test_one_hundred_selections_run_in_five_parallel_serial_throttled_buckets() -> None:
    async def exercise() -> None:
        clock = ControlledClock()
        arrived: asyncio.Queue[tuple[int, int, float]] = asyncio.Queue()
        releases = [asyncio.Event() for _ in range(20)]
        buckets = tuple(
            Bucket(str(group), tuple((group, item) for item in range(20)), 10) for group in range(5)
        )

        async def acquire(item: tuple[int, int]) -> str:
            group, index = item
            arrived.put_nowait((group, index, clock.monotonic()))
            await releases[index].wait()
            return f"{group}:{index}"

        async with asyncio.timeout(5):
            running = asyncio.create_task(run_buckets_async(buckets, acquire, clock=clock))
            for index in range(20):
                starts = [await arrived.get() for _ in range(5)]
                assert {value[0] for value in starts} == set(range(5))
                assert {value[1] for value in starts} == {index}
                assert {value[2] for value in starts} == {index * 10}
                releases[index].set()
                if index < 19:
                    waiting = [await clock.waiting.get() for _ in range(5)]
                    assert {ready_at for ready_at, _ in waiting} == {(index + 1) * 10}
                    clock.now += 10
                    for _, ready in waiting:
                        ready.set_result(None)
            results = unwrap(await running)
        assert len(results) == 5
        assert sum(len(bucket.items) for bucket in results) == 100
        for group, bucket in enumerate(results):
            assert bucket.items == tuple(f"{group}:{index}" for index in range(20))

    asyncio.run(exercise())


@pytest.mark.parametrize("spacing", [-1, float("nan"), float("inf"), True])
def test_invalid_throttles_fail_before_an_operation(spacing: float) -> None:
    async def acquire(value: int) -> int:
        raise AssertionError("Invalid throttle reached acquisition")

    result = asyncio.run(run_buckets_async((Bucket("group", (1,), spacing),), acquire))
    assert isinstance(result, Failure) and result.code == "invalid_input"


def test_group_aliases_cannot_create_two_parallel_buckets() -> None:
    async def acquire(value: int) -> int:
        raise AssertionError("Duplicate group reached acquisition")

    result = asyncio.run(
        run_buckets_async((Bucket("group", (1,), 10), Bucket("group", (2,), 10)), acquire)
    )
    assert isinstance(result, Failure)


def test_failure_in_one_operation_cancels_and_joins_other_workers() -> None:
    async def exercise() -> None:
        entered = asyncio.Event()
        finished = asyncio.Event()

        async def acquire(value: int) -> int:
            if value == 1:
                await entered.wait()
                raise RuntimeError("Controlled unexpected producer failure")
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()
            return value

        with pytest.raises(ExceptionGroup):
            await run_buckets_async((Bucket("first", (1,), 0), Bucket("second", (2,), 0)), acquire)
        assert finished.is_set()

    asyncio.run(exercise())
