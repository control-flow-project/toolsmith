"""Source-neutral accounting; missing measurements remain unknown."""

from dataclasses import dataclass, field

from toolsmith.result import ToolsmithError
from toolsmith.validation import number

from .contracts import Acquisition, Decision, Outcome


@dataclass
class Totals:
    attempted: int = 0
    reused: int = 0
    complete: int = 0
    provisional: int = 0
    failed: int = 0
    unavailable: int = 0
    requests: int = 0
    request_measurements_complete: bool = True
    downloaded_bytes: int = 0
    elapsed_seconds: float = 0.0

    def add(self, decision: Decision, acquisition: Acquisition | None) -> None:
        if not isinstance(decision, Decision):
            raise ToolsmithError("invalid_input", "Progress requires an acquisition decision")
        if decision.action == "blocked":
            return
        if acquisition is not None and (
            acquisition.identity,
            acquisition.source,
            acquisition.item,
        ) != (decision.request.identity, decision.request.source, decision.request.item):
            raise ToolsmithError("integrity", "Outcome differs from the planned native request")
        self.attempted += 1
        if decision.action == "reuse" and (
            acquisition is None or acquisition.outcome in {"complete", "provisional"}
        ):
            self.reused += 1
            return
        if acquisition is None:
            self.failed += 1
            self.request_measurements_complete = False
            return
        if acquisition.outcome == "complete":
            self.complete += 1
        elif acquisition.outcome == "provisional":
            self.provisional += 1
        elif acquisition.outcome == "unavailable":
            self.unavailable += 1
        else:
            self.failed += 1
        self.request_measurements_complete &= acquisition.requests is not None
        self.requests += acquisition.requests or 0
        self.downloaded_bytes += acquisition.bytes
        self.elapsed_seconds += acquisition.elapsed_seconds or 0

    def report(self, *, wall_seconds: float) -> dict[str, object]:
        from dataclasses import asdict

        number(wall_seconds, 0, float("inf"), "Invocation wall duration")
        return {
            **asdict(self),
            "wall_seconds": wall_seconds,
            "critical": self.failed > 0 and self.failed * 5 >= self.attempted,
        }


@dataclass
class Accounting:
    """One per-stream accounting owner shared by every native execution adapter."""

    streams: dict[str, Totals] = field(default_factory=dict)
    discovery_requests: int = 0
    payload_requests: int = 0

    def observe(
        self,
        decision: Decision,
        *,
        outcome: Outcome,
        observed_at: str,
        requests: int | None,
        downloaded_bytes: int,
        elapsed_seconds: float,
    ) -> None:
        request = decision.request
        result = Acquisition(
            request.identity,
            request.source,
            request.item,
            observed_at,
            outcome,
            bytes=downloaded_bytes,
            requests=requests,
            elapsed_seconds=elapsed_seconds,
        )
        self.streams.setdefault(request.source, Totals()).add(decision, result)
        if request.discovery:
            self.discovery_requests += requests or 0
        else:
            self.payload_requests += requests or 0

    def report(
        self, *, wall_seconds: float, preparation_requests: int = 0, preparation_bytes: int = 0
    ) -> dict[str, object]:
        from toolsmith.validation import integer

        integer(preparation_requests, 0, 2**63 - 1, "Preparation requests")
        integer(preparation_bytes, 0, 2**63 - 1, "Preparation bytes")
        number(wall_seconds, 0, float("inf"), "Invocation wall duration")
        return {
            "streams": {
                source: value.report(wall_seconds=wall_seconds)
                for source, value in self.streams.items()
            },
            "preparation_requests": preparation_requests,
            "preparation_bytes": preparation_bytes,
            "discovery_requests": self.discovery_requests,
            "payload_requests": self.payload_requests,
            "network_requests": preparation_requests
            + sum(value.requests for value in self.streams.values()),
            "downloaded_bytes": preparation_bytes
            + sum(value.downloaded_bytes for value in self.streams.values()),
            "network_requests_complete": all(
                value.request_measurements_complete for value in self.streams.values()
            ),
            "wall_seconds": wall_seconds,
        }
