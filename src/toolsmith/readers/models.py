from dataclasses import dataclass

MAX_TEXT_BYTES = 144 * 1024 * 1024


@dataclass(frozen=True)
class TextPart:
    label: str
    text: str
    physical_page: int | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Document:
    title: str
    parts: tuple[TextPart, ...]
    method: str = "provided-text"
    source_url: str | None = None
    published_at: str | None = None
    observed_at: str | None = None
