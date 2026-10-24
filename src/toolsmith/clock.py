import asyncio
import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def wall(self) -> float: ...
    def monotonic(self) -> float: ...
    async def wait(self, seconds: float) -> None: ...


class SystemClock:
    def wall(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    async def wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def utc_now(clock: Clock) -> str:
    return datetime.fromtimestamp(clock.wall(), UTC).isoformat()
