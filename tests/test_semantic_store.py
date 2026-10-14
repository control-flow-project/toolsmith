from pathlib import Path
from unittest.mock import patch

import pytest
from semantic_support import FixtureEncoder

from toolsmith.cli import main
from toolsmith.operations.backup import backup_store, restore_store
from toolsmith.operations.integrity import check_integrity
from toolsmith.readers.models import Document, TextPart
from toolsmith.result import Failure, Success, unwrap
from toolsmith.retrieval import read_citation
from toolsmith.semantic.store import (
    clear_text_index,
    index_text,
    inspect_text_index,
    search_semantic_text,
)
from toolsmith.storage.database import open_store
from toolsmith.storage.text import put_text


def add(root: Path, item: str, body: str, request: str) -> str:
    return unwrap(
        put_text(
            root, "sample", item, Document("Source", (TextPart("Physical page", body, 7),)), request
        )
    ).version


def test_index_batches_and_scope_with_exact_unicode_page_citations(store: Path) -> None:
    version = add(store, "weather", "évidence — rain on wet roads", "weather")
    add(store, "bank", "bank deposits and lending", "bank")
    encoder = FixtureEncoder()
    assert (
        unwrap(index_text(store, "sample", Path("/unused"), 1, encoder=encoder)).status.pending == 1
    )
    assert (
        unwrap(index_text(store, "sample", Path("/unused"), 1, encoder=encoder)).status.pending == 0
    )
    with patch("toolsmith.semantic.store.load_model") as loader:
        assert unwrap(index_text(store, "sample", Path("/absent"))).newly_indexed == 0
        loader.assert_not_called()
    result = unwrap(search_semantic_text(store, "sample", "wet", Path("/unused"), encoder=encoder))
    hit = result.hits[0]
    assert hit.citation.item == "weather" and hit.citation.version == version
    assert hit.citation.physical_page == 7
    assert hit.citation.text == "évidence — rain on wet roads"
    assert unwrap(read_citation(store, "sample", version, 1)).text == hit.citation.text
    restricted = unwrap(
        search_semantic_text(store, "sample", "wet", Path("/unused"), encoder=encoder, item="bank")
    )
    assert [hit.citation.item for hit in restricted.hits] == ["bank"]
    assert isinstance(index_text(store, "other", Path("/unused"), encoder=encoder), Failure)
    assert isinstance(
        search_semantic_text(store, "other", "wet", Path("/unused"), encoder=encoder), Failure
    )


def test_import_invalidates_only_changed_current_vectors_but_keeps_exact_old_citations(
    store: Path,
) -> None:
    old = add(store, "document", "original source words", "old")
    encoder = FixtureEncoder()
    unwrap(index_text(store, "sample", Path("/unused"), encoder=encoder))
    add(store, "document", "original source words", "same")
    assert unwrap(inspect_text_index(store, "sample")).indexed == 1
    current = add(store, "document", "corrected rain and wet roads", "new")
    assert unwrap(inspect_text_index(store, "sample")).indexed == 0
    assert unwrap(read_citation(store, "sample", old, 1)).text == "original source words"
    missing = unwrap(search_semantic_text(store, "sample", "wet", Path("/unused"), encoder=encoder))
    assert missing.missing == 1 and missing.hits == ()
    unwrap(index_text(store, "sample", Path("/unused"), encoder=encoder))
    assert (
        unwrap(search_semantic_text(store, "sample", "wet", Path("/unused"), encoder=encoder))
        .hits[0]
        .citation.version
        == current
    )
    with open_store(store, "sample") as selected:
        assert (
            selected.connection.execute("SELECT COUNT(*) FROM embedding_document").fetchone()[0]
            == 1
        )
    assert unwrap(check_integrity(store, "sample")).valid


@pytest.mark.parametrize("reference", ["part:01", "part:" + "9" * 40, "part:9223372036854775808"])
def test_corrupt_store_references_fail_integrity_with_bounded_errors(
    store: Path, reference: str
) -> None:
    add(store, "document", "source words", "source")
    unwrap(index_text(store, "sample", Path("/unused"), encoder=FixtureEncoder()))
    with open_store(store, "sample", write=True) as selected, selected.connection:
        selected.connection.execute("UPDATE embedding_document SET reference = ?", (reference,))
    result = check_integrity(store, "sample")
    assert isinstance(result, Failure) and result.code == "integrity"


def test_encoding_holds_no_store_transaction_or_lock_and_rechecks_current_input(
    store: Path,
) -> None:
    add(store, "document", "original source", "original")

    def correct() -> None:
        add(store, "document", "replacement source", "replacement")

    encoder = FixtureEncoder(correct)
    failed = index_text(store, "sample", Path("/unused"), encoder=encoder)
    assert isinstance(failed, Failure) and failed.code == "conflict"
    assert unwrap(inspect_text_index(store, "sample")).indexed == 0
    assert unwrap(index_text(store, "sample", Path("/unused"), encoder=encoder)).status.pending == 0


def test_backup_restore_and_derived_only_clear(store: Path, tmp_path: Path) -> None:
    version = add(store, "agreement", "loan agreement protects lenders", "agreement")
    encoder = FixtureEncoder()
    unwrap(index_text(store, "sample", Path("/unused"), encoder=encoder))
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    unwrap(backup_store(store, "sample", backup))
    unwrap(restore_store(backup, "sample", restored))
    assert unwrap(inspect_text_index(restored, "sample")).indexed == 1
    assert unwrap(
        search_semantic_text(restored, "sample", "lender", Path("/unused"), encoder=encoder)
    ).hits
    assert unwrap(clear_text_index(restored, "sample")) == 1
    assert (
        unwrap(read_citation(restored, "sample", version, 1)).text
        == "loan agreement protects lenders"
    )
    assert unwrap(check_integrity(restored, "sample")).valid
    assert (
        unwrap(index_text(restored, "sample", Path("/unused"), encoder=encoder)).status.pending == 0
    )


def test_corrupt_vectors_block_integrity_and_backup_and_explicit_clear_allows_rebuild(
    store: Path, tmp_path: Path
) -> None:
    add(store, "document", "original source", "original")
    unwrap(index_text(store, "sample", Path("/unused"), encoder=FixtureEncoder()))
    with open_store(store, "sample", write=True) as selected, selected.connection:
        selected.connection.execute("UPDATE embedding_chunk SET vector = zeroblob(1536)")
    assert isinstance(check_integrity(store, "sample"), Failure)
    assert isinstance(backup_store(store, "sample", tmp_path / "bad-backup"), Failure)
    assert not (tmp_path / "bad-backup").exists()
    unwrap(clear_text_index(store, "sample"))
    unwrap(index_text(store, "sample", Path("/unused"), encoder=FixtureEncoder()))
    assert unwrap(check_integrity(store, "sample")).valid


def test_cli_uses_same_library_for_search_status_clear(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    add(store, "document", "rain and wet roads", "original")
    arguments = ["--json", "--root", str(store), "--collection", "sample", "semantic"]
    with patch("toolsmith.semantic.store.load_model", return_value=Success(FixtureEncoder())):
        assert main([*arguments, "index", "--model-directory", "/unused"]) == 0
        assert json.loads(capsys.readouterr().out)["result"]["status"]["pending"] == 0
        assert main([*arguments, "search", "wet", "--model-directory", "/unused"]) == 0
        assert (
            json.loads(capsys.readouterr().out)["result"]["hits"][0]["citation"]["item"]
            == "document"
        )
    assert main([*arguments, "status"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["indexed"] == 1
    assert main([*arguments, "clear"]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == 1


def test_query_encoding_rechecks_the_complete_current_candidate_selection(store: Path) -> None:
    add(store, "document", "original source", "original")
    unwrap(index_text(store, "sample", Path("/unused"), encoder=FixtureEncoder()))

    def change() -> None:
        add(store, "document", "replacement source", "replacement")

    result = search_semantic_text(
        store, "sample", "source", Path("/unused"), encoder=FixtureEncoder(change)
    )
    assert isinstance(result, Failure) and result.code == "conflict"


def test_metadata_only_changes_rebind_exact_vectors_without_reencoding(store: Path) -> None:
    add(store, "document", "identical source text", "original-metadata")
    encoder = FixtureEncoder()
    unwrap(index_text(store, "sample", Path("/unused"), encoder=encoder))
    calls = encoder.calls
    document = Document("Corrected title", (TextPart("Page", "identical source text", 11),))
    current = unwrap(put_text(store, "sample", "document", document, "metadata-correction"))
    assert unwrap(index_text(store, "sample", Path("/unused"), encoder=encoder)).newly_indexed == 0
    assert encoder.calls == calls
    result = unwrap(
        search_semantic_text(store, "sample", "source", Path("/unused"), encoder=encoder)
    )
    assert result.hits[0].citation.version == current.version
    assert result.hits[0].citation.title == "Corrected title"
    assert result.hits[0].citation.physical_page == 11
    assert unwrap(check_integrity(store, "sample")).valid


def test_blank_unicode_whitespace_pages_remain_citable_but_are_not_index_candidates(
    store: Path,
) -> None:
    document = Document(
        "Agreement",
        (
            TextPart("Blank page", "\n\t\u00a0\u2003", 1),
            TextPart("Content", "lender payment rights", 2),
        ),
    )
    reference = unwrap(put_text(store, "sample", "agreement", document, "blank-page"))
    assert (
        unwrap(index_text(store, "sample", Path("/unused"), encoder=FixtureEncoder())).status.parts
        == 1
    )
    assert unwrap(inspect_text_index(store, "sample")).pending == 0
    assert (
        unwrap(read_citation(store, "sample", reference.version, 1)).text == document.parts[0].text
    )
    assert unwrap(check_integrity(store, "sample")).valid
