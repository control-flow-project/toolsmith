import json
from pathlib import Path

import pytest

from toolsmith.cli import main
from toolsmith.readers.pdf import MAXIMUM_PDF_BYTES, read_pdf, render_pdf_page
from toolsmith.result import Failure, unwrap


def pdf_document(pages: int = 1) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{4 + number * 2} 0 R".encode() for number in range(pages))
        + f"] /Count {pages} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for number in range(pages):
        stream = f"BT /F1 18 Tf 30 100 Td (Quarterly results page {number + 1}) Tj ET".encode()
        objects.extend(
            [
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
                + b"/Resources << /Font << /F1 3 0 R >> >> "
                + f"/Contents {5 + number * 2} 0 R >>".encode(),
                f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
            ]
        )
    content = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    start = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    content.extend(b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:]))
    content.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return bytes(content)


def test_native_pdf_text_pagination_has_explicit_continuation() -> None:
    content = pdf_document(3)
    first = unwrap(read_pdf(content, limit=2))
    assert first.total_pages == 3
    assert first.next_page == 2
    assert [page.page for page in first.pages] == [0, 1]
    assert first.pages[0].text == "Quarterly results page 1"
    final = unwrap(read_pdf(content, start=2))
    assert final.pages[0].text == "Quarterly results page 3"
    assert final.next_page is None


def test_native_pdf_render_produces_bounded_png() -> None:
    image = unwrap(render_pdf_page(pdf_document(), 0, dpi=72))
    assert (image.width, image.height, image.media_type) == (300, 200, "image/png")
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("content", [b"not a pdf", b"%PDF-invalid"])
def test_pdf_rejects_invalid_input(content: bytes) -> None:
    assert isinstance(read_pdf(content), Failure)
    assert isinstance(render_pdf_page(content, 0), Failure)


def test_pdf_input_size_is_always_at_most_thirty_two_mib() -> None:
    content = b"%PDF-" + b" " * MAXIMUM_PDF_BYTES
    result = read_pdf(content)
    assert isinstance(result, Failure) and result.code == "limit"


def test_pdf_limits_and_out_of_range_pages_fail_explicitly() -> None:
    content = pdf_document()
    assert isinstance(read_pdf(content, maximum_text_bytes=2), Failure)
    assert isinstance(read_pdf(content, start=1), Failure)
    assert isinstance(render_pdf_page(content, 1), Failure)
    pixels = render_pdf_page(content, 0, maximum_pixels=100)
    assert isinstance(pixels, Failure) and pixels.code == "limit"
    size = render_pdf_page(content, 0, maximum_output_bytes=1)
    assert isinstance(size, Failure) and size.code == "limit"


def test_pdf_cli_uses_the_same_reader_and_rendering_implementation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, destination = tmp_path / "document.pdf", tmp_path / "page.png"
    source.write_bytes(pdf_document())
    assert main(["--json", "read", "pdf", str(source)]) == 0
    assert (
        json.loads(capsys.readouterr().out)["result"]["pages"][0]["text"]
        == "Quarterly results page 1"
    )
    assert (
        main(
            [
                "--json",
                "render",
                "pdf",
                str(source),
                "--page",
                "0",
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["result"]["media_type"] == "image/png"
    assert destination.read_bytes().startswith(b"\x89PNG")
