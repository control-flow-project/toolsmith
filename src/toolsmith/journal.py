import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from toolsmith.clock import Clock, SystemClock, utc_now
from toolsmith.files import (
    directory_lock,
    private_directory,
    private_file,
    read_descriptor,
    write_chunk,
)
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import (
    JsonValue,
    digest,
    fields,
    integer,
    json_value,
    parse_json,
    timestamp,
)

MAX_JOURNAL_BYTES = 32 * 1024 * 1024
MAX_RECORD_BYTES = 66560


def record_bytes(value: object) -> bytes:
    return json.dumps(
        json_value(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")


@dataclass(frozen=True)
class Record:
    sequence: int
    at: str
    previous: str
    event: JsonValue
    sha256: str


def records(descriptor: int) -> tuple[Record, ...]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    content = read_descriptor(descriptor, MAX_JOURNAL_BYTES)
    if content and not content.endswith(b"\n"):
        raise ToolsmithError(
            "integrity", "Journal has an incomplete final record; no tail was removed"
        )
    previous = "0" * 64
    output: list[Record] = []
    for line in content.splitlines():
        if not 0 < len(line) <= MAX_RECORD_BYTES:
            raise ToolsmithError("integrity", "Journal record exceeds its byte budget")
        value = fields(
            parse_json(line, MAX_RECORD_BYTES), {"sequence", "at", "previous", "event", "sha256"}
        )
        sequence = integer(value["sequence"], 1, 100000, "Sequence")
        at = value["at"]
        if not isinstance(at, str) or timestamp(at) is None:
            raise ToolsmithError("integrity", "Journal record needs a timezone-aware timestamp")
        hashed = record_bytes(
            {name: value[name] for name in ("sequence", "at", "previous", "event")}
        )
        checksum = hashlib.sha256(hashed).hexdigest()
        if (
            sequence != len(output) + 1
            or digest(value["previous"]) != previous
            or digest(value["sha256"]) != checksum
        ):
            raise ToolsmithError("integrity", "Journal sequence or content chain does not verify")
        output.append(Record(sequence, at, previous, value["event"], checksum))
        previous = checksum
    return tuple(output)


def named_identity(directory: int, name: str, descriptor: int) -> None:
    selected = os.stat(name, dir_fd=directory, follow_symlinks=False)
    opened = os.fstat(descriptor)
    if (selected.st_dev, selected.st_ino) != (opened.st_dev, opened.st_ino):
        raise ToolsmithError(
            "conflict", "Journal filename changed; inspect the selected history before retrying"
        )


@boundary
def read_journal(root: Path, name: str = "journal.jsonl") -> tuple[Record, ...]:
    with private_directory(root) as directory, directory_lock(directory, shared=True):
        try:
            with private_file(directory, name) as descriptor:
                result = records(descriptor)
                named_identity(directory.descriptor, name, descriptor)
                return result
        except FileNotFoundError:
            return ()


@boundary
def append_record(
    root: Path, event: JsonValue, *, name: str = "journal.jsonl", clock: Clock | None = None
) -> Record:
    supplied = json_value(event)
    if len(record_bytes(supplied)) > 65536:
        raise ToolsmithError("limit", "Journal event exceeds 64 KiB")
    with (
        private_directory(root) as directory,
        directory_lock(directory),
        private_file(directory, name, create=True) as descriptor,
    ):
        existing = records(descriptor)
        named_identity(directory.descriptor, name, descriptor)
        previous = existing[-1].sha256 if existing else "0" * 64
        at = utc_now(clock or SystemClock())
        value: dict[str, JsonValue] = {
            "sequence": len(existing) + 1,
            "at": at,
            "previous": previous,
            "event": supplied,
        }
        checksum = hashlib.sha256(record_bytes(value)).hexdigest()
        value["sha256"] = checksum
        encoded = record_bytes(value) + b"\n"
        size = os.fstat(descriptor).st_size
        if (
            len(encoded) > MAX_RECORD_BYTES
            or size + len(encoded) > MAX_JOURNAL_BYTES
            or len(existing) >= 100000
        ):
            raise ToolsmithError(
                "limit", "Journal capacity requires explicit caller retention/maintenance"
            )
        os.lseek(descriptor, 0, os.SEEK_END)
        try:
            write_chunk(descriptor, encoded)
            os.fsync(descriptor)
        except BaseException:
            os.ftruncate(descriptor, size)
            os.fsync(descriptor)
            raise
        os.fsync(directory.descriptor)
        named_identity(directory.descriptor, name, descriptor)
        return Record(len(existing) + 1, at, previous, supplied, checksum)
