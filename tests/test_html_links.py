import pytest

from toolsmith.readers import HtmlLink, inspect_html, read_html
from toolsmith.result import Failure, unwrap


def test_duplicate_html_attributes_preserve_the_first_link_target_and_metadata() -> None:
    inspected = unwrap(
        inspect_html(
            b'<main><a href="/first" HREF="/second" rel="author" rel="external">Article</a></main>'
        )
    )
    assert inspected.links == (HtmlLink("/first", "Article", ("author",), None, False),)
    assert inspected.text == "Article"


def test_duplicate_visibility_attributes_do_not_reveal_hidden_content() -> None:
    inspected = unwrap(
        inspect_html(
            b'<main><p>Visible</p><div style="display:none" style="">'
            b'<a href="/hidden">Hidden</a></div></main>'
        )
    )
    assert inspected.links == ()
    assert inspected.text == "Visible"


def test_duplicate_unused_attributes_do_not_block_readable_html() -> None:
    content = b'<main data-layout="wide" data-layout="narrow"><p>Reporting</p></main>'
    assert unwrap(read_html(content)).parts[0].text == "Reporting"


def test_linked_inspection_keeps_navigation_and_feed_metadata_outside_cleaned_text() -> None:
    content = b"""<html><head><title>Publisher</title>
    <link rel="alternate" type="application/rss+xml" href="/feed.xml" title="News feed">
    </head><body><nav><a href="/industry">Industry</a></nav>
    <main><h1>Current reporting</h1><a href="/one?x=1&amp;y=2">First <b>article</b></a>
    <div role="navigation"><a href="../markets">Markets</a></div></main></body></html>"""
    inspected = unwrap(inspect_html(content))
    assert inspected.links == (
        HtmlLink("/feed.xml", "News feed", ("alternate",), "application/rss+xml", False),
        HtmlLink("/industry", "Industry", (), None, False),
        HtmlLink("/one?x=1&y=2", "First article", (), None, False),
        HtmlLink("../markets", "Markets", (), None, False),
    )
    assert "Industry" not in inspected.text
    assert "Markets" not in inspected.text
    assert "First article" in inspected.text
    assert "First article" in unwrap(read_html(content)).parts[0].text


def test_links_do_not_follow_urls_or_extract_hidden_advertising_or_template_content() -> None:
    content = b"""<main><p>Visible</p>
    <a href="javascript:alert(1)">Untrusted target</a>
    <div hidden><a href="/hidden">Hidden</a></div>
    <nav aria-hidden="true"><a href="/hidden-navigation">Hidden navigation</a></nav>
    <div class="advertisement"><a href="https://ads.example.com">Advertisement</a></div>
    <template><a href="/template">Not rendered</a></template>
    <script>const markup = '<a href="/script">Not markup</a>';</script>
    </main>"""
    inspected = unwrap(inspect_html(content))
    assert inspected.links == (
        HtmlLink("javascript:alert(1)", "Untrusted target", (), None, False),
    )
    assert "Not rendered" not in inspected.text


def test_navigation_class_does_not_override_hidden_or_advertising_markers() -> None:
    content = b"""<div class="navbar"><a href="/news">News</a></div>
    <div class="navbar advertisement"><a href="/ad">Advertisement</a></div>
    <nav style="display:none"><a href="/hidden">Hidden</a></nav>"""
    assert unwrap(inspect_html(content)).links == (HtmlLink("/news", "News", (), None, False),)


def test_link_labels_report_truncation_without_changing_target_or_full_text() -> None:
    label = "a" * 1200
    inspected = unwrap(inspect_html(f'<main><a href="/one">{label}</a></main>'.encode()))
    assert inspected.links == (HtmlLink("/one", label[:1000], (), None, True),)
    assert inspected.text == label


def test_ignored_large_data_attributes_do_not_block_readable_content() -> None:
    ignored = "x" * 20000
    content = (
        '<html><title>Readable result</title><script data-state="'
        + ignored
        + '">not readable</script><main data-props="'
        + ignored
        + '"><p>Relevant reporting.</p><a href="/next">Next</a></main></html>'
    ).encode()
    assert unwrap(read_html(content)).parts[0].text == "Relevant reporting.\nNext"
    inspected = unwrap(inspect_html(content))
    assert inspected.links == (HtmlLink("/next", "Next", (), None, False),)
    assert ignored not in inspected.text


@pytest.mark.parametrize("attribute", ["href", "style", "class", "role", "src", "content"])
def test_large_reading_attributes_remain_bounded(attribute: str) -> None:
    content = f'<main {attribute}="{"x" * 8193}"><p>Reporting.</p></main>'.encode()
    assert isinstance(inspect_html(content), Failure)
    assert isinstance(read_html(content), Failure)


def test_duplicate_ignored_attributes_do_not_weaken_access_checks() -> None:
    assert unwrap(inspect_html(b'<main data-key="one" data-key="two">Text</main>')).text == "Text"
    assert isinstance(inspect_html(b"<title>Access denied</title><a href='/one'>One</a>"), Failure)
    gated = b"""<main>Reporting</main><div role="dialog" aria-modal="true">
    <p>Subscribe to read</p><input type="password"></div>"""
    assert isinstance(read_html(gated), Failure)
    assert unwrap(inspect_html(gated)).password_controls
