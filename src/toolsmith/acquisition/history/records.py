"""One mandatory current record contract over the existing private-file primitives."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from toolsmith.files import private_directory, read_private, replace_bytes, write_new_bytes
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.validation import canonical_json, fields, identity, parse_json

CONTRACT = "toolsmith.acquisition.history"
MAX_RECORD_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class Record:
    category: str
    key: str
    value: dict[str, object]

    def __post_init__(self) -> None:
        identity(self.category, "Record category")
        if not self.key or len(self.key.encode()) > 4096 or "\x00" in self.key:
            raise ToolsmithError("invalid_input", "Record identity must be bounded text")
        if not isinstance(self.value, dict):
            raise ToolsmithError("invalid_input", "Record payload must be an explicit JSON object")
        canonical_json(self.value)


def encode(record: Record) -> bytes:
    if not isinstance(record, Record):
        raise ToolsmithError("invalid_input", "Supply a typed historical record")
    return (
        canonical_json(
            {
                "contract": CONTRACT,
                "category": record.category,
                "key": record.key,
                "payload_sha256": hashlib.sha256(canonical_json(record.value)).hexdigest(),
                "payload": record.value,
            }
        )
        + b"\n"
    )


def decode(content: bytes, *, category: str | None = None, key: str | None = None) -> Record:
    value = fields(
        parse_json(content, MAX_RECORD_BYTES),
        {"contract", "category", "key", "payload_sha256", "payload"},
    )
    if value["contract"] != CONTRACT:
        raise ToolsmithError(
            "invalid_input", "Only the current historical record contract is accepted"
        )
    if (
        not isinstance(value["payload"], dict)
        or not isinstance(value["category"], str)
        or not isinstance(value["key"], str)
    ):
        raise ToolsmithError("invalid_input", "Historical record fields are invalid")
    if hashlib.sha256(canonical_json(value["payload"])).hexdigest() != value["payload_sha256"]:
        raise ToolsmithError("integrity", "Historical record payload differs from its digest")
    if (category is not None and value["category"] != category) or (
        key is not None and value["key"] != key
    ):
        raise ToolsmithError("integrity", "Historical record differs from its selected identity")
    payload: dict[str, object] = {name: item for name, item in value["payload"].items()}
    return Record(value["category"], value["key"], payload)


@boundary
def read_record(path: Path, *, category: str | None = None, key: str | None = None) -> Record:
    with private_directory(path.parent) as directory:
        return decode(
            read_private(directory, path.name, MAX_RECORD_BYTES), category=category, key=key
        )


@boundary
def write_record(path: Path, record: Record, *, immutable: bool = False) -> None:
    if type(immutable) is not bool:
        raise ToolsmithError("invalid_input", "Immutable publication intent must be Boolean")
    content = encode(record)
    if len(content) > MAX_RECORD_BYTES:
        raise ToolsmithError("limit", "Historical metadata exceeds32MiB")
    if immutable:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            current = unwrap(read_record(path))
            if encode(current) != content:
                raise ToolsmithError("conflict", "Immutable historical record already differs")
            return
        unwrap(write_new_bytes(path, content))
    else:
        unwrap(replace_bytes(path, content))
