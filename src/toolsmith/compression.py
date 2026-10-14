import zlib

from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer


@boundary
def expand_gzip(content: bytes, maximum_bytes: int) -> bytes:
    maximum = integer(maximum_bytes, 1, 128 * 1024 * 1024, "Expanded byte budget")
    if not isinstance(content, bytes) or len(content) > 128 * 1024 * 1024:
        raise ToolsmithError("invalid_input", "Supply bounded compressed bytes")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        expanded = decoder.decompress(content, maximum + 1)
        if len(expanded) > maximum or decoder.unconsumed_tail:
            raise ToolsmithError("limit", "Expanded content exceeds its explicit byte budget")
        if not decoder.eof or decoder.unused_data:
            raise ToolsmithError("invalid_input", "GZIP content is truncated or has extra members")
        return expanded
    except zlib.error as error:
        raise ToolsmithError("invalid_input", "GZIP content is malformed") from error
