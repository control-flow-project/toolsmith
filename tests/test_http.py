import gzip
import ssl
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import ControlledClock
from test_transport import NativeRequest
from test_transport import native_request as native_request

from toolsmith.acquisition.client import retry_after
from toolsmith.acquisition.http import acquire_http, resume_http
from toolsmith.acquisition.limits import inspect_limits
from toolsmith.acquisition.policy import SourcePolicy
from toolsmith.acquisition.transport import (
    HttpMethod,
    Response,
    expanded_body,
)
from toolsmith.clock import Clock
from toolsmith.result import Failure, ToolsmithError, unwrap
from toolsmith.storage.artifacts import read_file
from toolsmith.storage.database import inspect_store, open_store
from toolsmith.storage.operations import operation_status
from toolsmith.validation import canonical_json, json_value


class FixedResolver:
    def __init__(self, addresses: tuple[str, ...] = ("8.8.8.8",)) -> None:
        self.addresses = addresses
        self.hosts: list[str] = []

    async def resolve_async(self, host: str, deadline: float, clock: Clock) -> tuple[str, ...]:
        self.hosts.append(host)
        return self.addresses


class RecordedTransport:
    def __init__(self, responses: list[Response | ToolsmithError]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    async def request_async(
        self,
        url: str,
        addresses: tuple[str, ...],
        maximum_bytes: int,
        deadline: float,
        clock: Clock,
        *,
        method: HttpMethod = "GET",
        body: bytes | None = None,
    ) -> Response:
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, ToolsmithError):
            raise response
        return response


def plain(content: bytes = b"useful words") -> Response:
    return Response(200, (("Content-Type", "text/plain; charset=utf-8"),), content, len(content))


@pytest.mark.parametrize("value", ["864000", "Sun, 25 Oct 2026 12:00:00 GMT"])
def test_long_upstream_cooldowns_are_not_shortened(value: str, clock: ControlledClock) -> None:
    clock.current_wall = 1_792_065_600
    response = Response(429, (("Retry-After", value),), b"", 0)
    assert retry_after(response, clock) == 864_000


def test_unrepresentable_upstream_cooldown_fails_closed(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "text_only")
    transport = RecordedTransport([Response(429, (("Retry-After", "9" * 400),), b"", 0)])
    result = acquire_http(
        store,
        "sample",
        tmp_path / "network",
        "https://example.com/",
        policy,
        "unknown-cooldown",
        item="doc",
        clock=clock,
        resolver=FixedResolver(),
        transport=transport,
    )
    assert isinstance(result, Failure) and result.code == "deferred"
    assert result.retry_after_seconds is None
    clock.advance(7 * 86_400)
    repeated = acquire_http(
        store,
        "sample",
        tmp_path / "network",
        "https://example.com/",
        policy,
        "blocked-cooldown",
        item="doc",
        clock=clock,
        resolver=FixedResolver(),
        transport=transport,
    )
    assert isinstance(repeated, Failure) and repeated.code == "deferred"
    assert len(transport.urls) == 1


def test_fetch_replay_and_original_retention(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "original")
    transport = RecordedTransport([plain()])
    resolver = FixedResolver()
    result = unwrap(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/doc",
            policy,
            "request",
            item="doc",
            name="doc.txt",
            clock=clock,
            resolver=resolver,
            transport=transport,
        )
    )
    assert result.artifact is not None and result.document is not None
    assert unwrap(read_file(store, "sample", result.artifact.version)) == b"useful words"
    assert resolver.hosts == ["example.com"] and len(transport.urls) == 1
    repeated = unwrap(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/doc",
            policy,
            "request",
            item="doc",
            name="doc.txt",
            clock=clock,
            resolver=resolver,
            transport=transport,
        )
    )
    assert repeated.reused and len(transport.urls) == 1
    assert unwrap(
        resume_http(
            store,
            "sample",
            tmp_path / "network",
            policy,
            "request",
            clock=clock,
            resolver=resolver,
            transport=transport,
        )
    ).reused
    assert isinstance(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/other",
            policy,
            "request",
            item="doc",
            name="doc.txt",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )


def test_denied_scope_host_retention_and_dns_never_send(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "text_only")
    transport = RecordedTransport([])
    resolver = FixedResolver()
    assert isinstance(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/",
            policy,
            "original",
            name="raw.html",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )
    assert isinstance(
        acquire_http(
            store,
            "other",
            tmp_path / "network",
            "https://example.com/",
            policy,
            "wrong",
            item="doc",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )
    assert isinstance(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://other.com/",
            policy,
            "host",
            item="doc",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )
    assert isinstance(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/",
            policy,
            "dns",
            item="doc",
            clock=clock,
            resolver=FixedResolver(("8.8.8.8", "127.0.0.1")),
            transport=transport,
        ),
        Failure,
    )
    assert not transport.urls


def test_redirects_recheck_policy_and_dns(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "original")
    transport = RecordedTransport([Response(302, (("Location", "/final"),), b"", 0), plain()])
    resolver = FixedResolver()
    result = unwrap(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/first",
            policy,
            "redirect",
            name="doc.txt",
            clock=clock,
            resolver=resolver,
            transport=transport,
        )
    )
    assert result.final_url == "https://example.com/final" and result.requests == 2
    assert resolver.hosts == ["example.com", "example.com"]
    blocked = RecordedTransport(
        [Response(302, (("Location", "https://other.com/secret"),), b"", 0)]
    )
    assert isinstance(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/first",
            policy,
            "blocked",
            name="doc.txt",
            clock=clock,
            resolver=resolver,
            transport=blocked,
        ),
        Failure,
    )
    assert len(blocked.urls) == 1


def test_interrupted_get_requires_explicit_bounded_resume(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "text_only", maximum_requests=2)
    transport = RecordedTransport([ToolsmithError("http", "Connection broke"), plain()])
    resolver = FixedResolver()
    first = acquire_http(
        store,
        "sample",
        tmp_path / "network",
        "https://example.com/doc",
        policy,
        "request",
        item="doc",
        clock=clock,
        resolver=resolver,
        transport=transport,
    )
    assert isinstance(first, Failure) and first.code == "http"
    assert unwrap(operation_status(store, "sample", "request")).status == "failed"
    assert (
        unwrap(inspect_limits(tmp_path / "network", policy, clock=clock)).reserved_bytes
        == policy.maximum_response_bytes
    )
    assert isinstance(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/doc",
            policy,
            "request",
            item="doc",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )
    assert len(transport.urls) == 1
    deferred = resume_http(
        store,
        "sample",
        tmp_path / "network",
        policy,
        "request",
        clock=clock,
        resolver=resolver,
        transport=transport,
    )
    assert isinstance(deferred, Failure) and deferred.code == "deferred"
    assert len(transport.urls) == 1
    clock.advance(policy.deadline_seconds + 1)
    result = unwrap(
        resume_http(
            store,
            "sample",
            tmp_path / "network",
            policy,
            "request",
            clock=clock,
            resolver=resolver,
            transport=transport,
        )
    )
    assert result.requests == 2 and result.warnings
    assert unwrap(inspect_store(store, "sample")).text_versions == 1


def test_resume_cannot_change_policy_state_root_or_reset_allowance(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "text_only", maximum_requests=1)
    transport = RecordedTransport([ToolsmithError("http", "failed")])
    resolver = FixedResolver()
    acquire_http(
        store,
        "sample",
        tmp_path / "network",
        "https://example.com/doc",
        policy,
        "request",
        item="doc",
        clock=clock,
        resolver=resolver,
        transport=transport,
    )
    assert isinstance(
        resume_http(
            store,
            "sample",
            tmp_path / "elsewhere",
            policy,
            "request",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )
    assert isinstance(
        resume_http(
            store,
            "sample",
            tmp_path / "network",
            replace(policy, maximum_requests=2),
            "request",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )
    exhausted = resume_http(
        store,
        "sample",
        tmp_path / "network",
        policy,
        "request",
        clock=clock,
        resolver=resolver,
        transport=transport,
    )
    assert isinstance(exhausted, Failure) and exhausted.code == "limit"
    assert len(transport.urls) == 1


def test_running_operation_after_process_loss_resumes_saved_request(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "text_only")
    transport = RecordedTransport([ToolsmithError("http", "failed"), plain()])
    resolver = FixedResolver()
    acquire_http(
        store,
        "sample",
        tmp_path / "network",
        "https://example.com/doc",
        policy,
        "request",
        item="doc",
        clock=clock,
        resolver=resolver,
        transport=transport,
    )
    with open_store(store, "sample", write=True) as selected, selected.connection:
        selected.connection.execute(
            "UPDATE operation SET status = 'running', failure_json = NULL WHERE id = 'request'"
        )
    clock.advance(policy.deadline_seconds + 1)
    resumed = unwrap(
        resume_http(
            store,
            "sample",
            tmp_path / "network",
            policy,
            "request",
            clock=clock,
            resolver=resolver,
            transport=transport,
        )
    )
    assert resumed.document is not None and resumed.warnings


def test_upstream_cooldown_and_body_limits(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    policy = SourcePolicy("source", ("example.com",), "text_only", maximum_response_bytes=100)
    transport = RecordedTransport(
        [Response(429, (("Retry-After", "30"),), b"", 0), plain(b"too large" * 30)]
    )
    resolver = FixedResolver()
    first = acquire_http(
        store,
        "sample",
        tmp_path / "network",
        "https://example.com/",
        policy,
        "first",
        item="doc",
        clock=clock,
        resolver=resolver,
        transport=transport,
    )
    assert isinstance(first, Failure) and first.retry_after_seconds == 30
    assert isinstance(
        acquire_http(
            store,
            "sample",
            tmp_path / "network",
            "https://example.com/",
            policy,
            "second",
            item="doc",
            clock=clock,
            resolver=resolver,
            transport=transport,
        ),
        Failure,
    )
    assert len(transport.urls) == 1
    clock.advance(31)
    exceeded = resume_http(
        store,
        "sample",
        tmp_path / "network",
        policy,
        "first",
        clock=clock,
        resolver=resolver,
        transport=transport,
    )
    assert isinstance(exceeded, Failure) and exceeded.code == "limit"
    assert unwrap(inspect_store(store, "sample")).items == 0


def test_gzip_wire_and_expansion_controls() -> None:
    assert expanded_body(gzip.compress(b"plain"), "gzip", 100) == b"plain"
    for content, encoding, maximum in [
        (gzip.compress(b"x" * 1000), "gzip", 100),
        (gzip.compress(b"x")[:-2], "gzip", 100),
        (gzip.compress(b"x") + gzip.compress(b"y"), "gzip", 100),
        (b"plain", "br", 100),
    ]:
        with pytest.raises(ToolsmithError):
            expanded_body(content, encoding, maximum)


def test_tls_requires_certificate_and_hostname_verification(
    native_request: NativeRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = ssl.create_default_context
    contexts: list[ssl.SSLContext] = []

    def create() -> ssl.SSLContext:
        context = original()
        contexts.append(context)
        return context

    monkeypatch.setattr(ssl, "create_default_context", create)
    assert native_request((("Content-Length", "5"),), b"plain", 10) == b"plain"
    assert len(contexts) == 1
    assert contexts[0].check_hostname
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED


def test_slow_reads_enforce_an_absolute_deadline_without_threads(
    clock: ControlledClock, native_request: NativeRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aiohttp

    original = aiohttp.StreamReader.iter_chunked

    def delayed(reader: aiohttp.StreamReader, amount: int) -> AsyncIterator[bytes]:
        async def iterate() -> AsyncIterator[bytes]:
            async for chunk in original(reader, amount):
                clock.advance(11)
                yield chunk

        return iterate()

    monkeypatch.setattr(aiohttp.StreamReader, "iter_chunked", delayed)
    with pytest.raises(ToolsmithError) as expired:
        native_request((("Content-Length", "5"),), b"plain", 10)
    assert expired.value.failure.code == "limit"


def test_policy_json_results_contain_no_machine_paths() -> None:
    policy = SourcePolicy("source", ("example.com",), "text_only")
    assert b"/home/" not in canonical_json(json_value(policy))
