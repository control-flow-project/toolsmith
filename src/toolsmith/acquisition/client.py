import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from toolsmith.acquisition.budgets import (
    BudgetPolicy,
    reserve_budget_async,
    settle_budget,
    validate_policy,
)
from toolsmith.acquisition.transport import (
    NativeResolver,
    NativeTransport,
    Resolver,
    Response,
    Transport,
    one_header,
    remaining,
)
from toolsmith.acquisition.urls import canonical_url, hostname, public_address
from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.files import absolute_path
from toolsmith.result import ToolsmithError, async_boundary, boundary, unwrap
from toolsmith.validation import integer, number


@dataclass(frozen=True)
class HttpPolicy:
    hosts: tuple[str, ...]
    maximum_response_bytes: int = 1024 * 1024
    maximum_total_bytes: int = 64 * 1024 * 1024
    maximum_requests: int = 5
    maximum_redirects: int = 3
    deadline_seconds: float = 30


@dataclass(frozen=True)
class FetchResponse:
    final_url: str
    media_type: str
    content: bytes
    requests: int
    wire_bytes: int
    received_at: str


def validate_http_policy(policy: HttpPolicy) -> HttpPolicy:
    if (
        not isinstance(policy, HttpPolicy)
        or not isinstance(policy.hosts, tuple)
        or not 1 <= len(policy.hosts) <= 32
    ):
        raise ToolsmithError("invalid_input", "Supply one to 32 explicit approved HTTPS hosts")
    for host in policy.hosts:
        hostname(host)
    if len(set(policy.hosts)) != len(policy.hosts):
        raise ToolsmithError("invalid_input", "Approved hosts must be unique")
    response_bytes = integer(policy.maximum_response_bytes, 1, 128 * 1024 * 1024, "Response bytes")
    integer(policy.maximum_total_bytes, response_bytes, 2**63 - 1, "Total wire bytes")
    integer(policy.maximum_requests, 1, 100, "Maximum requests")
    integer(policy.maximum_redirects, 0, 10, "Maximum redirects")
    number(policy.deadline_seconds, 0.1, 60, "Deadline seconds")
    return HttpPolicy(
        tuple(sorted(hostname(host) for host in policy.hosts)),
        response_bytes,
        policy.maximum_total_bytes,
        policy.maximum_requests,
        policy.maximum_redirects,
        number(policy.deadline_seconds, 0.1, 60, "Deadline seconds"),
    )


def retry_after(response: Response, clock: Clock) -> float | None:
    value = one_header(response.headers, "retry-after")
    if value is None:
        return 60 if response.status == 429 else 0
    if value.isascii() and value.isdecimal():
        delay = float(value)
    else:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return 60 if response.status == 429 else 0
            delay = max(0, date.timestamp() - clock.wall())
        except (ValueError, TypeError, OverflowError):
            return 60 if response.status == 429 else 0
    return delay if math.isfinite(delay) and delay <= 2**53 - clock.wall() else None


@async_boundary
async def fetch_http_async(
    url: str,
    policy: HttpPolicy,
    network_state: Path,
    budget: BudgetPolicy,
    task: str,
    *,
    clock: Clock | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
    remaining_requests: int | None = None,
    before_request: Callable[[], None] | None = None,
    network_limit: asyncio.Semaphore | None = None,
    expected_configuration_digest: str | None = None,
) -> FetchResponse:
    current = canonical_url(url)
    checked, quota = validate_http_policy(policy), validate_policy(budget)
    absolute_path(network_state)
    allowance = (
        checked.maximum_requests
        if remaining_requests is None
        else integer(
            remaining_requests,
            0,
            checked.maximum_requests,
            "Remaining requests",
        )
    )
    actual_clock = clock or SystemClock()
    selected_resolver, selected_transport = (
        resolver or NativeResolver(),
        transport or NativeTransport(),
    )
    limiter = network_limit if network_limit is not None else asyncio.Semaphore(1)
    deadline = actual_clock.monotonic() + checked.deadline_seconds
    requests, redirects, used_total = 0, 0, 0
    while True:
        remaining(deadline, actual_clock)
        if urlsplit(current).hostname not in checked.hosts:
            raise ToolsmithError("denied", "Request or redirect host is not explicitly approved")
        if requests >= allowance or used_total >= checked.maximum_total_bytes:
            raise ToolsmithError(
                "limit", "The supplied operation request or byte allowance is exhausted"
            )
        try:
            async with asyncio.timeout(remaining(deadline, actual_clock)), limiter:
                addresses = await selected_resolver.resolve_async(
                    urlsplit(current).hostname or "", deadline, actual_clock
                )
        except TimeoutError as error:
            raise ToolsmithError("limit", "The explicit network deadline was exhausted") from error
        if not 1 <= len(addresses) <= 64:
            raise ToolsmithError("denied", "DNS must return a bounded nonempty public address set")
        pinned = tuple(public_address(address) for address in addresses)
        remaining(deadline, actual_clock)
        maximum = min(checked.maximum_response_bytes, checked.maximum_total_bytes - used_total)
        reservation = unwrap(
            await reserve_budget_async(
                network_state,
                quota,
                task,
                maximum,
                clock=actual_clock,
                deadline_seconds=min(60, remaining(deadline, actual_clock)),
                expected_configuration_digest=expected_configuration_digest,
            )
        )
        try:
            async with asyncio.timeout(remaining(deadline, actual_clock)), limiter:
                if before_request is not None:
                    before_request()
                requests += 1
                response = await selected_transport.get_async(
                    current, pinned, maximum, deadline, actual_clock
                )
        except TimeoutError as error:
            raise ToolsmithError("limit", "The explicit network deadline was exhausted") from error
        remaining(deadline, actual_clock)
        if (
            not isinstance(response, Response)
            or not isinstance(response.content, bytes)
            or len(response.content) > maximum
        ):
            raise ToolsmithError("limit", "Transport exceeded the approved expanded response bound")
        status = integer(response.status, 100, 599, "HTTP status")
        used = integer(response.wire_bytes, 0, maximum, "Wire bytes")
        used_total += used
        cooldown = retry_after(response, actual_clock)
        unwrap(settle_budget(network_state, quota, reservation, used, cooldown, clock=actual_clock))
        if status in {429, 503} and (cooldown is None or cooldown > 0):
            raise ToolsmithError(
                "deferred", "Upstream requested a cooldown; no automatic retry occurred", cooldown
            )
        if status in {301, 302, 303, 307, 308}:
            location = one_header(response.headers, "location")
            if location is None or redirects >= checked.maximum_redirects:
                raise ToolsmithError("http", "Redirect lacks a location or exceeds its bound")
            current = canonical_url(urljoin(current, location))
            redirects += 1
            continue
        if status != 200:
            raise ToolsmithError("http", "Approved source returned HTTP status " + str(status))
        media_type = (
            (one_header(response.headers, "content-type") or "application/octet-stream")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return FetchResponse(
            current, media_type, response.content, requests, used_total, utc_now(actual_clock)
        )


@boundary
def fetch_http(
    url: str,
    policy: HttpPolicy,
    network_state: Path,
    budget: BudgetPolicy,
    task: str,
    *,
    clock: Clock | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
    remaining_requests: int | None = None,
    before_request: Callable[[], None] | None = None,
    expected_configuration_digest: str | None = None,
) -> FetchResponse:
    return unwrap(
        asyncio.run(
            fetch_http_async(
                url,
                policy,
                network_state,
                budget,
                task,
                clock=clock,
                resolver=resolver,
                transport=transport,
                remaining_requests=remaining_requests,
                before_request=before_request,
                expected_configuration_digest=expected_configuration_digest,
            )
        )
    )
