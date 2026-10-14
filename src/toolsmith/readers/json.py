from toolsmith.result import boundary
from toolsmith.validation import JsonValue, integer, parse_json


@boundary
def read_json(content: bytes, maximum_bytes: int = 32 * 1024 * 1024) -> JsonValue:
    maximum = integer(maximum_bytes, 1, 128 * 1024 * 1024, "Maximum JSON bytes")
    return parse_json(content, maximum)
