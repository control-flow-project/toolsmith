import asyncio
import ssl
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiohttp
import pytest
from aiohttp.base_protocol import BaseProtocol
from aiohttp.http_exceptions import HttpProcessingError
from aiohttp.http_parser import HttpResponseParser
from conftest import ControlledClock

from toolsmith.acquisition.transport import HttpMethod, NativeTransport
from toolsmith.result import ToolsmithError

type NativeRequest = Callable[[tuple[tuple[str, str], ...], bytes, int], bytes]


@dataclass
class SourceResponse:
    status: int
    raw_headers: tuple[tuple[bytes, bytes], ...]
    content: aiohttp.StreamReader


@pytest.fixture
def native_request(monkeypatch: pytest.MonkeyPatch, clock: ControlledClock) -> NativeRequest:
    def request(headers: tuple[tuple[str, str], ...], body: bytes, maximum: int) -> bytes:
        wire = (
            b"HTTP/1.1 200 OK\r\n"
            + b"".join(name.encode() + b": " + value.encode() + b"\r\n" for name, value in headers)
            + b"\r\n"
            + body
        )

        class Session:
            def __init__(
                self,
                *,
                connector: aiohttp.BaseConnector,
                cookie_jar: aiohttp.abc.AbstractCookieJar,
                trust_env: bool,
                auto_decompress: bool,
                max_headers: int,
                max_line_size: int,
                max_field_size: int,
                read_bufsize: int,
            ) -> None:
                self.connector = connector
                assert isinstance(cookie_jar, aiohttp.DummyCookieJar)
                assert not trust_env and not auto_decompress
                assert max_headers == 100
                assert max_line_size == max_field_size == read_bufsize == 65_536

            async def __aenter__(self) -> "Session":
                return self

            async def __aexit__(self, *_arguments: object) -> None:
                await self.connector.close()

            @asynccontextmanager
            async def request(
                self,
                method: str,
                url: str,
                *,
                data: bytes | None,
                headers: tuple[tuple[str, str], ...],
                allow_redirects: bool,
                server_hostname: str,
            ) -> AsyncIterator[SourceResponse]:
                assert method == "GET" and data is None
                assert url == "https://example.com/path"
                assert server_hostname == "example.com" and not allow_redirects
                assert dict(headers)["User-Agent"].startswith("Mozilla/5.0")
                assert not {name.lower() for name, _value in headers} & {"cookie", "authorization"}
                loop = asyncio.get_running_loop()
                parser = HttpResponseParser(
                    BaseProtocol(loop),
                    loop,
                    65_536,
                    max_headers=100,
                    max_line_size=65_536,
                    max_field_size=65_536,
                    read_until_eof=True,
                )
                try:
                    messages, _upgraded, _tail = parser.feed_data(wire)
                    parser.feed_eof()
                except (HttpProcessingError, ValueError, OverflowError) as error:
                    raise aiohttp.ClientPayloadError("Invalid fixture response framing") from error
                assert len(messages) == 1
                message, payload = messages[0]
                yield SourceResponse(message.code, message.raw_headers, payload)

        monkeypatch.setattr(aiohttp, "ClientSession", Session)
        return (
            NativeTransport()
            .request(
                "https://example.com/path", ("8.8.8.8",), maximum, clock.monotonic() + 10, clock
            )
            .content
        )

    return request


def test_native_transport_bounded_success_and_no_credentials(native_request: NativeRequest) -> None:
    assert native_request((("Content-Length", "5"),), b"plain", 10) == b"plain"
    assert native_request((("Content-Length", "0" * 5000 + "5"),), b"plain", 10) == b"plain"


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "error,code",
    [
        (ConnectionResetError("Controlled connection reset"), "unavailable"),
        (aiohttp.ServerDisconnectedError("Controlled server disconnect"), "unavailable"),
        (aiohttp.ClientPayloadError("Controlled malformed response"), "http"),
        (ssl.SSLError("Controlled TLS rejection"), "tls"),
        (TimeoutError("Controlled deadline"), "limit"),
    ],
)
def test_native_transport_distinguishes_connection_failures_from_invalid_responses(
    monkeypatch: pytest.MonkeyPatch,
    clock: ControlledClock,
    error: Exception,
    code: str,
    method: HttpMethod,
) -> None:
    async def fail_request(
        self: aiohttp.ClientSession, method: str, url: object, **options: object
    ) -> aiohttp.ClientResponse:
        raise error

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fail_request)
    with pytest.raises(ToolsmithError) as failure:
        NativeTransport().request(
            "https://example.com/path",
            ("8.8.8.8",),
            1024,
            clock.monotonic() + 10,
            clock,
            method=method,
            body=b"{}" if method == "POST" else None,
        )
    assert failure.value.failure.code == code


@pytest.mark.parametrize(
    "headers,body,maximum",
    [
        ((("Content-Length", "100"),), b"short", 10),
        ((("Content-Length", "9" * 5000),), b"short", 10),
        ((("Content-Length", "٥"),), b"short", 10),
        ((("Content-Length", "7"),), b"short", 10),
        ((("Content-Length", "5"), ("Content-Length", "5")), b"plain", 10),
        ((("Content-Length", "5"), ("Transfer-Encoding", "chunked")), b"plain", 10),
        ((("Transfer-Encoding", "gzip"),), b"plain", 10),
        ((), b"too large", 5),
        ((("Content-Encoding", "br"),), b"plain", 10),
    ],
)
def test_native_response_framing_and_body_limits(
    native_request: NativeRequest, headers: tuple[tuple[str, str], ...], body: bytes, maximum: int
) -> None:
    with pytest.raises(ToolsmithError):
        native_request(headers, body, maximum)


def test_native_chunked_body_is_decoded_by_the_http_parser(native_request: NativeRequest) -> None:
    assert (
        native_request((("Transfer-Encoding", "chunked"),), b"5\r\nplain\r\n0\r\n\r\n", 10)
        == b"plain"
    )


def test_native_response_headers_have_an_aggregate_bound(native_request: NativeRequest) -> None:
    headers = tuple((f"X-Field-{number}", "a" * 1000) for number in range(70))
    with pytest.raises(ToolsmithError) as exceeded:
        native_request(headers, b"plain", 10)
    assert exceeded.value.failure.code == "limit"
