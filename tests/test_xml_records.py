import xml.etree.ElementTree as ET
from dataclasses import replace
from unittest.mock import patch

import pytest

from toolsmith.readers import XmlElement, XmlLimits, read_xml, read_xml_records
from toolsmith.readers.xml import element_value
from toolsmith.result import Failure, unwrap


def value(element: XmlElement) -> str:
    return "".join(item for item in element.content if isinstance(item, str))


def test_records_preserve_scoped_namespaces_order_and_mixed_content() -> None:
    original = b'<root xmlns:p="urn:one"><row>one</row><skip/><row xmlns:p="urn:two">two<b/>after</row></root>'
    records = unwrap(read_xml_records(original, "row", lambda element: element))
    assert len(records) == 2
    assert records[0].namespaces["p"] == "urn:one"
    assert records[1].namespaces["p"] == "urn:two"
    assert value(records[1]) == "twoafter"
    tree = unwrap(read_xml(original)).root
    expected = tuple(
        item for item in tree.content if isinstance(item, XmlElement) and item.name == "row"
    )
    assert records == expected


def test_records_release_processed_nodes_and_namespace_bindings() -> None:
    sizes: list[int] = []

    def inspect(element: ET.Element, bindings: dict[int, dict[str, str]]) -> XmlElement:
        sizes.append(len(bindings))
        return element_value(element, bindings)

    original = b"<root>" + b"<row><v>one</v></row>" * 10000 + b"</root>"
    with patch("toolsmith.readers.xml.element_value", side_effect=inspect):
        records = unwrap(read_xml_records(original, "row", lambda element: len(element.content)))
    assert len(records) == 10000 and set(records) == {1}
    assert max(sizes) <= 3


@pytest.mark.parametrize("suffix", [b"<broken>", b"</other>", b"<tail/>junk"])
def test_malformed_tail_never_returns_partial_records(suffix: bytes) -> None:
    calls: list[str] = []
    original = b"<root><row>ready</row>" + b" " * 8192 + suffix
    result = read_xml_records(original, "row", lambda element: calls.append(value(element)))
    assert isinstance(result, Failure)
    assert calls == ["ready"]  # Conversion is pure local work, not a committed output.


def test_records_validate_unselected_content_and_tail_across_input_chunks() -> None:
    original = b"<root><row>ok</row>" + b"x" * 9000 + b"</root>"
    limits = replace(XmlLimits(), maximum_text_bytes=8192)
    for result in (read_xml_records(original, "row", value, limits), read_xml(original, limits)):
        assert isinstance(result, Failure) and result.code == "limit"
    result = read_xml_records(
        b'<root><skip bad="long"/><row>ok</row></root>',
        "row",
        value,
        replace(XmlLimits(), maximum_attribute_bytes=3),
    )
    assert isinstance(result, Failure) and result.code == "limit"


def test_explicit_larger_node_budget_and_default_bound_remain_distinct() -> None:
    assert XmlLimits().maximum_nodes == 2_000_000
    original = b"<root><row>one</row><row>two</row></root>"
    result = read_xml_records(original, "row", value, replace(XmlLimits(), maximum_nodes=2))
    assert isinstance(result, Failure) and result.code == "limit"
    assert unwrap(
        read_xml_records(original, "row", value, replace(XmlLimits(), maximum_nodes=8_000_000))
    ) == ("one", "two")


def test_converter_failure_nested_selection_and_dtd_fail_explicitly() -> None:
    def reject(_element: XmlElement) -> str:
        raise ValueError("invalid record")

    for original, converter in [
        (b"<root><row/></root>", reject),
        (b"<root><row><row/></row></root>", value),
        (b"<!DOCTYPE root><root><row/></root>", value),
    ]:
        assert isinstance(read_xml_records(original, "row", converter), Failure)


def test_selected_records_require_the_explicit_root_before_conversion() -> None:
    calls: list[str] = []
    result = read_xml_records(
        b"<other><row>value</row></other>",
        "row",
        lambda element: calls.append(value(element)),
        root_name="root",
    )
    assert isinstance(result, Failure) and calls == []
    assert unwrap(
        read_xml_records(b"<root><row>value</row></root>", "row", value, root_name="root")
    ) == ("value",)
