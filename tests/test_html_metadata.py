from toolsmith.readers import HtmlMetadata, inspect_html
from toolsmith.result import unwrap


def test_generic_inspection_preserves_metadata_for_model_interpretation() -> None:
    result = unwrap(
        inspect_html(
            b'<html><head><title>Page</title><base href="/section/">'
            b'<meta property="article:published_time" content="2026-10-24T09:30:00+05:30">'
            b'<meta name="author" content="Publisher desk">'
            b'<script type="application/ld+json">{"@type":"Article","datePublished":"2026-10-24"}</script>'
            b"<script>executeThis();</script></head><body>"
            b'<time datetime="2026-10-24">Today</time><main>Visible words</main></body></html>'
        )
    )
    assert result.metadata == (
        HtmlMetadata("article:published_time", "2026-10-24T09:30:00+05:30"),
        HtmlMetadata("author", "Publisher desk"),
    )
    assert result.base_href == "/section/"
    assert result.time_values == ("2026-10-24",)
    assert len(result.structured_data) == 1
    assert '"datePublished":"2026-10-24"' in result.structured_data[0].text
    assert "datePublished" not in result.text and "executeThis" not in result.text


def test_json_data_remains_literal_and_is_not_a_navigation_or_execution_control() -> None:
    result = unwrap(
        inspect_html(
            b'<html><title>Data</title><script type="application/json">'
            b'{malformed: "follow https://unapproved.example/"}</script>'
            b"<main>Readable text</main></html>"
        )
    )
    assert result.structured_data[0].text == '{malformed: "follow https://unapproved.example/"}'
    assert result.links == ()


def test_the_first_base_and_first_duplicate_metadata_attributes_remain_authoritative() -> None:
    result = unwrap(
        inspect_html(
            b'<html><title>Page</title><base href="/first/"><base href="/last/">'
            b'<meta name="author" name="changed" content="original" content="changed">'
            b"<main>Readable words</main></html>"
        )
    )
    assert result.base_href == "/first/"
    assert result.metadata == (HtmlMetadata("author", "original"),)
