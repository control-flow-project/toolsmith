"""One source-neutral acquisition vocabulary; native descriptors stay opaque data."""

from dataclasses import dataclass, field
from typing import Literal

from toolsmith.result import ToolsmithError
from toolsmith.validation import json_value, text, timestamp

from .ranges import DateRange, TimeRange

type Outcome = Literal[
    "complete",
    "provisional",
    "missing",
    "failed",
    "unavailable",
    "discovery-unknown",
    "not-yet-due",
]
type Action = Literal["reuse", "download", "refresh", "discover", "blocked"]
OUTCOMES = frozenset(
    {
        "complete",
        "provisional",
        "missing",
        "failed",
        "unavailable",
        "discovery-unknown",
        "not-yet-due",
    }
)


@dataclass(frozen=True)
class NativeRequest:
    identity: str
    source: str
    item: str
    native: dict[str, object]
    scope: DateRange | TimeRange | None = None
    discovery: bool = False
    due: bool = True
    reason: str | None = None
    fresh_after: str | None = None
    expected: tuple[DateRange | TimeRange, ...] | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("Request", self.identity),
            ("Source", self.source),
            ("Item", self.item),
        ):
            text(value, 4096, label)
        if not isinstance(self.native, dict):
            raise ToolsmithError("invalid_input", "Native requests require a JSON object")
        json_value(self.native)
        if self.scope is not None and not isinstance(self.scope, DateRange | TimeRange):
            raise ToolsmithError("invalid_input", "Request scope must be a typed range or absent")
        if type(self.discovery) is not bool or type(self.due) is not bool:
            raise ToolsmithError("invalid_input", "Discovery/due flags must be Boolean")
        if self.fresh_after is not None:
            timestamp(self.fresh_after)
        if self.expected is not None and (
            not isinstance(self.expected, tuple)
            or self.scope is None
            or any(
                not isinstance(v, type(self.scope))
                or v.start < self.scope.start
                or v.end > self.scope.end
                for v in self.expected
            )
        ):
            raise ToolsmithError(
                "invalid_input", "Expected coverage must stay within its native request scope/unit"
            )
        if self.reason is not None:
            text(self.reason, 2000, "Request reason")


@dataclass(frozen=True)
class Acquisition:
    identity: str
    source: str
    item: str
    observed_at: str
    outcome: Outcome
    originals: tuple[str, ...] = ()
    complete: tuple[DateRange | TimeRange, ...] = ()
    provisional: tuple[DateRange | TimeRange, ...] = ()
    reason: str | None = None
    bytes: int = 0
    requests: int | None = None
    elapsed_seconds: float | None = None
    evidence: dict[str, object] = field(default_factory=dict)
    discovery_complete: bool = False
    assignment: str | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("Request", self.identity),
            ("Source", self.source),
            ("Item", self.item),
        ):
            text(value, 4096, label)
        timestamp(text(self.observed_at, 64, "Observed at"))
        if self.outcome not in OUTCOMES:
            raise ToolsmithError("invalid_input", "Unknown acquisition outcome")
        if not isinstance(self.originals, tuple) or any(
            not isinstance(v, str) for v in self.originals
        ):
            raise ToolsmithError(
                "invalid_input", "Original references must be a tuple of identities"
            )
        if type(self.bytes) is not int or self.bytes < 0:
            raise ToolsmithError("invalid_input", "Acquired bytes must be nonnegative")
        if self.requests is not None and (type(self.requests) is not int or self.requests < 0):
            raise ToolsmithError(
                "invalid_input", "Request measurements must be nonnegative or unknown"
            )
        if self.elapsed_seconds is not None:
            from toolsmith.validation import number

            number(self.elapsed_seconds, 0, float("inf"), "Acquisition duration")
        if any(
            not isinstance(v, DateRange | TimeRange) for v in (*self.complete, *self.provisional)
        ):
            raise ToolsmithError("invalid_input", "Coverage requires typed ranges")
        if self.complete and self.outcome not in {"complete", "provisional"}:
            raise ToolsmithError("invalid_input", "Failed/unknown outcomes cannot prove completion")
        if self.assignment is not None:
            text(self.assignment, 4096, "Acquisition assignment")
        if not isinstance(self.evidence, dict) or type(self.discovery_complete) is not bool:
            raise ToolsmithError("invalid_input", "Acquisition evidence/discovery flags differ")
        json_value(self.evidence)


@dataclass(frozen=True)
class Decision:
    request: NativeRequest
    action: Action
    outcome: Outcome
    reason: str
    retained: Acquisition | None
    missing: tuple[DateRange | TimeRange, ...]
    available: tuple[Acquisition, ...] = ()
