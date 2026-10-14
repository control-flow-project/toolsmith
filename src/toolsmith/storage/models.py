import re
from dataclasses import dataclass

from toolsmith.readers import models as reader_models
from toolsmith.result import ToolsmithError
from toolsmith.validation import fields, integer, text, timestamp

MAX_TEXT_BYTES = 4 * 1024 * 1024
MAX_PARTS = 1000


@dataclass(frozen=True)
class TextReference:
    collection: str
    item: str
    version: str
    title: str
    parts: int
    content_bytes: int
    recorded_at: str
    reused: bool


@dataclass(frozen=True)
class FileReference:
    collection: str
    version: str
    name: str
    media_type: str
    content_sha256: str
    content_bytes: int
    source_url: str | None
    recorded_at: str
    reused: bool


def validate_document(document: reader_models.Document) -> reader_models.Document:
    if (
        not isinstance(document, reader_models.Document)
        or not isinstance(document.parts, tuple)
        or not 1 <= len(document.parts) <= MAX_PARTS
    ):
        raise ToolsmithError("invalid_input", "Document requires 1..1000 immutable text parts")
    title = text(document.title, 1024, "Title")
    method = text(document.method, 80, "Method")
    parts: list[reader_models.TextPart] = []
    total = 0
    for part in document.parts:
        if (
            not isinstance(part, reader_models.TextPart)
            or not isinstance(part.warnings, tuple)
            or len(part.warnings) > 64
        ):
            raise ToolsmithError("invalid_input", "Part requires bounded immutable warnings")
        body = text(part.text, MAX_TEXT_BYTES, "Part text", allow_empty=True)
        total += len(body.encode("utf-8"))
        if total > MAX_TEXT_BYTES:
            raise ToolsmithError("limit", "Document exceeds its total text byte limit")
        page = (
            None
            if part.physical_page is None
            else integer(part.physical_page, 1, 1_000_000, "Physical page")
        )
        parts.append(
            reader_models.TextPart(
                text(part.label, 200, "Part label"),
                body,
                page,
                tuple(text(warning, 1024, "Warning") for warning in part.warnings),
            )
        )
    if not any(part.text.strip() for part in parts):
        raise ToolsmithError("invalid_input", "Document requires meaningful text")
    source: str | None = None
    if document.source_url is not None:
        from toolsmith.acquisition.urls import canonical_url

        source = canonical_url(document.source_url)
    return reader_models.Document(
        title,
        tuple(parts),
        method,
        source,
        timestamp(document.published_at),
        timestamp(document.observed_at),
    )


def document_from_json(value: object) -> reader_models.Document:
    data = fields(
        value, {"title", "parts"}, {"method", "source_url", "published_at", "observed_at"}
    )
    supplied = data["parts"]
    if not isinstance(supplied, list) or not 1 <= len(supplied) <= MAX_PARTS:
        raise ToolsmithError("invalid_input", "Document requires a bounded parts array")
    parts: list[reader_models.TextPart] = []
    for entry in supplied:
        part = fields(entry, {"label", "text"}, {"physical_page", "warnings"})
        warnings = part.get("warnings", [])
        if not isinstance(warnings, list) or len(warnings) > 64:
            raise ToolsmithError("invalid_input", "Part warnings require a bounded array")
        page = part.get("physical_page")
        parts.append(
            reader_models.TextPart(
                text(part["label"], 200, "Part label"),
                text(part["text"], MAX_TEXT_BYTES, "Part text", allow_empty=True),
                None if page is None else integer(page, 1, 1_000_000, "Physical page"),
                tuple(text(warning, 1024, "Warning") for warning in warnings),
            )
        )
    return validate_document(
        reader_models.Document(
            text(data["title"], 1024, "Title"),
            tuple(parts),
            text(data.get("method", "provided-text"), 80, "Method"),
            None
            if data.get("source_url") is None
            else text(data["source_url"], 8192, "Source URL"),
            timestamp(data.get("published_at")),
            timestamp(data.get("observed_at")),
        )
    )


def file_name(value: object) -> str:
    name = text(value, 200, "File name")
    if name in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,199}", name):
        raise ToolsmithError("invalid_input", "File name must be a machine-neutral leaf name")
    return name


def media_type(value: object) -> str:
    selected = text(value, 200, "Media type")
    if not re.fullmatch(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*", selected):
        raise ToolsmithError("invalid_input", "Media type must be a simple lowercase MIME type")
    return selected
