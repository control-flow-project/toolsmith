import http.client
import io
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlsplit

from toolsmith.acquisition.urls import public_address
from toolsmith.clock import Clock
from toolsmith.compression import expand_gzip
from toolsmith.result import Failure, ToolsmithError

if TYPE_CHECKING:
    from _typeshed import WriteableBuffer


@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    content: bytes
    wire_bytes: int


class Resolver(Protocol):
    def resolve(self, host: str, deadline: float, clock: Clock) -> tuple[str, ...]: ...


class Transport(Protocol):
    def get(
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
        try:
            import dns.exception
            import dns.resolver
        except ImportError as error:
            raise ToolsmithError(
                "unavailable",
                "HTTP acquisition requires the optional http dependency; no unbounded DNS fallback is used",
            ) from error
        addresses: list[str] = []
        try:
            resolver = dns.resolver.Resolver()
            for kind in ("A", "AAAA"):
                answer = resolver.resolve(
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
        except dns.exception.DNSException as error:
            raise ToolsmithError(
                "unavailable", "Approved source DNS resolution failed within its explicit deadline"
            ) from error
        remaining(deadline, clock)
        if not 1 <= len(addresses) <= 64:
            raise ToolsmithError("denied", "DNS must return one to 64 public addresses")
        return tuple(dict.fromkeys(public_address(address) for address in addresses))


class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, deadline: float, clock: Clock) -> None:
        self.tls_context = ssl.create_default_context()
        super().__init__(host, 443, timeout=remaining(deadline, clock), context=self.tls_context)
        self.address = address
        self.deadline = deadline
        self.clock = clock
        self.active_socket: ssl.SSLSocket | None = None

        class DeadlineResponse(http.client.HTTPResponse):
            def __init__(
                response_self,
                sock: socket.socket,
                debuglevel: int = 0,
                method: str | None = None,
                url: str | None = None,
            ) -> None:
                super().__init__(sock, debuglevel, method, url)
                original = response_self.fp
                raw = cast(io.RawIOBase, sock.makefile("rb", buffering=0))
                response_self.fp = io.BufferedReader(DeadlineReader(raw, sock, deadline, clock))
                if original is not None:
                    original.close()

        self.response_class = DeadlineResponse

    def connect(self) -> None:
        family = (
            socket.AF_INET6
            if isinstance(ipaddress.ip_address(self.address), ipaddress.IPv6Address)
            else socket.AF_INET
        )
        raw = socket.socket(family, socket.SOCK_STREAM)
        try:
            raw.settimeout(remaining(self.deadline, self.clock))
            endpoint = (
                (self.address, 443, 0, 0) if family == socket.AF_INET6 else (self.address, 443)
            )
            raw.connect(endpoint)
            raw.settimeout(remaining(self.deadline, self.clock))
            self.active_socket = self.tls_context.wrap_socket(raw, server_hostname=self.host)
            self.sock = self.active_socket
        except BaseException:
            raw.close()
            raise


class DeadlineReader(io.RawIOBase):
    def __init__(
        self, raw: io.RawIOBase, sock: socket.socket, deadline: float, clock: Clock
    ) -> None:
        super().__init__()
        self.raw = raw
        self.sock = sock
        self.deadline = deadline
        self.clock = clock

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: "WriteableBuffer") -> int | None:
        self.sock.settimeout(remaining(self.deadline, self.clock))
        received = self.raw.readinto(buffer)
        remaining(self.deadline, self.clock)
        return received

    def close(self) -> None:
        try:
            self.raw.close()
        finally:
            super().close()


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


class NativeTransport:
    def get(
        self,
        url: str,
        addresses: tuple[str, ...],
        maximum_bytes: int,
        deadline: float,
        clock: Clock,
    ) -> Response:
        parts = urlsplit(url)
        if parts.hostname is None or not addresses:
            raise ToolsmithError(
                "invalid_input", "Transport requires a host and a validated pinned address"
            )
        connection = PinnedConnection(parts.hostname, public_address(addresses[0]), deadline, clock)
        try:
            connection.request(
                "GET",
                parts.path + ("?" + parts.query if parts.query else ""),
                headers={
                    "User-Agent": "Mozilla/5.0 (Toolsmith/0.3.0; approved bounded acquisition)",
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip",
                    "Connection": "close",
                },
            )
            if connection.active_socket is not None:
                connection.active_socket.settimeout(remaining(deadline, clock))
            response = connection.getresponse()
            try:
                headers = tuple(response.getheaders())
                length = one_header(headers, "content-length")
                transfer = one_header(headers, "transfer-encoding")
                encoding = one_header(headers, "content-encoding")
                declared_bytes: int | None = None
                if length is not None:
                    digits = length.lstrip("0") or "0"
                    if (
                        not length.isascii()
                        or not length.isdecimal()
                        or len(digits) > len(str(maximum_bytes))
                        or int(digits) > maximum_bytes
                    ):
                        raise ToolsmithError(
                            "limit",
                            "Declared response bytes exceed the explicit limit or are invalid",
                        )
                    declared_bytes = int(digits)
                if transfer is not None and (transfer.lower() != "chunked" or length is not None):
                    raise ToolsmithError("http", "Response framing is ambiguous or unsupported")
                chunks = bytearray()
                while len(chunks) <= maximum_bytes:
                    if response.isclosed():
                        break
                    chunk = response.read1(min(65_536, maximum_bytes + 1 - len(chunks)))
                    if not chunk:
                        break
                    chunks.extend(chunk)
                remaining(deadline, clock)
                if len(chunks) > maximum_bytes:
                    raise ToolsmithError("limit", "Response wire bytes exceed the explicit limit")
                if declared_bytes is not None and len(chunks) != declared_bytes:
                    raise ToolsmithError("http", "Response ended before its declared length")
                wire = bytes(chunks)
                return Response(
                    response.status,
                    headers,
                    expanded_body(wire, encoding, maximum_bytes),
                    len(wire),
                )
            finally:
                response.close()
        except ssl.SSLError as error:
            raise ToolsmithError(
                "tls", "Approved source TLS verification or handshake failed"
            ) from error
        except (OSError, http.client.HTTPException) as error:
            raise ToolsmithError(
                "http", "Approved source request failed within its bounded transport"
            ) from error
        finally:
            connection.close()
