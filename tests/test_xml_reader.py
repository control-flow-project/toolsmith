from dataclasses import asdict, replace

import pytest

from toolsmith.readers import XmlElement, XmlLimits, read_json_lines, read_xml
from toolsmith.result import Failure, unwrap


def test_xml_preserves_expanded_names_attributes_order_and_mixed_text() -> None:
    document = unwrap(
        read_xml(
            b'<root xmlns="urn:default" xmlns:a="urn:extra" a:id="17">before'
            b'<a:item number="1">one &amp; two</a:item>between'
            b'<a:item number="2"/>after</root>'
        )
    )
    assert document.nodes == 3
    assert document.root == XmlElement(
        "{urn:default}root",
        {"{urn:extra}id": "17"},
        (
            "before",
            XmlElement("{urn:extra}item", {"number": "1"}, ("one & two",)),
            "between",
            XmlElement("{urn:extra}item", {"number": "2"}, ()),
            "after",
        ),
    )


def test_xml_does_not_apply_a_two_hundred_item_cutoff() -> None:
    entries = b"".join(f'<entry id="{number}"/>'.encode() for number in range(2500))
    document = unwrap(read_xml(b"<root>" + entries + b"</root>"))
    assert document.nodes == 2501
    assert len(document.root.content) == 2500
    final = document.root.content[-1]
    assert isinstance(final, XmlElement)
    assert asdict(final)["attributes"] == {"id": "2499"}


@pytest.mark.parametrize(
    "content",
    [
        b'<!DOCTYPE root SYSTEM "https://example.org/external"><root/>',
        b'<!DOCTYPE root [<!ENTITY secret SYSTEM "file:///etc/passwd">]><root>&secret;</root>',
        b'<!ENTITY body "content"><root/>',
    ],
)
def test_xml_rejects_dtd_and_entity_declarations(content: bytes) -> None:
    result = read_xml(content)
    assert isinstance(result, Failure) and result.code == "denied"


@pytest.mark.parametrize(
    "content", [b"", b"<root>", b"<root/><other/>", b'<root id="one" id="two"/>', b"\xff"]
)
def test_xml_rejects_malformed_or_non_utf8_input(content: bytes) -> None:
    assert isinstance(read_xml(content), Failure)


@pytest.mark.parametrize(
    ("content", "limits"),
    [
        (b"<root/>", replace(XmlLimits(), maximum_bytes=6)),
        (b"<root><child/></root>", replace(XmlLimits(), maximum_nodes=1)),
        (b"<root><child/></root>", replace(XmlLimits(), maximum_depth=1)),
        (b'<root one="1" two="2"/>', replace(XmlLimits(), maximum_attributes=1)),
        (b"<root/>", replace(XmlLimits(), maximum_name_characters=3)),
        (b'<root value="1234"/>', replace(XmlLimits(), maximum_attribute_bytes=3)),
        (b"<root>1234</root>", replace(XmlLimits(), maximum_text_bytes=3)),
        (b"<root><child/>1234</root>", replace(XmlLimits(), maximum_text_bytes=3)),
    ],
)
def test_xml_structural_budgets_fail_explicitly(content: bytes, limits: XmlLimits) -> None:
    result = read_xml(content, limits)
    assert isinstance(result, Failure) and result.code == "limit"


def test_json_lines_preserves_every_record_and_skips_only_blank_lines() -> None:
    document = b"\n".join(f'{{"number":{number}}}'.encode() for number in range(2500))
    records = unwrap(read_json_lines(b"\n" + document + b"\n\n"))
    assert len(records) == 2500
    assert records[-1] == {"number": 2499}
    assert unwrap(read_json_lines(b" \n\t")) == ()


def test_json_lines_rejects_a_bad_record_instead_of_dropping_it() -> None:
    assert isinstance(read_json_lines(b'{"valid":1}\n{"bad":}\n'), Failure)
    assert isinstance(read_json_lines(b"null\ntrue", maximum_bytes=3), Failure)
