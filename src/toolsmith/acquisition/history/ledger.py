"""Canonical input, attempt and coverage records. No source adapters or converters."""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from toolsmith.files import absolute_path, directory_lock, private_directory
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.validation import canonical_json, fields, text, timestamp

from .contracts import Acquisition, Gap
from .ranges import DateRange, TimeRange
from .records import Record, read_record, write_record


def scope_value(value: DateRange | TimeRange) -> dict[str, object]:
    return {
        "unit": "date" if isinstance(value, DateRange) else "instant",
        "start": value.start.isoformat(),
        "end": value.end.isoformat(),
    }


def scope_read(value: object) -> DateRange | TimeRange:
    row = fields(value, {"unit", "start", "end"})
    first, last = text(row["start"], 64, "Range start"), text(row["end"], 64, "Range end")
    try:
        if row["unit"] == "date":
            return DateRange(date.fromisoformat(first), date.fromisoformat(last))
        if row["unit"] == "instant":
            return TimeRange(datetime.fromisoformat(first), datetime.fromisoformat(last))
    except ValueError as error:
        raise ToolsmithError("invalid_input", "Coverage endpoints have invalid syntax") from error
    raise ToolsmithError("invalid_input", "Unknown acquisition coverage unit")


def acquisition_value(value: Acquisition) -> dict[str, object]:
    return {
        "identity": value.identity,
        "source": value.source,
        "item": value.item,
        "observed_at": value.observed_at,
        "outcome": value.outcome,
        "originals": list(value.originals),
        "complete": [scope_value(v) for v in value.complete],
        "provisional": [scope_value(v) for v in value.provisional],
        "reason": value.reason,
        "bytes": value.bytes,
        "requests": value.requests,
        "elapsed_seconds": value.elapsed_seconds,
        "evidence": value.evidence,
        "discovery_complete": value.discovery_complete,
        "assignment": value.assignment,
        "unresolved": [
            {
                "scope": None if gap.scope is None else scope_value(gap.scope),
                "outcome": gap.outcome,
                "reason": gap.reason,
            }
            for gap in value.unresolved
        ],
    }


def acquisition_read(value: object) -> Acquisition:
    from typing import cast

    from .contracts import OUTCOMES, Outcome

    row = fields(
        value,
        {
            "identity",
            "source",
            "item",
            "observed_at",
            "outcome",
            "originals",
            "complete",
            "provisional",
            "reason",
            "bytes",
            "requests",
            "elapsed_seconds",
            "evidence",
            "discovery_complete",
            "assignment",
            "unresolved",
        },
    )
    if (
        not isinstance(row["originals"], list)
        or not isinstance(row["complete"], list)
        or not isinstance(row["provisional"], list)
        or not isinstance(row["evidence"], dict)
        or not isinstance(row["outcome"], str)
        or row["outcome"] not in OUTCOMES
    ):
        raise ToolsmithError("invalid_input", "Acquisition fields are invalid")
    if (
        type(row["bytes"]) is not int
        or row["requests"] is not None
        and type(row["requests"]) is not int
        or row["elapsed_seconds"] is not None
        and not isinstance(row["elapsed_seconds"], int | float)
        or type(row["discovery_complete"]) is not bool
    ):
        raise ToolsmithError("invalid_input", "Acquisition measurements are invalid")
    if row["reason"] is not None and not isinstance(row["reason"], str):
        raise ToolsmithError("invalid_input", "Acquisition reason is invalid")
    if not isinstance(row["unresolved"], list):
        raise ToolsmithError("invalid_input", "Unresolved acquisition observations must be a list")
    unresolved = []
    for raw in row["unresolved"]:
        gap = fields(raw, {"scope", "outcome", "reason"})
        if not isinstance(gap["outcome"], str) or gap["outcome"] not in OUTCOMES:
            raise ToolsmithError("invalid_input", "Gap outcome is invalid")
        unresolved.append(
            Gap(
                None if gap["scope"] is None else scope_read(gap["scope"]),
                cast(Outcome, gap["outcome"]),
                text(gap["reason"], 2000, "Gap reason"),
            )
        )
    return Acquisition(
        identity=text(row["identity"], 4096, "Request"),
        source=text(row["source"], 4096, "Source"),
        item=text(row["item"], 4096, "Item"),
        observed_at=text(row["observed_at"], 64, "Observed at"),
        outcome=cast(Outcome, row["outcome"]),
        originals=tuple(text(v, 4096, "Original") for v in row["originals"]),
        complete=tuple(scope_read(v) for v in row["complete"]),
        provisional=tuple(scope_read(v) for v in row["provisional"]),
        reason=row["reason"],
        bytes=row["bytes"],
        requests=row["requests"],
        elapsed_seconds=None if row["elapsed_seconds"] is None else float(row["elapsed_seconds"]),
        evidence={key: val for key, val in row["evidence"].items()},
        discovery_complete=row["discovery_complete"],
        assignment=None
        if row["assignment"] is None
        else text(row["assignment"], 4096, "Acquisition assignment"),
        unresolved=tuple(unresolved),
    )


@dataclass(frozen=True)
class Attempt:
    identity: str
    source: str
    item: str
    assignment: str
    observed_at: str
    phase: Literal["acquisition", "discovery"]
    outcome: Literal["complete", "failed", "unavailable", "discovery-unknown"]
    reason: str

    def __post_init__(self) -> None:
        for label, value in (
            ("Request", self.identity),
            ("Source", self.source),
            ("Item", self.item),
            ("Assignment", self.assignment),
            ("Reason", self.reason),
        ):
            text(value, 4096, label)
        timestamp(self.observed_at)
        if self.phase not in {"acquisition", "discovery"} or self.outcome not in {
            "complete",
            "failed",
            "unavailable",
            "discovery-unknown",
        }:
            raise ToolsmithError("invalid_input", "Invalid acquisition attempt phase/outcome")


@dataclass(frozen=True)
class Coverage:
    source: str
    item: str
    identity: str
    scope: DateRange | TimeRange
    evidence: dict[str, object]

    def __post_init__(self) -> None:
        for label, value in (
            ("Source", self.source),
            ("Item", self.item),
            ("Coverage", self.identity),
        ):
            text(value, 4096, label)
        if not isinstance(self.scope, DateRange | TimeRange) or not isinstance(self.evidence, dict):
            raise ToolsmithError(
                "invalid_input", "Coverage needs a typed extent and native evidence"
            )
        canonical_json(self.evidence)


@dataclass(frozen=True)
class Ledger:
    root: Path

    def __post_init__(self) -> None:
        absolute_path(self.root)

    @staticmethod
    def _exists(path: Path) -> bool:
        try:
            path.lstat()
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def _files(path: Path) -> tuple[Path, ...]:
        try:
            with private_directory(path):
                return tuple(sorted(path.glob("*.json")))
        except FileNotFoundError:
            return ()

    def path(self, kind: str, source: str, item: str, key: str | None = None) -> Path:
        if kind not in {"inputs", "attempts", "coverage"}:
            raise ToolsmithError("invalid_input", "Select an acquisition ledger record kind")
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ToolsmithError("invalid_input", "Choose an explicit absolute acquisition ledger")
        text(source, 4096, "Source")
        text(item, 4096, "Item")
        if key is not None:
            text(key, 16384, "Ledger record key")
        source_key = hashlib.sha256(source.encode()).hexdigest()
        item_key = hashlib.sha256(item.encode()).hexdigest()
        folder = self.root / kind / source_key / item_key
        return (
            folder if key is None else folder / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        )

    def _publish(self, path: Path, kind: str, value: dict[str, object]) -> None:
        with private_directory(path.parent, create=True):
            pass
        unwrap(write_record(path, Record(kind, str(path.relative_to(self.root)), value)))

    def _read(self, path: Path, kind: str) -> dict[str, object]:
        return unwrap(read_record(path, category=kind, key=str(path.relative_to(self.root)))).value

    @boundary
    def save(self, value: Acquisition) -> None:
        if (
            not isinstance(value, Acquisition)
            or value.outcome not in {"complete", "provisional"}
            or not value.originals
        ):
            raise ToolsmithError(
                "invalid_input", "Only retained original observations enter the input catalogue"
            )
        path = self.path("inputs", value.source, value.item, value.identity)
        with private_directory(path.parent, create=True) as directory, directory_lock(directory):
            previous = (
                acquisition_read(self._read(path, "acquisition")) if self._exists(path) else None
            )
            if previous is not None and acquisition_value(previous) == acquisition_value(value):
                return
            if previous is None or datetime.fromisoformat(
                value.observed_at
            ) >= datetime.fromisoformat(previous.observed_at):
                self._publish(path, "acquisition", acquisition_value(value))

    @boundary
    def lookup(self, source: str, item: str, key: str) -> Acquisition | None:
        path = self.path("inputs", source, item, key)
        if not self._exists(path):
            return None
        value = acquisition_read(self._read(path, "acquisition"))
        if (value.source, value.item, value.identity) != (source, item, key):
            raise ToolsmithError("integrity", "Acquisition catalogue identity differs")
        return value

    @boundary
    def inputs(self, source: str, item: str) -> tuple[Acquisition, ...]:
        result = tuple(
            acquisition_read(self._read(path, "acquisition"))
            for path in self._files(self.path("inputs", source, item))
        )
        if any((value.source, value.item) != (source, item) for value in result):
            raise ToolsmithError("integrity", "Acquisition item catalogue differs")
        return result

    @boundary
    def attempt(self, value: Attempt) -> None:
        from dataclasses import asdict

        path = self.path(
            "attempts",
            value.source,
            value.item,
            value.identity + ":" + value.assignment + ":" + value.observed_at,
        )
        self._publish(path, "acquisition-attempt", asdict(value))

    @boundary
    def attempts(self, source: str, item: str, key: str) -> tuple[Attempt, ...]:
        result = []
        for path in self._files(self.path("attempts", source, item)):
            row = self._read(path, "acquisition-attempt")
            if (row.get("source"), row.get("item")) != (source, item):
                raise ToolsmithError("integrity", "Attempt differs from the selected source/item")
            if row["identity"] != key:
                continue
            phase, outcome = row["phase"], row["outcome"]
            if phase not in {"acquisition", "discovery"} or outcome not in {
                "complete",
                "failed",
                "unavailable",
                "discovery-unknown",
            }:
                raise ToolsmithError("invalid_input", "Attempt phase/outcome differs")
            result.append(
                Attempt(
                    text(row["identity"], 4096, "Request"),
                    text(row["source"], 4096, "Source"),
                    text(row["item"], 4096, "Item"),
                    text(row["assignment"], 4096, "Assignment"),
                    text(row["observed_at"], 64, "Observed at"),
                    phase,
                    outcome,
                    text(row["reason"], 4096, "Reason"),
                )
            )
        return tuple(sorted(result, key=lambda v: datetime.fromisoformat(v.observed_at)))

    @boundary
    def cover(self, value: Coverage) -> None:
        self._publish(
            self.path("coverage", value.source, value.item, value.identity),
            "coverage",
            {
                "source": value.source,
                "item": value.item,
                "identity": value.identity,
                "scope": scope_value(value.scope),
                "evidence": value.evidence,
            },
        )

    @boundary
    def coverage(self, source: str, item: str) -> tuple[Coverage, ...]:
        result = []
        for path in self._files(self.path("coverage", source, item)):
            row = self._read(path, "coverage")
            if (
                row["source"] != source
                or row["item"] != item
                or not isinstance(row["evidence"], dict)
            ):
                raise ToolsmithError(
                    "integrity", "Coverage identity differs from its selected owner"
                )
            result.append(
                Coverage(
                    source,
                    item,
                    text(row["identity"], 4096, "Coverage"),
                    scope_read(row["scope"]),
                    {key: value for key, value in row["evidence"].items()},
                )
            )
        return tuple(result)
