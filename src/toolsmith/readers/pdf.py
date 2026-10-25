import io
import math
from contextlib import closing
from dataclasses import dataclass
from importlib import import_module
from typing import BinaryIO, Literal, Protocol, cast

from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer

MAXIMUM_PDF_BYTES = 32 * 1024 * 1024


class Image(Protocol):
    def save(self, target: BinaryIO, format: str) -> None: ...
    def close(self) -> None: ...


class Bitmap(Protocol):
    width: int
    height: int

    def to_pil(self) -> Image: ...
    def close(self) -> None: ...


class TextPage(Protocol):
    def count_chars(self) -> int: ...
    def get_text_range(self, index: int, count: int, *, errors: str) -> str: ...
    def close(self) -> None: ...


class Page(Protocol):
    def get_textpage(self) -> TextPage: ...
    def get_size(self) -> tuple[float, float]: ...
    def render(self, *, scale: float, rev_byteorder: bool) -> Bitmap: ...
    def close(self) -> None: ...


class Document(Protocol):
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> Page: ...
    def close(self) -> None: ...


class Backend(Protocol):
    PdfiumError: type[Exception]

    def PdfDocument(self, content: bytes) -> Document: ...


@dataclass(frozen=True)
class PdfPageText:
    page: int
    text: str


@dataclass(frozen=True)
class PdfText:
    total_pages: int
    pages: tuple[PdfPageText, ...]
    next_page: int | None


@dataclass(frozen=True)
class PdfImage:
    page: int
    width: int
    height: int
    media_type: Literal["image/png"]
    content: bytes


def load_backend(content: bytes) -> Backend:
    if not isinstance(content, bytes):
        raise ToolsmithError("invalid_input", "PDF input must be bytes")
    if len(content) > MAXIMUM_PDF_BYTES:
        raise ToolsmithError("limit", "PDF input exceeds the 32 MiB limit")
    if not content.startswith(b"%PDF-"):
        raise ToolsmithError("invalid_input", "Input has no PDF header")
    try:
        return cast(Backend, import_module("pypdfium2"))
    except ImportError as error:
        raise ToolsmithError(
            "unavailable", "PDF reading requires the optional pdf dependency"
        ) from error


@boundary
def read_pdf(
    content: bytes,
    start: int = 0,
    limit: int = 20,
    *,
    maximum_text_bytes: int = 4 * 1024 * 1024,
) -> PdfText:
    first = integer(start, 0, 2**31 - 1, "First PDF page")
    count = integer(limit, 1, 1000, "PDF pages per read")
    maximum = integer(maximum_text_bytes, 1, 32 * 1024 * 1024, "PDF text bytes")
    backend = load_backend(content)
    try:
        with closing(backend.PdfDocument(content)) as document:
            total = len(document)
            if first >= total:
                raise ToolsmithError("invalid_input", "Requested PDF page is outside the document")
            pages: list[PdfPageText] = []
            used = 0
            for number in range(first, min(total, first + count)):
                with closing(document[number]) as page, closing(page.get_textpage()) as text_page:
                    characters = text_page.count_chars()
                    if characters < 0 or characters > maximum - used:
                        raise ToolsmithError(
                            "limit", "Selected PDF pages exceed the text budget; read fewer pages"
                        )
                    value = text_page.get_text_range(0, characters, errors="strict").replace(
                        "\r\n", "\n"
                    )
                    used += len(value.encode("utf-8"))
                    if used > maximum:
                        raise ToolsmithError(
                            "limit", "Selected PDF pages exceed the text budget; read fewer pages"
                        )
                    pages.append(PdfPageText(number, value))
            following = first + len(pages)
            return PdfText(total, tuple(pages), following if following < total else None)
    except (backend.PdfiumError, ValueError, OverflowError, UnicodeError) as error:
        raise ToolsmithError(
            "invalid_input", "PDF cannot be read or requires a password"
        ) from error


@boundary
def render_pdf_page(
    content: bytes,
    page: int,
    dpi: int = 144,
    *,
    maximum_pixels: int = 8 * 1024 * 1024,
    maximum_output_bytes: int = 32 * 1024 * 1024,
) -> PdfImage:
    number = integer(page, 0, 2**31 - 1, "PDF page")
    resolution = integer(dpi, 1, 300, "PDF render DPI")
    pixels = integer(maximum_pixels, 1, 32 * 1024 * 1024, "PDF render pixels")
    output_bytes = integer(maximum_output_bytes, 1, 128 * 1024 * 1024, "PNG output bytes")
    backend = load_backend(content)
    try:
        with closing(backend.PdfDocument(content)) as document:
            if number >= len(document):
                raise ToolsmithError("invalid_input", "Requested PDF page is outside the document")
            with closing(document[number]) as selected:
                width, height = selected.get_size()
                scale = resolution / 72
                if not all(math.isfinite(value) and value > 0 for value in (width, height)):
                    raise ToolsmithError("invalid_input", "PDF page dimensions are invalid")
                if math.ceil(width * scale) * math.ceil(height * scale) > pixels:
                    raise ToolsmithError("limit", "PDF render exceeds its pixel budget")
                with closing(selected.render(scale=scale, rev_byteorder=True)) as bitmap:
                    if bitmap.width * bitmap.height > pixels:
                        raise ToolsmithError("limit", "PDF render exceeds its pixel budget")
                    with closing(bitmap.to_pil()) as image, io.BytesIO() as output:
                        image.save(output, "PNG")
                        if output.tell() > output_bytes:
                            raise ToolsmithError("limit", "PDF render exceeds its PNG byte budget")
                        return PdfImage(
                            number, bitmap.width, bitmap.height, "image/png", output.getvalue()
                        )
    except ImportError as error:
        raise ToolsmithError(
            "unavailable", "PDF rendering requires the optional pdf dependencies"
        ) from error
    except (backend.PdfiumError, ValueError, OverflowError) as error:
        raise ToolsmithError("invalid_input", "PDF page cannot be rendered") from error
