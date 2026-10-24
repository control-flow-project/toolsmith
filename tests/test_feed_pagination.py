import json
from pathlib import Path

import pytest

from toolsmith.cli import main
from toolsmith.readers import read_feed
from toolsmith.result import Failure, unwrap

ATOM = "http://www.w3.org/2005/Atom"


def feed(links: str, *, atom: bool) -> bytes:
    if atom:
        return (f'<feed xmlns="{ATOM}">' + links + "</feed>").encode()
    return (f'<rss xmlns:atom="{ATOM}"><channel>' + links + "</channel></rss>").encode()


@pytest.mark.parametrize("atom", [True, False])
def test_next_page_is_resolved_for_atom_and_rss_without_following_it(atom: bool) -> None:
    prefix = "" if atom else "atom:"
    content = feed(f'<{prefix}link rel="next" href="?page=2"/>', atom=atom)
    selected = unwrap(read_feed(content, "https://example.com/current/feed"))
    assert selected.next_url == "https://example.com/current/feed?page=2"
    assert selected.entries == ()


@pytest.mark.parametrize("atom", [True, False])
def test_absent_next_is_explicit_and_previous_pages_are_not_substituted(atom: bool) -> None:
    prefix = "" if atom else "atom:"
    content = feed(f'<{prefix}link rel="previous" href="?page=1"/>', atom=atom)
    assert unwrap(read_feed(content, "https://example.com/feed")).next_url is None


def test_entry_pagination_does_not_impersonate_feed_pagination() -> None:
    content = feed(
        '<entry><title>Report</title><link href="/report"/>'
        '<link rel="next" href="/article-part-two"/></entry>',
        atom=True,
    )
    selected = unwrap(read_feed(content, "https://example.com/feed"))
    assert selected.next_url is None and selected.entries[0].url == "https://example.com/report"


def test_conflicting_next_pages_are_rejected() -> None:
    content = feed('<link rel="next" href="?page=2"/><link rel="next" href="?page=3"/>', atom=True)
    result = read_feed(content, "https://example.com/feed")
    assert isinstance(result, Failure) and result.code == "conflict"


def test_large_feed_returns_every_entry_without_an_item_ceiling() -> None:
    entries = "".join(
        f'<entry><title>Report {index}</title><link href="/report/{index}"/></entry>'
        for index in range(2500)
    )
    selected = unwrap(read_feed(feed(entries, atom=True), "https://example.com/feed"))
    assert len(selected.entries) == selected.total_entries == 2500
    assert selected.entries[-1].url == "https://example.com/report/2499"


def test_identical_next_targets_have_one_resolved_value() -> None:
    content = feed(
        '<link rel="next" href="/next"/><link rel="next" href="https://example.com/next"/>',
        atom=True,
    )
    assert (
        unwrap(read_feed(content, "https://example.com/feed")).next_url
        == "https://example.com/next"
    )


@pytest.mark.parametrize(
    "target",
    [
        "",
        "http://example.com/next",
        "https://user:secret@example.com/next",
        "file:///private",
        "/next?token=private",
    ],
)
def test_next_page_retains_the_reader_url_safety_boundary(target: str) -> None:
    result = read_feed(
        feed(f'<link rel="next" href="{target}"/>', atom=True), "https://example.com/feed"
    )
    assert isinstance(result, Failure)


def test_xml_base_is_consistent_for_next_pages_and_article_links() -> None:
    content = (
        f'<feed xmlns="{ATOM}" xml:base="/base/">'
        '<link rel="next" xml:base="pages/" href="two"/>'
        '<entry xml:base="articles/"><title>Report</title>'
        '<link xml:base="../reports/" href="one"/></entry></feed>'
    ).encode()
    selected = unwrap(read_feed(content, "https://example.com/feed"))
    assert selected.next_url == "https://example.com/base/pages/two"
    assert selected.entries[0].url == "https://example.com/base/reports/one"
    assert selected.entries[0].original_url == "one"


def test_cli_returns_the_same_next_page_without_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "feed.xml"
    content = feed('<link rel="next" href="/next"/>', atom=True)
    source.write_bytes(content)
    assert (
        main(["--json", "read", "feed", str(source), "--source-url", "https://example.com/feed"])
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert (
        output["result"]["next_url"]
        == unwrap(read_feed(content, "https://example.com/feed")).next_url
    )


def test_rss_root_channel_and_link_bases_have_one_resolution() -> None:
    content = (
        f'<rss xmlns:atom="{ATOM}" xml:base="/base/"><channel xml:base="channel/">'
        '<atom:link rel="next" xml:base="pages/" href="two"/>'
        '<item xml:base="articles/"><title>Report</title>'
        '<link xml:base="../reports/">one</link></item></channel></rss>'
    ).encode()
    selected = unwrap(read_feed(content, "https://example.com/feed"))
    assert selected.next_url == "https://example.com/base/channel/pages/two"
    assert selected.entries[0].url == "https://example.com/base/channel/reports/one"
