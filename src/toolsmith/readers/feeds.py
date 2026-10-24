import html
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urljoin

from toolsmith.acquisition.urls import canonical_url
from toolsmith.readers.html_dom import OMIT, content_text, parse_html
from toolsmith.readers.text import normalize_text
from toolsmith.readers.xml import XmlLimits, parse_tree
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import text

ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"


@dataclass(frozen=True)
class FeedEntry:
    url: str
    title: str
    excerpt: str
    published_original: str | None
    published_source_at: str | None
    published_at: str | None
    updated_original: str | None
    updated_source_at: str | None
    updated_at: str | None
    original_url: str


@dataclass(frozen=True)
class Feed:
    title: str
    entries: tuple[FeedEntry, ...]
    warnings: tuple[str, ...]
    total_entries: int
    duplicate_entries: int
    format: Literal["rss", "atom"]
    next_url: str | None


def selected(parent: ET.Element, name: str) -> ET.Element | None:
    matches = parent.findall(name)
    if len(matches) > 1:
        raise ToolsmithError("conflict", "Feed contains an ambiguous duplicate field")
    return matches[0] if matches else None


def markup_text(element: ET.Element) -> str:
    if element.tag.rsplit("}", 1)[-1].lower() in OMIT:
        return ""
    parts = [element.text or ""]
    for child in element:
        parts.extend((markup_text(child), child.tail or ""))
    return " ".join(parts)


def field_text(element: ET.Element | None, maximum: int) -> str | None:
    if element is None:
        return None
    value = markup_text(element)
    for _iteration in range(5):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    if html.unescape(value) != value:
        raise ToolsmithError("limit", "Feed field contains excessive nested escapes")
    parsed = parse_html(("<div>" + value + "</div>").encode())
    extracted = normalize_text(content_text(parsed))
    return text(extracted, maximum, "Feed field", allow_empty=True)


def feed_dates(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    try:
        try:
            instant = datetime.fromisoformat(value)
        except ValueError:
            instant = parsedate_to_datetime(value)
        if instant.utcoffset() is None:
            return None, None
        return instant.isoformat(), instant.astimezone(UTC).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None, None


def base_url(element: ET.Element, source: str) -> str:
    return canonical_url(urljoin(source, element.attrib.get(XML_BASE, "")))


def next_page(container: ET.Element, source: str) -> str | None:
    targets: set[str] = set()
    for link in container.findall(ATOM + "link"):
        if link.attrib.get("rel") != "next":
            continue
        target = text(link.attrib.get("href"), 8192, "Next feed page")
        targets.add(canonical_url(urljoin(base_url(link, source), target)))
    if len(targets) > 1:
        raise ToolsmithError("conflict", "Feed declares conflicting next-page links")
    return next(iter(targets)) if targets else None


def feed_entry(element: ET.Element, source: str, atom: bool) -> FeedEntry:
    source = base_url(element, source)
    prefix = ATOM if atom else ""
    title = field_text(selected(element, prefix + "title"), 1024)
    if not title:
        raise ToolsmithError("invalid_input", "Feed entry needs a meaningful title")
    if atom:
        links = {
            (child.attrib.get("href", ""), base_url(child, source))
            for child in element.findall(ATOM + "link")
            if child.attrib.get("rel", "alternate") == "alternate"
            and child.attrib.get("type", "text/html") in {"text/html", "application/xhtml+xml"}
        }
        if len(links) != 1:
            raise ToolsmithError("conflict", "Atom needs one unambiguous alternate article link")
        original_link, link_base = next(iter(links))
        url = canonical_url(urljoin(link_base, original_link))
    else:
        linked = selected(element, "link")
        link = field_text(linked, 8192)
        if not link:
            raise ToolsmithError("invalid_input", "Feed entry lacks an explicit article link")
        original_link = link
        url = canonical_url(
            urljoin(base_url(linked, source) if linked is not None else source, original_link)
        )
    publication = selected(element, prefix + ("published" if atom else "pubDate"))
    if publication is None and not atom:
        publication = selected(element, DC + "date")
    original = field_text(publication, 200)
    update = field_text(selected(element, ATOM + "updated"), 200) if atom else None
    excerpt = selected(element, prefix + ("summary" if atom else "description"))
    if excerpt is None and atom:
        excerpt = selected(element, ATOM + "content")
    source_at, utc_at = feed_dates(original)
    updated_source_at, updated_at = feed_dates(update)
    return FeedEntry(
        url,
        title,
        field_text(excerpt, 65536) or "",
        original,
        source_at,
        utc_at,
        update,
        updated_source_at,
        updated_at,
        original_link,
    )


@boundary
def read_feed(content: bytes, source_url: str) -> Feed:
    source = canonical_url(source_url)
    root, _ = parse_tree(
        content,
        XmlLimits(
            maximum_bytes=2 * 1024 * 1024,
            maximum_nodes=2_000_000,
            maximum_depth=32,
            maximum_attributes=16,
            maximum_name_characters=500,
            maximum_attribute_bytes=8192,
            maximum_text_bytes=32768,
        ),
    )
    source = base_url(root, source)
    if root.tag == "rss":
        channel = selected(root, "channel")
        if channel is None:
            raise ToolsmithError("invalid_input", "RSS requires exactly one channel")
        entries = channel.findall("item")
        container, atom = channel, False
        source = base_url(channel, source)
    elif root.tag == ATOM + "feed":
        entries = root.findall(ATOM + "entry")
        container, atom = root, True
    else:
        raise ToolsmithError("invalid_input", "Only RSS and namespaced Atom are supported")
    distinct: dict[str, FeedEntry] = {}
    for element in entries:
        entry = feed_entry(element, source, atom)
        if entry.url in distinct and distinct[entry.url] != entry:
            raise ToolsmithError("conflict", "Feed contains conflicting entries for one URL")
        distinct[entry.url] = entry
    warnings: tuple[str, ...] = (
        "Feed discovery does not fetch articles; supplied dates and excerpts are unverified.",
    )
    return Feed(
        field_text(selected(container, (ATOM if atom else "") + "title"), 1024) or "Untitled feed",
        tuple(distinct.values()),
        warnings,
        len(entries),
        len(entries) - len(distinct),
        "atom" if atom else "rss",
        next_page(container, source),
    )
