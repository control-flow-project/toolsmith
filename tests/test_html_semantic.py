import builtins
from pathlib import Path
from unittest.mock import patch

from toolsmith.readers import inspect_html
from toolsmith.readers.html_dom import READ_ATTRIBUTES, parse_html
from toolsmith.result import Failure, unwrap


def test_actual_publisher_decorative_span_with_118_attributes_remains_readable() -> None:
    original = (Path(__file__).parent / "fixtures/html/publisher-many-attributes.html").read_bytes()
    result = unwrap(inspect_html(b"<main><h1>Results</h1>" + original + b"<p>Report.</p></main>"))
    assert "<h1>Results</h1>" in result.semantic_html
    assert "<p>Report.</p>" in result.semantic_html
    assert "data-cf-" not in result.semantic_html
    assert "onclick" not in result.semantic_html


def test_omitted_head_and_body_closures_do_not_discard_html5_article_elements() -> None:
    original = b"<html><title>Results</title><article><h1>Results</h1><p>Revenue rose.</p></article></html>"
    result = unwrap(inspect_html(original))
    assert result.text == "Results\nRevenue rose."
    assert result.semantic_html == "<h1>Results</h1><p>Revenue rose.</p>"


def test_semantic_html_keeps_structure_without_any_attributes_or_duplicate_page_state() -> None:
    original = b"""<!doctype html><html><head><title>Results</title>
    <script type="application/ld+json">{"articleBody":"duplicate body"}</script></head>
    <body><nav>Navigation</nav><main class="layout" data-state="tracking">
    <h1 id="headline" style="font-size:40px">Company results</h1>
    <p class="body">Revenue <b data-extra="x">rose</b> 20% &amp; profit rose 5%.</p>
    <ul class="items"><li data-key="1">First fact</li></ul>
    <table class="data"><tr><th scope="col">Revenue</th><td data-x="2">120</td></tr></table>
    <a href="https://example.org">Source</a><div class="related">Other stories</div>
    <div hidden>Hidden story</div></main><footer>Footer</footer></body></html>"""
    result = unwrap(inspect_html(original))
    assert "<h1>Company results</h1>" in result.semantic_html
    assert "<p>Revenue <strong>rose</strong> 20% &amp; profit rose 5%.</p>" in result.semantic_html
    assert "<ul><li>First fact</li></ul>" in result.semantic_html
    assert "<table><tr><th>Revenue</th><td>120</td></tr></table>" in result.semantic_html
    for forbidden in (
        "class=",
        "style=",
        "data-",
        "id=",
        "href=",
        "scope=",
        "<script",
        "<nav",
        "duplicate body",
        "Other stories",
        "Hidden story",
        "Footer",
    ):
        assert forbidden not in result.semantic_html, forbidden
    # The literal link is still available to the caller, never in the semantic body.
    assert result.links[0].target == "https://example.org"


def test_many_ignored_attributes_do_not_discard_a_valid_page_or_expand_retained_attributes() -> (
    None
):
    attributes = " ".join(f'data-{n}="tracking"' for n in range(114))
    original = f"<main><h1 {attributes}>Reporting</h1><p>Full report.</p></main>".encode()
    result = unwrap(inspect_html(original))
    assert result.semantic_html == "<h1>Reporting</h1><p>Full report.</p>"
    root = parse_html(original)
    pending = [root]
    while pending:
        node = pending.pop()
        assert node.attributes.keys() <= READ_ATTRIBUTES
        pending.extend(child for child in node.children if not isinstance(child, str))


def test_encoded_text_cannot_become_markup_and_inline_word_spacing_is_preserved() -> None:
    result = unwrap(
        inspect_html(
            b"<main><p>One <em>two</em> <b>three</b> &lt;script&gt;literal&lt;/script&gt;</p></main>"
        )
    )
    assert (
        result.semantic_html
        == "<p>One <em>two</em> <strong>three</strong> &lt;script&gt;literal&lt;/script&gt;</p>"
    )


def test_table_spans_keep_cell_relationships_without_decorative_attributes() -> None:
    result = unwrap(
        inspect_html(
            b'<table><tr><th colspan="2" class="tracking">Reported amounts</th></tr>'
            b'<tr><td rowspan="2" onclick="bad()">Revenue</td><td>120</td></tr>'
            b"<tr><td>140</td></tr></table>"
        )
    )
    assert '<th colspan="2">Reported amounts</th>' in result.semantic_html
    assert '<td rowspan="2">Revenue</td>' in result.semantic_html
    assert "onclick" not in result.semantic_html
    assert "class=" not in result.semantic_html


def test_missing_html_dependency_fails_without_selecting_another_parser() -> None:
    imported = builtins.__import__

    def load(name: str, *args: object, **kwargs: object) -> object:
        if name == "bs4":
            raise ImportError("Optional dependency intentionally absent")
        return imported(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=load):
        result = inspect_html(b"<p>Reporting</p>")
    assert isinstance(result, Failure)
    assert result.code == "unavailable"
