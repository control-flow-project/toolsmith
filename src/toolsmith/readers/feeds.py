import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import cast
from urllib.parse import urljoin

from toolsmith.acquisition.urls import canonical_url
from toolsmith.readers.text import decode_text
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer, text, timestamp


@dataclass(frozen=True)
class FeedEntry:
    url: str
    title: str
    excerpt: str
    published_original: str | None
    published_at: str | None


@dataclass(frozen=True)
class Feed:
    title: str
    entries: tuple[FeedEntry, ...]
    warnings: tuple[str, ...]


def local_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def field_value(element: ET.Element, name: str, maximum: int) -> str | None:
    for child in element:
        if local_tag(child) == name:
            return text(
                "".join(child.itertext()).strip(), maximum, "Feed " + name, allow_empty=True
            )
    return None


def feed_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return timestamp(value, "Feed date")
    except ToolsmithError:
        try:
            parsed = parsedate_to_datetime(value)
            return timestamp(parsed.isoformat(), "Feed date") if parsed.tzinfo is not None else None
        except (ValueError, TypeError, OverflowError):
            return None


@boundary
def read_feed(content: bytes, source_url: str, maximum_entries: int = 100) -> Feed:
    source = canonical_url(source_url)
    maximum = integer(maximum_entries, 1, 1000, "Maximum entries")
    decoded = decode_text(content)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", decoded, re.I):
        raise ToolsmithError("denied", "Feed DTDs and entity definitions are not permitted")
    parser: ET.XMLPullParser[ET.Element[str]] = ET.XMLPullParser(events=("start", "end"))
    depth = 0
    nodes = 0
    root: ET.Element | None = None
    try:
        for offset in range(0, len(decoded), 4096):
            parser.feed(decoded[offset : offset + 4096])
            for event, element in cast(
                "list[tuple[str, ET.Element[str]]]", list(parser.read_events())
            ):
                if event == "start":
                    if root is None:
                        root = element
                    depth += 1
                    nodes += 1
                    if depth > 32 or nodes > 50_000 or len(element.attrib) > 32:
                        raise ToolsmithError("limit", "Feed structure exceeds its bounded limits")
                else:
                    depth -= 1
        parser.close()
    except ET.ParseError as error:
        raise ToolsmithError("invalid_input", "Feed XML is malformed") from error
    if root is None or local_tag(root) not in {"rss", "feed"}:
        raise ToolsmithError("invalid_input", "Only RSS and Atom feeds are supported")
    container = next((child for child in root if local_tag(child) == "channel"), root)
    entries: dict[str, FeedEntry] = {}
    truncated = False
    for element in container:
        if local_tag(element) not in {"item", "entry"}:
            continue
        if len(entries) >= maximum:
            truncated = True
            break
        link = field_value(element, "link", 8192)
        if local_tag(element) == "entry":
            link = next(
                (
                    child.attrib.get("href")
                    for child in element
                    if local_tag(child) == "link"
                    and child.attrib.get("rel", "alternate") == "alternate"
                ),
                None,
            )
        if not link:
            raise ToolsmithError("invalid_input", "Feed entry lacks an explicit article link")
        url = canonical_url(urljoin(source, link))
        original = (
            field_value(element, "pubDate", 200)
            or field_value(element, "published", 200)
            or field_value(element, "updated", 200)
        )
        entry = FeedEntry(
            url,
            field_value(element, "title", 4096) or "Untitled entry",
            field_value(element, "description", 65_536)
            or field_value(element, "summary", 65_536)
            or "",
            original,
            feed_date(original),
        )
        if url in entries and entries[url] != entry:
            raise ToolsmithError("conflict", "Feed contains conflicting entries for the same URL")
        entries[url] = entry
    warnings: tuple[str, ...] = (
        "Feed discovery does not fetch articles; supplied dates and excerpts are unverified.",
    )
    if truncated:
        warnings += ("Entry limit reached; remaining entries were not returned.",)
    return Feed(
        field_value(container, "title", 4096) or "Untitled feed", tuple(entries.values()), warnings
    )
