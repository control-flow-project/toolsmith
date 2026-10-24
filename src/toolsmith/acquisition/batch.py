import asyncio
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from toolsmith.acquisition.budgets import BudgetPolicy, common_definition, validate_policy
from toolsmith.acquisition.client import HttpPolicy, fetch_http_async, validate_http_policy
from toolsmith.acquisition.transport import Resolver, Transport
from toolsmith.acquisition.urls import canonical_url
from toolsmith.clock import Clock, SystemClock
from toolsmith.files import absolute_path, write_new_bytes
from toolsmith.result import Failure, Result, ToolsmithError, async_boundary, boundary, unwrap
from toolsmith.validation import identity, integer, number, text


@dataclass(frozen=True)
class DownloadRequest:
    id: str
    url: str
    destination: Path
    policy: HttpPolicy
    budget: BudgetPolicy


@dataclass(frozen=True)
class DownloadedFile:
    final_url: str
    path: str
    media_type: str
    content_bytes: int
    wire_bytes: int
    requests: int
    received_at: str


@dataclass(frozen=True)
class DownloadOutcome:
    id: str
    attempted_requests: int | None
    result: Result[DownloadedFile]


@dataclass(frozen=True)
class DownloadBatch:
    items: tuple[DownloadOutcome, ...]
    complete: bool
    elapsed_seconds: float


def validate_requests(requests: tuple[DownloadRequest, ...]) -> None:
    if not isinstance(requests, tuple):
        raise ToolsmithError("invalid_input", "Supply typed download requests")
    identities: set[str] = set()
    urls: set[str] = set()
    destinations: set[Path] = set()
    budgets: dict[str, BudgetPolicy] = {}
    common: str | None = None
    used = 0
    for request in requests:
        if not isinstance(request, DownloadRequest):
            raise ToolsmithError("invalid_input", "Supply typed download requests")
        identity = text(request.id, 300, "Download id")
        url = canonical_url(request.url)
        destination = absolute_path(request.destination)
        policy = validate_http_policy(request.policy)
        budget = validate_policy(request.budget)
        definition = common_definition(budget)
        if common is not None and common != definition:
            raise ToolsmithError("invalid_input", "Batch budgets require shared period/task limits")
        if budget.group in budgets and budgets[budget.group] != budget:
            raise ToolsmithError("conflict", "A batch group requires one budget policy")
        budgets[budget.group] = budget
        common = definition
        if identity in identities or url in urls or destination in destinations:
            raise ToolsmithError(
                "invalid_input", "Download ids, URLs and destinations must be unique"
            )
        if urlsplit(url).hostname not in policy.hosts:
            raise ToolsmithError("denied", "Download host is not in its explicit approved policy")
        used += len(identity.encode()) + len(url.encode()) + len(str(destination).encode())
        if used > 32 * 1024 * 1024:
            raise ToolsmithError(
                "limit", "Batch input exceeds 32 MiB; retain remaining inputs for another batch"
            )
        identities.add(identity)
        urls.add(url)
        destinations.add(destination)


async def download_one(
    request: DownloadRequest,
    network_state: Path,
    task: str,
    clock: Clock,
    semaphore: asyncio.Semaphore,
    resolver: Resolver | None,
    transport: Transport | None,
) -> DownloadOutcome:
    attempted = 0

    def before_request() -> None:
        nonlocal attempted
        attempted += 1

    @async_boundary
    async def execute() -> DownloadedFile:
        if request.destination.exists() or request.destination.is_symlink():
            raise ToolsmithError(
                "conflict", "Download destination already exists; no request was made"
            )
        response = unwrap(
            await fetch_http_async(
                request.url,
                request.policy,
                network_state,
                request.budget,
                task,
                clock=clock,
                resolver=resolver,
                transport=transport,
                before_request=before_request,
                network_limit=semaphore,
            )
        )
        unwrap(write_new_bytes(request.destination, response.content))
        return DownloadedFile(
            response.final_url,
            str(request.destination),
            response.media_type,
            len(response.content),
            response.wire_bytes,
            response.requests,
            response.received_at,
        )

    result = await execute()
    return DownloadOutcome(request.id, attempted, result)


@async_boundary
async def download_batch_async(
    requests: tuple[DownloadRequest, ...],
    network_state: Path,
    task: str,
    *,
    concurrency: int = 8,
    deadline_seconds: float = 300,
    clock: Clock | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> DownloadBatch:
    validate_requests(requests)
    absolute_path(network_state)
    identity(task, "Task identity")
    maximum = integer(concurrency, 1, 16, "Concurrent network operations")
    duration = number(deadline_seconds, 0.1, 3600, "Batch deadline seconds")
    selected_clock = clock or SystemClock()
    started = selected_clock.monotonic()
    deadline = started + duration
    semaphore = asyncio.Semaphore(maximum)
    groups: dict[str, list[DownloadRequest]] = defaultdict(list)
    for request in requests:
        groups[request.budget.group].append(request)
    outcomes: dict[str, DownloadOutcome] = {}

    async def run_group(group: list[DownloadRequest]) -> None:
        blocked: Failure | None = None
        for request in group:
            if blocked is not None:
                outcomes[request.id] = DownloadOutcome(request.id, 0, blocked)
                continue
            if selected_clock.monotonic() >= deadline:
                break
            try:
                outcome = await download_one(
                    request, network_state, task, selected_clock, semaphore, resolver, transport
                )
            except asyncio.CancelledError:
                outcomes[request.id] = DownloadOutcome(
                    request.id,
                    None,
                    Failure(
                        "deferred",
                        "Download was interrupted; delivery is unknown and its quota reservation is retained",
                    ),
                )
                raise
            outcomes[request.id] = outcome
            if isinstance(outcome.result, Failure) and outcome.result.code == "deferred":
                blocked = outcome.result

    tasks = [asyncio.create_task(run_group(group)) for group in groups.values()]
    try:
        async with asyncio.timeout(duration):
            await asyncio.gather(*tasks)
    except TimeoutError:
        for active in tasks:
            active.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        for active in tasks:
            if not active.done():
                active.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    items = tuple(
        outcomes.get(
            request.id,
            DownloadOutcome(
                request.id,
                0,
                Failure("deferred", "Batch deadline reached; this input remains unfinished"),
            ),
        )
        for request in requests
    )
    complete = all(not isinstance(item.result, Failure) for item in items)
    return DownloadBatch(items, complete, max(0, selected_clock.monotonic() - started))


@boundary
def download_batch(
    requests: tuple[DownloadRequest, ...],
    network_state: Path,
    task: str,
    *,
    concurrency: int = 8,
    deadline_seconds: float = 300,
    clock: Clock | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> DownloadBatch:
    return unwrap(
        asyncio.run(
            download_batch_async(
                requests,
                network_state,
                task,
                concurrency=concurrency,
                deadline_seconds=deadline_seconds,
                clock=clock,
                resolver=resolver,
                transport=transport,
            )
        )
    )
