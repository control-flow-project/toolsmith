from collections.abc import Callable

import pytest
from conftest import ControlledClock

from toolsmith.acquisition.transport import NativeTransport
from toolsmith.result import ToolsmithError


class SourceResponse:
    def __init__(self, headers: tuple[tuple[str, str], ...], body: bytes) -> None:
        self.headers = headers
        self.body = body
        self.status = 200
        self.closed = False

    def getheaders(self) -> tuple[tuple[str, str], ...]:
        return self.headers

    def isclosed(self) -> bool:
        return self.closed

    def read1(self, maximum: int) -> bytes:
        content = self.body[:maximum]
        self.body = self.body[maximum:]
        if not self.body:
            self.closed = True
        return content

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def native_request(
    monkeypatch: pytest.MonkeyPatch, clock: ControlledClock
) -> Callable[[tuple[tuple[str, str], ...], bytes, int], bytes]:
    import toolsmith.acquisition.transport as implementation

    def request(headers: tuple[tuple[str, str], ...], body: bytes, maximum: int) -> bytes:
        response = SourceResponse(headers, body)
        captured: dict[str, str] = {}
        closed: list[bool] = []

        class Connection:
            active_socket: None = None

            def __init__(self, *_arguments: object) -> None:
                pass

            def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
                assert method == "GET" and path == "/source"
                captured.update(headers)

            def getresponse(self) -> SourceResponse:
                return response

            def close(self) -> None:
                closed.append(True)

        monkeypatch.setattr(implementation, "PinnedConnection", Connection)
        try:
            result = NativeTransport().get(
                "https://example.com/source", ("8.8.8.8",), maximum, clock.monotonic() + 10, clock
            )
            assert captured["User-Agent"].startswith("Mozilla/5.0")
            assert "Authorization" not in captured and "Cookie" not in captured
            return result.content
        finally:
            assert closed == [True]
            assert response.closed

    return request


def test_native_transport_bounded_success_and_no_credentials(
    native_request: Callable[[tuple[tuple[str, str], ...], bytes, int], bytes],
) -> None:
    assert native_request((("Content-Length", "5"),), b"plain", 10) == b"plain"
    assert native_request((("Content-Length", "0" * 5000 + "5"),), b"plain", 10) == b"plain"


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
    native_request: Callable[[tuple[tuple[str, str], ...], bytes, int], bytes],
    headers: tuple[tuple[str, str], ...],
    body: bytes,
    maximum: int,
) -> None:
    with pytest.raises(ToolsmithError):
        native_request(headers, body, maximum)
