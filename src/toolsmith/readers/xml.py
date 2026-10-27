from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from toolsmith.readers.text import decode_text
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer


@dataclass(frozen=True)
class XmlLimits:
    maximum_bytes: int = 32 * 1024 * 1024
    maximum_nodes: int = 2_000_000
    maximum_depth: int = 64
    maximum_attributes: int = 256
    maximum_name_characters: int = 1000
    maximum_attribute_bytes: int = 128 * 1024
    maximum_text_bytes: int = 4 * 1024 * 1024


@dataclass(frozen=True)
class XmlElement:
    name: str
    attributes: dict[str, str]
    content: tuple[XmlElement | str, ...]
    namespaces: dict[str, str]


@dataclass(frozen=True)
class XmlDocument:
    root: XmlElement
    nodes: int


def validate_limits(limits: XmlLimits) -> XmlLimits:
    if not isinstance(limits, XmlLimits):
        raise ToolsmithError("invalid_input", "Supply explicit XML structural limits")
    integer(limits.maximum_bytes, 1, 128 * 1024 * 1024, "Maximum XML bytes")
    integer(limits.maximum_nodes, 1, 8_000_000, "Maximum XML nodes")
    integer(limits.maximum_depth, 1, 128, "Maximum XML depth")
    integer(limits.maximum_attributes, 1, 10_000, "Maximum XML attributes")
    integer(limits.maximum_name_characters, 1, 8192, "Maximum XML name characters")
    integer(limits.maximum_attribute_bytes, 1, 128 * 1024 * 1024, "Maximum XML attribute bytes")
    integer(limits.maximum_text_bytes, 1, 128 * 1024 * 1024, "Maximum XML text bytes")
    return limits


def parse_tree(
    content: bytes,
    limits: XmlLimits,
    selected_names: tuple[str, ...] = (),
    accept: Callable[[XmlElement], None] | None = None,
    expected_root: str | None = None,
) -> tuple[ET.Element, int, dict[int, dict[str, str]]]:
    checked = validate_limits(limits)
    decoded = decode_text(content, checked.maximum_bytes)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", decoded, re.I):
        raise ToolsmithError("denied", "XML DTDs and entity definitions are not permitted")
    parser: ET.XMLPullParser[ET.Element[str]] = ET.XMLPullParser(
        events=("start", "end", "start-ns")
    )
    root: ET.Element | None = None
    depth, nodes = 0, 0
    scopes: list[dict[str, str]] = [{"xml": "http://www.w3.org/XML/1998/namespace"}]
    stack: list[ET.Element] = []
    pending: dict[str, str] = {}
    bindings: dict[int, dict[str, str]] = {}
    selected_depth: int | None = None
    completed: tuple[ET.Element, ET.Element | None, bool] | None = None

    def finish_tail() -> None:
        nonlocal completed
        if completed is None:
            return
        node, parent, release = completed
        if len((node.tail or "").encode()) > checked.maximum_text_bytes:
            raise ToolsmithError("limit", "XML tail text exceeds its field budget")
        if release:
            for child in node.iter():
                bindings.pop(id(child), None)
            if parent is not None:
                parent.remove(node)
            node.clear()
        completed = None

    try:
        for offset in range(0, len(decoded), 4096):
            parser.feed(decoded[offset : offset + 4096])
            for event, element in cast(
                "list[tuple[str, ET.Element[str] | tuple[str, str]]]", list(parser.read_events())
            ):
                if event == "start-ns":
                    prefix, namespace = cast("tuple[str, str]", element)
                    if (
                        len(prefix) > checked.maximum_name_characters
                        or len(namespace.encode()) > checked.maximum_attribute_bytes
                    ):
                        raise ToolsmithError(
                            "limit", "XML namespace metadata exceeds its field budget"
                        )
                    pending[prefix] = namespace
                    if len(pending) > checked.maximum_attributes:
                        raise ToolsmithError("limit", "XML exceeds its namespace-count budget")
                    continue
                finish_tail()
                element = cast("ET.Element[str]", element)
                if event == "start":
                    scope = {**scopes[-1], **pending} if pending else scopes[-1]
                    if len(scope) > checked.maximum_attributes:
                        raise ToolsmithError("limit", "XML exceeds its in-scope namespace budget")
                    bindings[id(element)] = scope
                    scopes.append(scope)
                    stack.append(element)
                    if root is None:
                        if expected_root is not None and element.tag != expected_root:
                            raise ToolsmithError(
                                "invalid_input",
                                "XML root differs from the selected document contract",
                            )
                        root = element
                    depth += 1
                    nodes += 1
                    if depth > checked.maximum_depth or nodes > checked.maximum_nodes:
                        raise ToolsmithError("limit", "XML exceeds its node or depth budget")
                    if len(element.attrib) + len(pending) > checked.maximum_attributes:
                        raise ToolsmithError("limit", "XML exceeds its attribute-count budget")
                    if len(element.tag) > checked.maximum_name_characters or any(
                        len(key) > checked.maximum_name_characters
                        or len(value.encode()) > checked.maximum_attribute_bytes
                        for key, value in element.attrib.items()
                    ):
                        raise ToolsmithError("limit", "XML metadata exceeds its field budget")
                    if accept is not None and element.tag in selected_names:
                        if selected_depth is not None:
                            raise ToolsmithError(
                                "invalid_input", "Selected XML record elements cannot nest"
                            )
                        selected_depth = depth
                    pending = {}
                else:
                    if len((element.text or "").encode()) > checked.maximum_text_bytes:
                        raise ToolsmithError("limit", "XML text exceeds its field budget")
                    if accept is not None and depth == selected_depth:
                        accept(element_value(element, bindings))
                        selected_depth = None
                    scopes.pop()
                    stack.pop()
                    completed = (
                        element,
                        stack[-1] if stack else None,
                        accept is not None and selected_depth is None,
                    )
                    depth -= 1
        parser.close()
        finish_tail()
    except ET.ParseError as error:
        raise ToolsmithError("invalid_input", "XML is malformed") from error
    if root is None or depth:
        raise ToolsmithError("invalid_input", "XML has no complete root")
    return root, nodes, bindings


def element_value(element: ET.Element, bindings: dict[int, dict[str, str]]) -> XmlElement:
    content: list[XmlElement | str] = []
    if element.text:
        content.append(element.text)
    for child in element:
        content.append(element_value(child, bindings))
        if child.tail:
            content.append(child.tail)
    return XmlElement(element.tag, dict(element.attrib), tuple(content), bindings[id(element)])


@boundary
def read_xml(content: bytes, limits: XmlLimits | None = None) -> XmlDocument:
    root, nodes, bindings = parse_tree(content, XmlLimits() if limits is None else limits)
    return XmlDocument(element_value(root, bindings), nodes)


@boundary
def read_xml_records[Value](
    content: bytes,
    element_name: str | tuple[str, ...],
    convert: Callable[[XmlElement], Value],
    limits: XmlLimits | None = None,
    *,
    root_name: str | None = None,
) -> tuple[Value, ...]:
    """Transform non-nested selected elements without retaining the document tree.

    The converter must be pure: records are returned only after the entire XML
    document validates. No iterator exposes a partial-success prefix. The caller
    owns the compact record type and may persist only the successful result.
    """
    names = (element_name,) if isinstance(element_name, str) else element_name
    if (
        not isinstance(names, tuple)
        or not names
        or any(not isinstance(name, str) or not name or len(name) > 8192 for name in names)
        or len(names) != len(set(names))
        or not callable(convert)
    ):
        raise ToolsmithError("invalid_input", "Supply an exact XML element name and pure converter")
    if root_name is not None and (not isinstance(root_name, str) or not root_name):
        raise ToolsmithError("invalid_input", "XML root name must be a nonempty exact name")
    records: list[Value] = []

    def accept(element: XmlElement) -> None:
        try:
            records.append(convert(element))
        except (ValueError, TypeError) as error:
            raise ToolsmithError("invalid_input", "XML record conversion failed") from error

    parse_tree(content, XmlLimits() if limits is None else limits, names, accept, root_name)
    return tuple(records)
