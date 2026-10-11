from pathlib import Path

import pytest

from toolsmith.files import component
from toolsmith.result import Failure
from toolsmith.storage.models import Document, TextPart, document_from_json
from toolsmith.storage.text import put_text
from toolsmith.validation import parse_json


@pytest.mark.parametrize(
    "content",
    [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b"[]junk", b'"\xff"', b'"\\ud800"'],
)
def test_json_rejects_noncanonical_input(content: bytes) -> None:
    from toolsmith.result import ToolsmithError

    with pytest.raises(ToolsmithError):
        value = parse_json(content)
        from toolsmith.validation import canonical_json

        canonical_json(value)


def test_public_store_boundaries_do_not_accept_invalid_documents(store: Path) -> None:
    assert isinstance(
        put_text(store, "sample", "item", Document("Test", (TextPart("Part", "\ud800"),)), "bad"),
        Failure,
    )
    assert isinstance(
        put_text(
            store, "sample", "../escape", Document("Test", (TextPart("Part", "valid"),)), "bad"
        ),
        Failure,
    )


@pytest.mark.parametrize("name", ["", ".", "..", "../escape", "objects/data", "bad\x00name"])
def test_internal_file_components_cannot_escape(name: str) -> None:
    from toolsmith.result import ToolsmithError

    with pytest.raises(ToolsmithError):
        component(name)


def test_document_shape_rejects_unknown_fields() -> None:
    from toolsmith.result import ToolsmithError

    with pytest.raises(ToolsmithError):
        document_from_json(
            {
                "title": "Title",
                "parts": [{"label": "Part", "text": "valid", "hidden": "not allowed"}],
            }
        )


def test_enormous_numeric_input_is_an_expected_validation_failure() -> None:
    from toolsmith.result import ToolsmithError
    from toolsmith.validation import number

    with pytest.raises(ToolsmithError):
        number(10**1000, 0, 60, "Deadline")
