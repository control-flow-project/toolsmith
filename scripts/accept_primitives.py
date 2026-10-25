import asyncio
import importlib.metadata
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from toolsmith.acquisition.buckets import Bucket, run_buckets_async
from toolsmith.acquisition.urls import resolve_urls
from toolsmith.archives import list_archive, read_archive_member
from toolsmith.cli import main as cli
from toolsmith.readers import inspect_html, read_json_lines, read_xml
from toolsmith.readers.pdf import read_pdf, render_pdf_page
from toolsmith.result import unwrap


def blank_pdf() -> bytes:
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    )
    content = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = []
    for number, value in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    start = len(content)
    content.extend(b"xref\n0 5\n0000000000 65535 f \n")
    for offset in offsets:
        content.extend(f"{offset:010} 00000 n \n".encode())
    content.extend(f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(content)


async def accept_buckets() -> None:
    async def selected(value: str) -> str:
        return value

    results = unwrap(
        await run_buckets_async((Bucket("publisher", ("first", "second"), 0),), selected)
    )
    assert results[0].items == ("first", "second")


def main() -> int:
    assert importlib.metadata.version("ctlflow-toolsmith") == "0.5.0"
    asyncio.run(accept_buckets())
    assert "aiohttp" not in sys.modules and "pypdfium2" not in sys.modules
    threads = len(list(Path("/proc/self/task").iterdir()))
    inspected = unwrap(
        inspect_html(
            b'<meta name="author" content="Publisher"><main><a href="/report">Report</a></main>'
        )
    )
    assert inspected.links[0].target == "/report"
    assert inspected.metadata[0].content == "Publisher"
    wrapped = unwrap(
        inspect_html(
            b'<form><input type="hidden" value="opaque"><p>Public reporting.</p>'
            b'<a href="/release">Release</a></form>'
        )
    )
    assert wrapped.text == "Public reporting.\nRelease"
    assert wrapped.links[0].target == "/release"
    assert "opaque" not in wrapped.text
    assert unwrap(read_xml(b'<root><entry href="/one">One</entry></root>')).nodes == 2
    assert unwrap(read_json_lines(b'{"id":1}\n{"id":2}\n')) == ({"id": 1}, {"id": 2})
    assert len(unwrap(resolve_urls("https://example.com/index", ("/one", "/two")))) == 2
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as writer:
        writer.writestr("folder/", b"")
        writer.writestr("folder/report.txt", b"Report")
    pdf = blank_pdf()
    assert unwrap(read_pdf(pdf)).total_pages == 1
    rendered = unwrap(render_pdf_page(pdf, 0, dpi=72))
    assert rendered.width == rendered.height == 72 and rendered.content.startswith(b"\x89PNG")
    assert len(list(Path("/proc/self/task").iterdir())) == threads
    with tempfile.TemporaryDirectory(prefix="primitive-acceptance-") as temporary:
        root = Path(temporary)
        archive_file = root / "input.zip"
        archive_file.write_bytes(archive.getvalue())
        assert len(unwrap(list_archive(archive_file))) == 2
        assert unwrap(read_archive_member(archive_file, "folder/report.txt")) == b"Report"
        source, output = root / "source.xml", root / "result.json"
        source.write_bytes(b"<root/>")
        assert cli(["--output", str(output), "read", "xml", str(source)]) == 0
        assert json.loads(output.read_text())["result"]["root"]["name"] == "root"
        assert os.stat(output).st_mode & 0o777 == 0o600
    print("Installed primitives: XML/JSONL/HTML/URL/ZIP/PDF/CLI passed; no added threads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
