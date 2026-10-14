import re
from typing import Literal

from toolsmith.readers.feeds import read_feed
from toolsmith.readers.html_dom import check_access, content_text, parse_html
from toolsmith.readers.json import read_json
from toolsmith.readers.tables import TableFormat, decode_table
from toolsmith.readers.text import decode_text
from toolsmith.result import ToolsmithError, boundary, unwrap

type ContentFormat = Literal["csv", "zip-csv", "gzip-csv", "json", "html", "text", "pdf", "feed"]


def markup_prefix(content: bytes) -> bytes:
    prefix = content[:65536].removeprefix(b"\xef\xbb\xbf").lstrip()
    for _iteration in range(32):
        if prefix.startswith(b"<!--"):
            end = prefix.find(b"-->", 4)
            if end < 0:
                break
            prefix = prefix[end + 3 :].lstrip()
        elif prefix.startswith(b"<?xml"):
            end = prefix.find(b"?>", 5)
            if end < 0:
                break
            prefix = prefix[end + 2 :].lstrip()
        else:
            break
    return prefix


@boundary
def validate_content(
    content: bytes, media_type: str, format_name: ContentFormat, *, source_url: str | None = None
) -> tuple[str, ...]:
    if not isinstance(content, bytes) or not 0 < len(content) <= 128 * 1024 * 1024:
        raise ToolsmithError("limit", "Response content exceeds its explicit bounds")
    if not isinstance(media_type, str):
        raise ToolsmithError("invalid_input", "Supply an explicit media type")
    prefix = markup_prefix(content)
    is_html = (
        media_type in {"text/html", "application/xhtml+xml"}
        or re.match(rb"<(?:!doctype\s+html|html|head|body|form|script|title)\b", prefix, re.I)
        is not None
    )
    if is_html and format_name != "html":
        raise ToolsmithError(
            "invalid_input", "Response contains HTML instead of the selected format"
        )
    if format_name in {"csv", "zip-csv", "gzip-csv"}:
        selected: TableFormat = (
            "zip-csv"
            if format_name == "zip-csv"
            else "gzip-csv"
            if format_name == "gzip-csv"
            else "csv"
        )
        unwrap(decode_table(content, selected))
    elif format_name == "json":
        unwrap(read_json(content, 128 * 1024 * 1024))
    elif format_name == "html":
        root = parse_html(content)
        check_access(root)
        if not content_text(root).strip():
            raise ToolsmithError("not_found", "HTML contains no readable static source text")
    elif format_name == "text":
        decode_text(content, 128 * 1024 * 1024)
    elif format_name == "pdf":
        if re.match(rb"%PDF-\d\.\d\b", prefix) is None:
            raise ToolsmithError("invalid_input", "Response lacks a PDF signature")
        return (
            "Only the PDF signature is checked; parsing, rendering and OCR remain caller-owned.",
        )
    elif format_name == "feed":
        if source_url is None:
            raise ToolsmithError("invalid_input", "Feed validation needs an explicit source URL")
        unwrap(read_feed(content, source_url, 1000))
    else:
        raise ToolsmithError("invalid_input", "Choose an explicitly supported content format")
    return ("Format checks do not establish source completeness or factual correctness.",)
