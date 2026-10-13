import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from toolsmith.result import unwrap
from toolsmith.semantic import Source, initialize_index, prepare_embedding, publish_embedding


class FixtureEncoder:
    def __init__(self, on_encode: Callable[[], None] | None = None) -> None:
        self.on_encode = on_encode
        self.calls = 0

    def __enter__(self) -> "FixtureEncoder":
        return self

    def __exit__(self, *arguments: object) -> None:
        pass

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((match.start(), match.end()) for match in re.finditer(r"\S+", text))

    def tokens(self, text: str) -> int:
        return len(self.offsets(text)) + 2

    def encode(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls += 1
        if self.on_encode is not None:
            callback, self.on_encode = self.on_encode, None
            callback()
        output = []
        for body in texts:
            if self.tokens(body) > 256:
                raise ValueError("Fixture detected unsafe token truncation")
            axis = 0 if any(word in body.lower() for word in ("rain", "wet")) else 1
            output.append(tuple(float(index == axis) for index in range(384)))
        return tuple(output)


@contextmanager
def index_database() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        unwrap(initialize_index(connection))
        yield connection
    finally:
        connection.close()


def publish(connection: sqlite3.Connection, source: Source, previous: str | None = None) -> bool:
    return unwrap(
        publish_embedding(
            connection,
            unwrap(prepare_embedding(source, FixtureEncoder())),
            source,
            "2026-10-13T00:00:00Z",
            expected_digest=previous,
        )
    )
