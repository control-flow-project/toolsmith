from dataclasses import dataclass, field
from html.parser import HTMLParser

from toolsmith.readers.text import decode_text
from toolsmith.result import ToolsmithError, boundary
from toolsmith.storage.models import Document, TextPart
from toolsmith.validation import text

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
}
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
    "tr",
    "blockquote",
    "pre",
    "br",
    "hr",
}


@dataclass
class Node:
    tag: str
    omitted: bool
    children: list["Node | str"] = field(default_factory=list)


class MeaningfulParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", False)
        self.stack = [self.root]
        self.candidates: list[Node] = []
        self.title: list[str] = []
        self.nodes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > 50_000 or len(self.stack) > 128 or len(attrs) > 100:
            raise ToolsmithError(
                "limit", "HTML structure exceeds its node, attribute or nesting limit"
            )
        attributes = dict(attrs)
        style = (attributes.get("style") or "").replace(" ", "").lower()
        omitted = (
            self.stack[-1].omitted
            or tag in OMIT
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        node = Node(tag, omitted)
        self.stack[-1].children.append(node)
        if tag in {"main", "article"} and not omitted:
            self.candidates.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.stack[-1].tag == "title":
            self.title.append(data)
        elif not self.stack[-1].omitted:
            self.stack[-1].children.append(data)


def flatten(node: Node) -> str:
    if node.omitted or node.tag in {"head", "title"}:
        return ""
    content = "".join(
        flatten(child) if isinstance(child, Node) else child for child in node.children
    )
    return "\n" + content + "\n" if node.tag in BLOCK else content


@boundary
def read_html(content: bytes, title: str | None = None) -> Document:
    parser = MeaningfulParser()
    parser.feed(decode_text(content))
    parser.close()
    candidates = parser.candidates or [parser.root]
    selected = max((flatten(node) for node in candidates), key=len)
    meaningful = "\n".join(" ".join(line.split()) for line in selected.splitlines() if line.strip())
    if not meaningful:
        raise ToolsmithError("not_found", "HTML contains no meaningful static text")
    actual_title = text(
        title if title is not None else " ".join(" ".join(parser.title).split()) or "Untitled HTML",
        1024,
        "Title",
    )
    warnings = (
        "Static HTML extraction is not a browser; completeness and hidden/dynamic content are unverified.",
    )
    return Document(
        actual_title,
        (TextPart("Meaningful HTML text", meaningful, warnings=warnings),),
        "static-html",
    )
