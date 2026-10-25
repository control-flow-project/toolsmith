import io
import socket
from typing import TYPE_CHECKING

from toolsmith.acquisition.transport import remaining
from toolsmith.clock import Clock

if TYPE_CHECKING:
    from _typeshed import WriteableBuffer


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
