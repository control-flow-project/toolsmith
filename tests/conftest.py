from dataclasses import dataclass
from pathlib import Path

import pytest

from toolsmith.result import unwrap
from toolsmith.storage.database import initialize_store


@dataclass
class ControlledClock:
    current_wall: float = 1_800_000_000
    current_monotonic: float = 100

    def wall(self) -> float:
        return self.current_wall

    def monotonic(self) -> float:
        return self.current_monotonic

    def advance(self, seconds: float) -> None:
        self.current_wall += seconds
        self.current_monotonic += seconds

    async def wait(self, seconds: float) -> None:
        self.advance(seconds)


@pytest.fixture
def clock() -> ControlledClock:
    return ControlledClock()


@pytest.fixture
def store(tmp_path: Path, clock: ControlledClock) -> Path:
    root = tmp_path / "store"
    unwrap(initialize_store(root, "sample", clock=clock))
    return root
