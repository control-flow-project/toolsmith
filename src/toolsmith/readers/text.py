from toolsmith.readers.models import MAX_TEXT_BYTES, Document, TextPart
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer, text


def decode_text(content: bytes, maximum_bytes: int = 4 * 1024 * 1024) -> str:
    maximum = integer(maximum_bytes, 1, MAX_TEXT_BYTES, "Maximum text bytes")
    if not isinstance(content, bytes):
        raise ToolsmithError("invalid_input", "Reader input must be bytes")
    if len(content) > maximum:
        raise ToolsmithError("limit", "Reader input exceeds its explicit byte limit")
    try:
        decoded = content.decode("utf-8-sig", errors="strict")
    except UnicodeError as error:
        raise ToolsmithError(
            "invalid_input",
            "Reader input is not UTF-8 text; native document extraction is not implemented",
        ) from error
    return text(decoded, maximum, "Reader text")


@boundary
def read_text(content: bytes, title: str, maximum_bytes: int = 4 * 1024 * 1024) -> Document:
    return Document(
        text(title, 1024, "Title"),
        (TextPart("Text", decode_text(content, maximum_bytes)),),
        "utf8-text",
    )
