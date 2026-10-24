import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from toolsmith.readers.text import decode_text, normalize_text
from toolsmith.result import ToolsmithError

OMIT = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "nav",
    "footer",
    "form",
    "iframe",
    "button",
    "select",
    "input",
    "textarea",
    "object",
    "embed",
    "canvas",
}
FORMS = {"form", "button", "select", "input", "textarea"}
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
BLOCK = {
    "p",
    "div",
    "section",
    "article",
    "main",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ul",
    "ol",
    "table",
    "tr",
    "blockquote",
    "pre",
    "br",
    "hr",
    "figcaption",
}
NOISE = re.compile(
    r"(?:^|[\s_-])(?:ads?|advert(?:isement|ising)?|sidebar|newsletter|"
    r"cookie|consent|share|social|related|recommended|sponsored)(?:$|[\s_-])",
    re.I,
)
NAVIGATION = re.compile(r"(?:^|[\s_-])(?:navigation|navbar)(?:$|[\s_-])", re.I)
READ_ATTRIBUTES = frozenset(
    {
        "aria-hidden",
        "aria-modal",
        "class",
        "content",
        "hidden",
        "href",
        "id",
        "itemprop",
        "poster",
        "property",
        "rel",
        "role",
        "src",
        "srcset",
        "style",
        "title",
        "type",
    }
)
ACCESS_HEADING = re.compile(
    r"(?:access denied|forbidden|unauthori[sz]ed|verify (?:that )?you are human|"
    r"checking your browser|security (?:check|verification)|just a moment|attention required|"
    r"sign ?in(?: to (?:your account|continue))?|log ?in(?: to (?:your account|continue))?|"
    r"authentication required|captcha|enable javascript and cookies)",
    re.I,
)
ACCESS_BODY = re.compile(
    r"(?:subscribe (?:to |and )(?:continue|read|unlock)|sign in to (?:read|continue)|"
    r"verify (?:that )?you are human|enable javascript and cookies|"
    r"complete (?:the |this )?(?:captcha|security check)|automated requests are blocked)",
    re.I,
)


@dataclass
class Node:
    tag: str
    attributes: dict[str, str]
    children: list["Node | str"] = field(default_factory=list)


def excluded(node: Node, *, include_forms: bool = False, include_navigation: bool = False) -> bool:
    attributes = node.attributes
    style = re.sub(r"\s+", "", attributes.get("style", "").lower())
    return (
        node.tag in OMIT
        and not (include_forms and node.tag in FORMS or include_navigation and node.tag == "nav")
        or "hidden" in attributes
        or attributes.get("aria-hidden", "").lower() == "true"
        or attributes.get("role", "").lower() in {"banner", "complementary"}
        or not include_navigation
        and attributes.get("role", "").lower() == "navigation"
        or "display:none" in style
        or "visibility:hidden" in style
        or bool(NOISE.search(attributes.get("id", "") + " " + attributes.get("class", "")))
        or not include_navigation
        and bool(NAVIGATION.search(attributes.get("id", "") + " " + attributes.get("class", "")))
    )


class MeaningfulParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]
        self.nodes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > 50_000 or len(self.stack) >= 128 or len(attrs) > 100:
            raise ToolsmithError("limit", "HTML exceeds its node, attribute or nesting budget")
        if len({name for name, _ in attrs}) != len(attrs):
            raise ToolsmithError("invalid_input", "HTML contains ambiguous duplicate attributes")
        if any(len(name) > 500 for name, _ in attrs):
            raise ToolsmithError("limit", "HTML attribute exceeds its field budget")
        selected = {name: value or "" for name, value in attrs if name in READ_ATTRIBUTES}
        if any(len(value) > 8192 for value in selected.values()):
            raise ToolsmithError("limit", "HTML reading attribute exceeds its field budget")
        if tag in {"p", "li"} and self.stack[-1].tag == tag:
            self.stack.pop()
        node = Node(tag, selected)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for position in range(len(self.stack) - 1, 0, -1):
            if self.stack[position].tag == tag:
                del self.stack[position:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(content: bytes) -> Node:
    parser = MeaningfulParser()
    try:
        parser.feed(decode_text(content, 4 * 1024 * 1024))
        parser.close()
    except (AssertionError, ValueError, RecursionError) as error:
        raise ToolsmithError(
            "invalid_input", "HTML declarations or structure are malformed"
        ) from error
    return parser.root


def descendants(
    node: Node, *, include_forms: bool = False, include_navigation: bool = False
) -> list[Node]:
    output: list[Node] = []
    pending = [node]
    while pending:
        current = pending.pop()
        if excluded(current, include_forms=include_forms, include_navigation=include_navigation):
            continue
        output.append(current)
        pending.extend(child for child in reversed(current.children) if isinstance(child, Node))
    return output


def content_text(node: Node, *, include_forms: bool = False) -> str:
    if excluded(node, include_forms=include_forms):
        return ""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        else:
            value = content_text(child, include_forms=include_forms)
            if child.tag in BLOCK:
                parts.extend(("\n", value, "\n"))
            elif child.tag in {"td", "th"}:
                parts.extend((value, "\t"))
            elif child.tag not in {"head", "title"}:
                parts.append(value)
    return "".join(parts)


def titles(nodes: list[Node]) -> list[str]:
    values = [normalize_text(content_text(node)) for node in nodes if node.tag == "title"]
    values.extend(
        node.attributes.get("content", "")
        for node in nodes
        if node.tag == "meta" and node.attributes.get("property", "").lower() == "og:title"
    )
    return [value for value in values if value.strip()]


def check_title_access(nodes: list[Node]) -> None:
    if any(ACCESS_HEADING.match(value.strip(" .!")) for value in titles(nodes)):
        raise ToolsmithError("denied", "HTML is an access/login/challenge screen; do not bypass it")


def check_access(root: Node) -> None:
    nodes = descendants(root, include_forms=True)
    check_title_access(nodes)
    for node in nodes:
        if node.attributes.get("aria-modal", "").lower() == "true" or node.attributes.get(
            "role", ""
        ).lower() in {"dialog", "alertdialog"}:
            region = descendants(node, include_forms=True)
            if (
                any(
                    child.tag == "input" and child.attributes.get("type", "").lower() == "password"
                    for child in region
                )
                or ACCESS_BODY.search(content_text(node, include_forms=True))
                or any(
                    re.fullmatch(r"h[1-6]", child.tag)
                    and ACCESS_HEADING.fullmatch(
                        normalize_text(content_text(child, include_forms=True)).strip(" .!")
                    )
                    for child in region
                )
            ):
                raise ToolsmithError(
                    "denied", "HTML contains an active access dialog; do not bypass it"
                )
    headings = [normalize_text(content_text(node)) for node in nodes if node.tag == "h1"]
    if any(ACCESS_HEADING.fullmatch(value.strip(" .!")) for value in headings):
        raise ToolsmithError("denied", "HTML is an access/login/challenge screen; do not bypass it")
    if not any(node.tag in {"article", "main"} for node in nodes) and (
        any(
            node.tag == "input" and node.attributes.get("type", "").lower() == "password"
            for node in nodes
        )
        or ACCESS_BODY.search(content_text(root))
    ):
        raise ToolsmithError("denied", "HTML is an active login form; do not bypass it")
