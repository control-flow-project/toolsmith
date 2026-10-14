import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import cast

from toolsmith.result import ToolsmithError

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ToolsmithError("invalid_input", f"{label} must be an integer in {minimum}..{maximum}")
    return value


def number(value: object, minimum: float, maximum: float, label: str) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
        or not math.isfinite(value)
    ):
        raise ToolsmithError("invalid_input", f"{label} must be finite in {minimum}..{maximum}")
    return float(value)


def text(value: object, maximum: int, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ToolsmithError("invalid_input", f"{label} must be text")
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeError as error:
        raise ToolsmithError("invalid_input", f"{label} must be valid UTF-8") from error
    if size > maximum or not allow_empty and not value.strip() or "\x00" in value:
        raise ToolsmithError("invalid_input", f"{label} exceeds its text bounds")
    return value


def identity(value: object, label: str = "Identity") -> str:
    output = text(value, 120, label)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", output):
        raise ToolsmithError("invalid_input", f"{label} must be bounded machine-neutral text")
    return output


def digest(value: object, label: str = "Version") -> str:
    output = text(value, 64, label)
    if not re.fullmatch(r"[0-9a-f]{64}", output):
        raise ToolsmithError("invalid_input", label + " must be a lowercase SHA-256 digest")
    return output


def source_reference(value: object) -> str:
    reference = text(value, 200, "Source reference")
    if any(ord(character) < 32 or ord(character) == 127 for character in reference):
        raise ToolsmithError("invalid_input", "References cannot contain control characters")
    return reference


def timestamp(value: object, label: str = "Timestamp") -> str | None:
    if value is None:
        return None
    output = text(value, 64, label)
    try:
        parsed = datetime.fromisoformat(output)
        if parsed.utcoffset() is None:
            raise ValueError("Missing timezone")
        return parsed.astimezone(UTC).isoformat()
    except (ValueError, OverflowError) as error:
        raise ToolsmithError(
            "invalid_input", "Timestamp must be timezone-aware ISO 8601"
        ) from error


def json_value(value: object) -> JsonValue:
    return nested_json(value, 0)


def nested_json(value: object, depth: int) -> JsonValue:
    if depth > 64:
        raise ToolsmithError("invalid_input", "JSON nesting exceeds its explicit depth limit")
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError as error:
            raise ToolsmithError("invalid_input", "JSON text must be valid UTF-8") from error
        return value
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ToolsmithError("invalid_input", "JSON numbers must be finite")
        return value
    if isinstance(value, list | tuple):
        return [
            nested_json(entry, depth + 1)
            for entry in cast(list[object] | tuple[object, ...], value)
        ]
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return nested_json(asdict(value), depth + 1)
        except RecursionError as error:
            raise ToolsmithError("invalid_input", "JSON data cannot contain cycles") from error
    if isinstance(value, Mapping):
        output: dict[str, JsonValue] = {}
        for key, entry in cast(Mapping[object, object], value).items():
            if not isinstance(key, str):
                raise ToolsmithError("invalid_input", "JSON keys must be text")
            nested_json(key, depth + 1)
            output[key] = nested_json(entry, depth + 1)
        return output
    raise ToolsmithError("invalid_input", "Value is not a supported JSON result")


def canonical_json(value: object) -> bytes:
    return json.dumps(
        json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def parse_json(content: bytes, maximum: int = 1_048_576) -> JsonValue:
    if not isinstance(content, bytes) or not 0 < len(content) <= maximum:
        raise ToolsmithError("invalid_input", "JSON exceeds its input byte limit")

    def pairs(entries: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in entries:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result

    def invalid_constant(_value: str) -> object:
        raise ValueError("Non-finite JSON number")

    try:
        value: object = json.loads(
            content.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid_constant
        )
        return json_value(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ToolsmithError(
            "invalid_input", "Input must be bounded UTF-8 JSON with unique keys and finite numbers"
        ) from error


def fields(
    value: object, required: set[str], optional: set[str] | None = None
) -> dict[str, JsonValue]:
    data = json_value(value)
    if (
        not isinstance(data, dict)
        or not required <= data.keys()
        or not data.keys() <= required | (optional or set())
    ):
        raise ToolsmithError("invalid_input", "Object fields do not match the documented contract")
    return data
