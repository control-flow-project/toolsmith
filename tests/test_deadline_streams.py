import io
import socket
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from conftest import ControlledClock

from toolsmith.acquisition.streams import DeadlineReader
from toolsmith.result import ToolsmithError


def test_buffered_socket_reader_keeps_one_absolute_deadline(
    tmp_path: Path, clock: ControlledClock
) -> None:
    path = tmp_path / "input"
    path.write_bytes(b"response")
    raw = io.FileIO(path, "rb")
    sock = Mock(spec=socket.socket)
    with DeadlineReader(raw, cast(socket.socket, sock), clock.monotonic() + 5, clock) as reader:
        first, second = bytearray(3), bytearray(5)
        assert reader.readinto(first) == 3 and first == b"res"
        clock.advance(2)
        assert reader.readinto(second) == 5 and second == b"ponse"
        assert [call.args[0] for call in sock.settimeout.call_args_list] == [5, 3]
    assert raw.closed


def test_expired_socket_reader_cannot_consume_input(tmp_path: Path, clock: ControlledClock) -> None:
    path = tmp_path / "input"
    path.write_bytes(b"response")
    raw = io.FileIO(path, "rb")
    with DeadlineReader(
        raw, cast(socket.socket, Mock(spec=socket.socket)), clock.monotonic(), clock
    ) as reader:
        with pytest.raises(ToolsmithError):
            reader.readinto(bytearray(4))
        assert raw.tell() == 0
    assert raw.closed
