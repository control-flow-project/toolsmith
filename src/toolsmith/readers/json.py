from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import JsonValue, integer, parse_json


@boundary
def read_json(content: bytes, maximum_bytes: int = 32 * 1024 * 1024) -> JsonValue:
    maximum = integer(maximum_bytes, 1, 128 * 1024 * 1024, "Maximum JSON bytes")
    return parse_json(content, maximum)


@boundary
def read_json_lines(content: bytes, maximum_bytes: int = 32 * 1024 * 1024) -> tuple[JsonValue, ...]:
    maximum = integer(maximum_bytes, 1, 128 * 1024 * 1024, "Maximum JSONL bytes")
    if not isinstance(content, bytes):
        raise ToolsmithError("invalid_input", "JSONL input must be bytes")
    if len(content) > maximum:
        raise ToolsmithError("limit", "JSONL input exceeds its explicit byte bound")
    return tuple(parse_json(line, maximum) for line in content.splitlines() if line.strip())
