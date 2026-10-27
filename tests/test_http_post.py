"""Real HTTP codecs over connected sockets, with connection establishment isolated."""

import asyncio
import socket
import ssl
from collections.abc import Callable
from typing import cast

import aiohttp
import pytest
from aiohttp.client_proto import ResponseHandler
from conftest import ControlledClock

from toolsmith.acquisition.transport import (
    MAX_REQUEST_BYTES,
    REQUEST_HEADERS,
    HttpMethod,
    request_pinned,
    request_pinned_async,
)
from toolsmith.clock import SystemClock
from toolsmith.result import ToolsmithError


@pytest.mark.parametrize(
    "method,body",
    [
        ("GET", b"{}"),
        ("POST", None),
        ("POST", b""),
        ("POST", b"x" * (MAX_REQUEST_BYTES + 1)),
        ("PUT", b"{}"),
    ],
)
def test_invalid_request_is_rejected_before_native_connection(method: object, body: object) -> None:
    with pytest.raises(ToolsmithError) as failure:
        request_pinned(
            "https://example.com/list",
            ("8.8.8.8",),
            100,
            100,
            ControlledClock(),
            method=cast("HttpMethod", method),
            body=cast(bytes | None, body),
        )
    assert failure.value.failure.code == "invalid_input"


@pytest.mark.parametrize("status", [200, 307, 429, 503])
@pytest.mark.parametrize(
    "request_body", [b'{"page":1,"language":"hi","order":"a+b/%"}', b"x" * MAX_REQUEST_BYTES]
)
def test_post_real_http_socket_serializes_exact_body_and_owns_framing(
    monkeypatch: pytest.MonkeyPatch, status: int, request_body: bytes
) -> None:
    """Bypass connection establishment only; exercise native aiohttp request/response codecs."""

    async def exercise() -> None:
        outgoing, incoming = socket.socketpair()
        outgoing.setblocking(False)
        incoming.setblocking(False)
        reader, writer = await asyncio.open_connection(sock=incoming)
        captured: list[bytes] = []
        loop = asyncio.get_running_loop()

        async def connect(
            self: aiohttp.TCPConnector, *arguments: object, **options: object
        ) -> tuple[asyncio.Transport, ResponseHandler]:
            assert options["server_hostname"] == "example.com"
            context = options["ssl"]
            assert isinstance(context, ssl.SSLContext)
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            addresses = cast(
                list[tuple[object, object, object, object, tuple[object, ...]]],
                options["addr_infos"],
            )
            assert addresses[0][4] == ("8.8.8.8", 443)
            factory = cast(Callable[[], ResponseHandler], arguments[0])
            return await loop.create_connection(factory, sock=outgoing)

        async def respond() -> None:
            header = await reader.readuntil(b"\r\n\r\n")
            length = next(
                int(line.split(b":", 1)[1])
                for line in header.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            body = await reader.readexactly(length)
            captured.extend((header, body))
            writer.write(
                ("HTTP/1.1 " + str(status) + " Fixture\r\n").encode()
                + b'Content-Type: application/json\r\nContent-Length: 11\r\n\r\n{"ok":true}'
            )
            await writer.drain()

        monkeypatch.setattr(aiohttp.TCPConnector, "_wrap_create_connection", connect)
        responder = asyncio.create_task(respond())
        clock = SystemClock()
        try:
            async with asyncio.timeout(5):
                result = await request_pinned_async(
                    "https://example.com/list?lang=hi",
                    ("8.8.8.8",),
                    100,
                    clock.monotonic() + 4,
                    clock,
                    method="POST",
                    body=request_body,
                    headers=REQUEST_HEADERS + (("Content-Type", "application/json"),),
                )
                await responder
            assert result.content == b'{"ok":true}' and result.wire_bytes == 11
            assert result.status == status  # No implicit redirect/retry at this primitive.
            assert captured[0].startswith(b"POST /list?lang=hi HTTP/1.1\r\n")
            assert b"Host: example.com\r\n" in captured[0]
            assert b"Content-Type: application/json\r\n" in captured[0]
            assert b"Authorization:" not in captured[0] and b"Cookie:" not in captured[0]
            assert captured[1] == request_body
        finally:
            if not responder.done():
                responder.cancel()
            await asyncio.gather(responder, return_exceptions=True)
            writer.close()
            await writer.wait_closed()
            outgoing.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("name", ["Host", "Content-Length", "Transfer-Encoding"])
def test_native_post_rejects_caller_framing_headers(name: str, clock: ControlledClock) -> None:
    with pytest.raises(ToolsmithError) as failure:
        request_pinned(
            "https://example.com/",
            ("8.8.8.8",),
            100,
            clock.monotonic() + 4,
            clock,
            method="POST",
            body=b"{}",
            headers=((name, "bad"),),
        )
    assert failure.value.failure.code == "invalid_input"


def test_native_post_cancellation_propagates_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        entered = asyncio.Event()
        blocked = asyncio.Event()
        methods: list[str] = []

        async def pending(
            self: aiohttp.ClientSession, method: str, url: object, **options: object
        ) -> aiohttp.ClientResponse:
            assert options["data"] == b"{}"
            methods.append(method)
            entered.set()
            await blocked.wait()
            raise AssertionError("Cancelled request must not resume")

        monkeypatch.setattr(aiohttp.ClientSession, "_request", pending)
        clock = SystemClock()
        task = asyncio.create_task(
            request_pinned_async(
                "https://example.com/list",
                ("8.8.8.8",),
                100,
                clock.monotonic() + 4,
                clock,
                method="POST",
                body=b"{}",
            )
        )
        try:
            async with asyncio.timeout(5):
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert methods == ["POST"]
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
