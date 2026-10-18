import gzip
import io
import zipfile

import pytest

from toolsmith.readers import inspect_html, read_feed, read_html
from toolsmith.readers.content import validate_content
from toolsmith.readers.json import read_json
from toolsmith.readers.tables import decode_table, iter_table_rows, project_table
from toolsmith.result import Failure, unwrap

PROSE = (
    "This is substantial source prose with ordinary statements and no acquisition instructions. "
    * 4
)


def test_article_title_selection_ambiguity_and_table_warning() -> None:
    document = (
        "<title>Publisher</title><main><article><h1>Intended report</h1><p>"
        + PROSE
        + "</p><table><tr><td>10</td></tr></table></article><article><h1>Other report</h1><p>"
        + PROSE
        + "</p></article></main>"
    ).encode()
    ambiguous = read_html(document, selection="article")
    assert isinstance(ambiguous, Failure) and ambiguous.code == "conflict"
    selected = unwrap(read_html(document, "Intended report", selection="article"))
    assert selected.title == "Intended report" and "Other report" not in selected.parts[0].text
    assert any("Table text" in warning for warning in selected.parts[0].warnings)
    assert isinstance(read_html(document, "Missing report", selection="article"), Failure)


@pytest.mark.parametrize(
    "blocked",
    [
        "<title>Access denied</title><main>content</main>",
        "<title>Access denied | Publisher</title><main>content</main>",
        '<div role="dialog"><h2>Sign in</h2></div><main>content</main>',
        '<form><input type="password"></form><p>Login</p>',
        '<main><p>source</p></main><div role="dialog"><input type="password"></div>',
        '<main><p>source</p></main><div aria-modal="true">Subscribe to continue</div>',
        "<h1>Verify you are human</h1><p>challenge</p>",
    ],
)
def test_html_rejects_active_access_gates_without_bypass(blocked: str) -> None:
    result = read_html(blocked.encode())
    assert isinstance(result, Failure) and result.code == "denied"


def test_inspection_does_not_claim_uncomputed_dialog_visibility() -> None:
    content = (
        "<title>Research note</title><style>.login {display:none}</style>"
        "<article><h1>Research note</h1><p>"
        + PROSE
        + '</p></article><div class="login" role="dialog"><input type="password"></div>'
    ).encode()
    observed = unwrap(inspect_html(content))
    assert observed.content_root and observed.password_controls
    assert observed.title == "Research note"
    denied = read_html(content, selection="article")
    assert isinstance(denied, Failure) and denied.code == "denied"
    assert isinstance(inspect_html(b"<title>Access denied</title><script>loop()</script>"), Failure)


def test_html_noise_is_not_article_content_and_tables_are_not_financial_models() -> None:
    content = b'<main><h1>Title</h1><p>Visible</p><div class="related">noise</div><span aria-hidden="TRUE">hidden</span><table><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>10</td></tr></table></main>'
    result = unwrap(read_html(content))
    assert "noise" not in result.parts[0].text and "hidden" not in result.parts[0].text
    assert any("Table text" in warning for warning in result.parts[0].warnings)


def test_feed_retains_publication_and_update_offsets_and_unknown_dates() -> None:
    content = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Report</title><link href="/report"/><published>2026-10-12T23:30:00-05:00</published><updated>unknown</updated><summary>&amp;lt;p&amp;gt;Excerpt&amp;lt;/p&amp;gt;</summary></entry></feed>'
    entry = unwrap(read_feed(content, "https://example.com/feed")).entries[0]
    assert entry.published_original == "2026-10-12T23:30:00-05:00"
    assert entry.published_source_at == entry.published_original
    assert entry.published_at == "2026-10-13T04:30:00+00:00"
    assert entry.updated_original == "unknown" and entry.updated_at is None
    assert entry.excerpt == "Excerpt"


def test_feed_duplicate_counts_truncation_and_omitted_entry_validation() -> None:
    first = '<entry><title>First</title><link href="/first"/></entry>'
    second = '<entry><title>Second</title><link href="/second"/></entry>'
    prefix = '<feed xmlns="http://www.w3.org/2005/Atom">'
    feed = unwrap(
        read_feed(
            (prefix + first + first + second + "</feed>").encode(), "https://example.com/feed", 1
        )
    )
    assert [entry.title for entry in feed.entries] == ["First"]
    assert feed.total_entries == 3 and feed.duplicate_entries == 1 and feed.truncated
    assert any("Entry limit reached" in warning for warning in feed.warnings)
    conflict = second.replace("/second", "/first")
    assert isinstance(
        read_feed(
            (prefix + first + second + conflict + "</feed>").encode(), "https://example.com/feed", 1
        ),
        Failure,
    )
    invalid = "<entry><title>Invalid</title></entry>"
    assert isinstance(
        read_feed((prefix + first + invalid + "</feed>").encode(), "https://example.com/feed", 1),
        Failure,
    )


@pytest.mark.parametrize(
    "entry",
    [
        '<title>A</title><title>B</title><link href="/one"/>',
        '<title>A</title><link href="/one"/><link href="/two"/>',
        '<title>A</title><link href="/one"/><updated>one</updated><updated>two</updated>',
    ],
)
def test_feed_ambiguous_fields_are_not_selected_silently(entry: str) -> None:
    content = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>' + entry + "</entry></feed>"
    ).encode()
    assert isinstance(read_feed(content, "https://example.com/feed"), Failure)


def test_tabular_decoding_and_projection_preserve_counts_and_values() -> None:
    content = b"Name,Value\nA,10\nB,20\nA,30\n"
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("report.csv", content)
    for supplied, format_name in (
        (content, "csv"),
        (gzip.compress(content), "gzip-csv"),
        (zipped.getvalue(), "zip-csv"),
    ):
        if format_name == "csv":
            decoded = unwrap(decode_table(supplied, "csv"))
        elif format_name == "gzip-csv":
            decoded = unwrap(decode_table(supplied, "gzip-csv"))
        else:
            decoded = unwrap(decode_table(supplied, "zip-csv"))
        projected = unwrap(project_table(decoded, ("Value",), {"Name": "A"}, 1))
        assert projected.scanned == 3 and projected.matched == 2 and projected.truncated
        assert projected.rows == ({"Value": "10"},)
        assert [unwrap(row) for row in iter_table_rows(decoded)] == [
            {"Name": "A", "Value": "10"},
            {"Name": "B", "Value": "20"},
            {"Name": "A", "Value": "30"},
        ]


@pytest.mark.parametrize(
    "body",
    [
        "Name,Name\nA,B\n",
        "Name,Value\nA\n",
        "Name,Value\nA,10,20\n",
        'Name,Value\n"unfinished,10\n',
    ],
)
def test_invalid_table_rows_are_expected_results(body: str) -> None:
    assert isinstance(project_table(body, ("Name",), {}), Failure)
    results = tuple(iter_table_rows(body))
    assert results and isinstance(results[-1], Failure)


def test_csv_explicit_budgets_are_not_corpus_or_header_position_ceilings() -> None:
    content = "Preamble\n" * 30 + "Name,Value\nA,10\nB,20\n"
    projected = unwrap(
        project_table(content, ("Value",), {}, header_row=31, maximum_rows=2_000_000)
    )
    assert projected.scanned == 2 and projected.rows == ({"Value": "10"}, {"Value": "20"})
    rows = iter_table_rows(content, header_row=31, maximum_rows=2**63 - 1)
    assert [unwrap(row) for row in rows] == [
        {"Name": "A", "Value": "10"},
        {"Name": "B", "Value": "20"},
    ]


def test_tabular_unsafe_archives_and_limits_do_not_return_prefixes() -> None:
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("../report.csv", "Name,Value\nA,10\n")
    assert isinstance(decode_table(zipped.getvalue(), "zip-csv"), Failure)
    assert isinstance(
        decode_table(gzip.compress(b"Name,Value\nA,10\n") + gzip.compress(b"x"), "gzip-csv"),
        Failure,
    )
    assert isinstance(
        project_table("Name,Value\nA,10\nA,20\n", ("Value",), {}, maximum_rows=1), Failure
    )


@pytest.mark.parametrize(
    "content",
    [
        b"<table><tr><td>One</td><td>Two</td></tr><tr><td>One</td></tr></table>",
        b"<table><tr><td><table><tr><td>Nested</td></tr></table></td></tr></table>",
        b'<table><tr><td rowspan="2">Spanning</td></tr></table>',
    ],
)
def test_html_tables_remain_source_text_without_deterministic_geometry(content: bytes) -> None:
    from toolsmith import readers

    result = unwrap(read_html(content))
    assert result.parts[0].text
    assert any("Table text" in warning for warning in result.parts[0].warnings)
    assert not hasattr(readers, "read_html_tables")
    assert not hasattr(readers, "HtmlTable")


def test_response_formats_are_not_confused_with_login_pages_or_pdf_parsers() -> None:
    assert isinstance(
        validate_content(b"<!-- comment --><html>login</html>", "text/plain", "csv"), Failure
    )
    assert isinstance(read_json(b'{"duplicate":1,"duplicate":2}'), Failure)
    assert isinstance(read_json(b'{"value":NaN}'), Failure)
    warnings = unwrap(validate_content(b"%PDF-1.7\nbytes", "application/pdf", "pdf"))
    assert warnings == (
        "Only the PDF signature is checked; parsing, rendering and OCR remain caller-owned.",
    )
