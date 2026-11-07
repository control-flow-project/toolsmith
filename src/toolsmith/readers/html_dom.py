import re
from dataclasses import dataclass, field
from html import escape

from toolsmith.readers.text import decode_text, normalize_text
from toolsmith.result import ToolsmithError
from toolsmith.validation import integer

DEFAULT_HTML_BYTES = 4 * 1024 * 1024
MAX_HTML_BYTES = 8 * 1024 * 1024
DEFAULT_HTML_NODES = 50_000
MAX_HTML_NODES = 500_000

OMIT = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "nav",
    "footer",
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
        "datetime",
        "hidden",
        "href",
        "id",
        "itemprop",
        "name",
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


def parse_html(
    content: bytes,
    *,
    maximum_bytes: int = DEFAULT_HTML_BYTES,
    maximum_nodes: int = DEFAULT_HTML_NODES,
) -> Node:
    maximum = integer(maximum_bytes, 1, MAX_HTML_BYTES, "Maximum HTML bytes")
    nodes = integer(maximum_nodes, 1, MAX_HTML_NODES, "Maximum HTML nodes")
    try:
        from bs4 import BeautifulSoup, Comment, Declaration, Doctype, FeatureNotFound, Tag
        from bs4.element import NavigableString
    except ImportError as error:
        raise ToolsmithError(
            "unavailable", "HTML reading requires the optional html extra"
        ) from error
    try:
        document = BeautifulSoup(
            decode_text(content, maximum), "lxml", multi_valued_attributes=None
        )
    except FeatureNotFound as error:
        raise ToolsmithError(
            "unavailable", "HTML reading requires the optional html extra"
        ) from error
    except (AssertionError, ValueError, RecursionError) as error:
        raise ToolsmithError(
            "invalid_input", "HTML declarations or structure are malformed"
        ) from error
    root = Node("root", {})
    pending = [(child, root, 1) for child in reversed(document.contents)]
    count = 0
    while pending:
        child, parent, depth = pending.pop()
        if isinstance(child, (Comment, Declaration, Doctype)):
            continue
        if isinstance(child, Tag):
            count += 1
            if count > nodes:
                raise ToolsmithError("limit", f"HTML node budget exceeded: {count} > {nodes}")
            if depth >= 128:
                raise ToolsmithError("limit", f"HTML nesting budget exceeded: {depth} >= 128")
            attributes: dict[str, str] = {}
            for name in READ_ATTRIBUTES:
                value = child.attrs.get(name)
                if name in child.attrs:
                    attributes[name] = " ".join(value) if isinstance(value, list) else value or ""
            node = Node(child.name, attributes)
            parent.children.append(node)
            pending.extend((item, node, depth + 1) for item in reversed(child.contents))
        elif isinstance(child, NavigableString):
            parent.children.append(str(child))
    return root


SEMANTIC_TAGS = frozenset(
    [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "ul",
        "ol",
        "li",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "blockquote",
        "pre",
        "code",
        "strong",
        "em",
        "br",
        "hr",
        "sub",
        "sup",
        "dl",
        "dt",
        "dd",
    ]
)


def content_html(node: Node) -> str:
    """One semantic rendering: no attributes, resources, page controls or scripts."""
    if excluded(node) or node.tag == "title":
        return ""
    parts = [
        escape(re.sub(r"\s+", " ", child), quote=False)
        if isinstance(child, str)
        else content_html(child)
        for child in node.children
    ]
    body = "".join(parts)
    tag = {"b": "strong", "i": "em"}.get(node.tag, node.tag)
    if tag in SEMANTIC_TAGS:
        if tag in {"br", "hr"}:
            return "<" + tag + ">"
        return "<" + tag + ">" + body.strip() + "</" + tag + ">" if body.strip() else ""
    return "\n" + body.strip() + "\n" if node.tag in BLOCK else body


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
            elif child.tag != "title":
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
