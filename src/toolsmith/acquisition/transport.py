import asyncio
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from toolsmith.acquisition.urls import canonical_url, public_address
from toolsmith.clock import Clock
from toolsmith.compression import expand_gzip
from toolsmith.result import Failure, ToolsmithError

REQUEST_HEADERS = (
    ("User-Agent", "Mozilla/5.0 (Toolsmith; approved bounded acquisition)"),
    ("Accept", "*/*"),
    ("Accept-Encoding", "gzip"),
    ("Connection", "close"),
)


@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    content: bytes
    wire_bytes: int


class Resolver(Protocol):
    async def resolve_async(self, host: str, deadline: float, clock: Clock) -> tuple[str, ...]: ...


class Transport(Protocol):
    async def get_async(
        self,
        url: str,
        addresses: tuple[str, ...],
        maximum_bytes: int,
        deadline: float,
        clock: Clock,
    ) -> Response: ...


def remaining(deadline: float, clock: Clock) -> float:
    seconds = deadline - clock.monotonic()
    if seconds <= 0:
        raise ToolsmithError("limit", "The explicit network deadline was exhausted")
    return seconds


class NativeResolver:
    def resolve(self, host: str, deadline: float, clock: Clock) -> tuple[str, ...]:
        return asyncio.run(self.resolve_async(host, deadline, clock))

    async def resolve_async(self, host: str, deadline: float, clock: Clock) -> tuple[str, ...]:
        try:
            import dns.asyncresolver
            import dns.exception
            import dns.resolver
        except ImportError as error:
            raise ToolsmithError(
                "unavailable", "HTTP acquisition requires the optional http dependency"
            ) from error
        addresses: list[str] = []
        try:
            resolver = dns.asyncresolver.Resolver()
            async with asyncio.timeout(remaining(deadline, clock)):
                for kind in ("A", "AAAA"):
                    answer = await resolver.resolve(
                        host,
                        kind,
                        search=False,
                        raise_on_no_answer=False,
                        lifetime=remaining(deadline, clock),
                    )
                    if answer.rrset is not None:
                        addresses.extend(str(record) for record in answer)
        except dns.resolver.NXDOMAIN as error:
            raise ToolsmithError("not_found", "Approved source DNS name does not exist") from error
        except (dns.exception.DNSException, TimeoutError) as error:
            raise ToolsmithError(
                "unavailable", "Approved source DNS resolution failed within its explicit deadline"
            ) from error
        remaining(deadline, clock)
        if not 1 <= len(addresses) <= 64:
            raise ToolsmithError("denied", "DNS must return one to 64 public addresses")
        return tuple(dict.fromkeys(public_address(address) for address in addresses))


def one_header(headers: tuple[tuple[str, str], ...], name: str) -> str | None:
    values = [value.strip() for key, value in headers if key.lower() == name]
    if len(values) > 1:
        raise ToolsmithError("http", "Source returned an ambiguous duplicate response header")
    return values[0] if values else None


def expanded_body(content: bytes, encoding: str | None, maximum_bytes: int) -> bytes:
    if encoding is None or encoding.lower() == "identity":
        return content
    if encoding.lower() != "gzip":
        raise ToolsmithError("http", "Only identity and bounded gzip responses are supported")
    result = expand_gzip(content, maximum_bytes)
    if isinstance(result, Failure):
        raise ToolsmithError("limit" if result.code == "limit" else "http", result.message)
    return result.value


def validate_headers(headers: tuple[tuple[str, str], ...], maximum_bytes: int) -> None:
    if len(headers) > 100 or sum(len(name) + len(value) + 4 for name, value in headers) > 65_536:
        raise ToolsmithError("limit", "Response headers exceed their structural budget")
    length = one_header(headers, "content-length")
    transfer = one_header(headers, "transfer-encoding")
    if length is not None:
        digits = length.lstrip("0") or "0"
        if (
            not length.isascii()
            or not length.isdecimal()
            or len(digits) > len(str(maximum_bytes))
            or int(digits) > maximum_bytes
        ):
            raise ToolsmithError(
                "limit", "Declared response bytes exceed the explicit limit or are invalid"
            )
    if transfer is not None and (transfer.lower() != "chunked" or length is not None):
        raise ToolsmithError("http", "Response framing is ambiguous or unsupported")


async def request_pinned_async(
    url: str,
    addresses: tuple[str, ...],
    maximum_bytes: int,
    deadline: float,
    clock: Clock,
    *,
    headers: tuple[tuple[str, str], ...] = REQUEST_HEADERS,
) -> Response:
    try:
        import aiohttp
        from aiohttp.abc import AbstractResolver, ResolveResult
    except ImportError as error:
        raise ToolsmithError(
            "unavailable", "HTTP acquisition requires the optional http dependency"
        ) from error
    selected = canonical_url(url)
    parts = urlsplit(selected)
    if parts.hostname is None or not addresses:
        raise ToolsmithError(
            "invalid_input", "Transport requires a host and a validated pinned address"
        )
    host, address = parts.hostname, public_address(addresses[0])
    if any(name.lower() == "host" for name, _value in headers):
        raise ToolsmithError("invalid_input", "The pinned transport owns the Host header")

    class PinnedResolver(AbstractResolver):
        async def resolve(
            self, hostname: str, port: int = 0, family: int = socket.AF_INET
        ) -> list[ResolveResult]:
            if hostname != host or port != 443:
                raise ToolsmithError(
                    "denied", "Connection does not match the validated host and port"
                )
            selected_family = (
                socket.AF_INET6
                if isinstance(ipaddress.ip_address(address), ipaddress.IPv6Address)
                else socket.AF_INET
            )
            return [
                ResolveResult(
                    hostname=host,
                    host=address,
                    port=443,
                    family=selected_family,
                    proto=0,
                    flags=socket.AI_NUMERICHOST,
                )
            ]

        async def close(self) -> None:
            return None

    try:
        async with asyncio.timeout(remaining(deadline, clock)):
            connector = aiohttp.TCPConnector(
                resolver=PinnedResolver(),
                use_dns_cache=False,
                ssl=ssl.create_default_context(),
                limit=1,
                force_close=True,
            )
            async with (
                aiohttp.ClientSession(
                    connector=connector,
                    cookie_jar=aiohttp.DummyCookieJar(),
                    trust_env=False,
                    auto_decompress=False,
                    max_headers=100,
                    max_line_size=65_536,
                    max_field_size=65_536,
                    read_bufsize=65_536,
                ) as session,
                session.get(
                    selected, headers=headers, allow_redirects=False, server_hostname=host
                ) as response,
            ):
                observed = tuple(
                    (name.decode("ascii"), value.decode("latin-1"))
                    for name, value in response.raw_headers
                )
                validate_headers(observed, maximum_bytes)
                content = bytearray()
                async for chunk in response.content.iter_chunked(65_536):
                    remaining(deadline, clock)
                    if len(content) + len(chunk) > maximum_bytes:
                        raise ToolsmithError(
                            "limit", "Response wire bytes exceed the explicit limit"
                        )
                    content.extend(chunk)
                remaining(deadline, clock)
                wire = bytes(content)
                length = one_header(observed, "content-length")
                if length is not None and len(wire) != int(length.lstrip("0") or "0"):
                    raise ToolsmithError("http", "Response ended before its declared length")
                return Response(
                    response.status,
                    observed,
                    expanded_body(wire, one_header(observed, "content-encoding"), maximum_bytes),
                    len(wire),
                )
    except (ssl.SSLError, aiohttp.ClientSSLError) as error:
        raise ToolsmithError(
            "tls", "Approved source TLS verification or handshake failed"
        ) from error
    except TimeoutError as error:
        raise ToolsmithError("limit", "The explicit network deadline was exhausted") from error
    except (OSError, aiohttp.ClientError, UnicodeError) as error:
        raise ToolsmithError(
            "http", "Approved source request failed within its bounded transport"
        ) from error


def request_pinned(
    url: str,
    addresses: tuple[str, ...],
    maximum_bytes: int,
    deadline: float,
    clock: Clock,
    *,
    headers: tuple[tuple[str, str], ...] = REQUEST_HEADERS,
) -> Response:
    return asyncio.run(
        request_pinned_async(url, addresses, maximum_bytes, deadline, clock, headers=headers)
    )


class NativeTransport:
    def get(
        self,
        url: str,
        addresses: tuple[str, ...],
        maximum_bytes: int,
        deadline: float,
        clock: Clock,
    ) -> Response:
        return request_pinned(url, addresses, maximum_bytes, deadline, clock)

    async def get_async(
        self,
        url: str,
        addresses: tuple[str, ...],
        maximum_bytes: int,
        deadline: float,
        clock: Clock,
    ) -> Response:
        return await request_pinned_async(url, addresses, maximum_bytes, deadline, clock)
