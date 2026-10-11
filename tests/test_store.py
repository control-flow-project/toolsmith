from pathlib import Path

import pytest
from conftest import ControlledClock

from toolsmith.result import Failure, unwrap
from toolsmith.retrieval import read_citation, search_text
from toolsmith.storage.database import initialize_store, inspect_store, open_store
from toolsmith.storage.models import Document, TextPart
from toolsmith.storage.operations import operation_status
from toolsmith.storage.text import inspect_text, list_text, put_text


def test_initialization_is_repeatable_and_scope_bound(store: Path) -> None:
    assert unwrap(initialize_store(store, "sample")).items == 0
    wrong = initialize_store(store, "other")
    assert isinstance(wrong, Failure) and wrong.code == "denied"
    assert isinstance(inspect_store(store, "other"), Failure)


def test_initialization_rejects_nonempty_and_can_finish_unpublished_state(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir(mode=0o700)
    (bad / "unknown").write_bytes(b"keep")
    assert isinstance(initialize_store(bad, "sample"), Failure)
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir(mode=0o700)
    (incomplete / "objects").mkdir(mode=0o700)
    (incomplete / "tmp").mkdir(mode=0o700)
    (incomplete / "tmp" / (".stage-" + "a" * 32 + ".tmp")).write_bytes(b"unpublished")
    assert unwrap(initialize_store(incomplete, "sample")).schema_version == 1


def test_immutable_versions_idempotency_and_current_search(
    store: Path, clock: ControlledClock
) -> None:
    first = Document(
        "First",
        (
            TextPart(
                "Physical page one",
                "Original unique words",
                1,
                ("Supplied extraction, not verified",),
            ),
        ),
    )
    old = unwrap(put_text(store, "sample", "report", first, "one", clock=clock))
    clock.advance(1)
    new = unwrap(
        put_text(
            store,
            "sample",
            "report",
            Document("Second", (TextPart("Page", "Replacement different text", 1),)),
            "two",
            clock=clock,
        )
    )
    repeated = unwrap(put_text(store, "sample", "report", first, "one", clock=clock))
    assert repeated.version == old.version and repeated.reused
    assert unwrap(list_text(store, "sample"))[0].version == new.version
    assert len(unwrap(list_text(store, "sample", item="report"))) == 2
    assert not unwrap(search_text(store, "sample", "unique"))
    citation = unwrap(read_citation(store, "sample", old.version, 1, 9, 6))
    assert citation.text == "unique"
    assert citation.start == 9 and citation.end == 15 and citation.physical_page == 1
    assert citation.warnings == ("Supplied extraction, not verified",)
    assert unwrap(operation_status(store, "sample", "one")).status == "succeeded"
    assert isinstance(put_text(store, "sample", "different", first, "one"), Failure)


def test_chunks_return_exact_unicode_spans(store: Path) -> None:
    supplied = "αβ " * 400 + "needle " + "Ω " * 900
    reference = unwrap(
        put_text(
            store, "sample", "large", Document("Unicode", (TextPart("Part", supplied),)), "large"
        )
    )
    hits = unwrap(search_text(store, "sample", "needle"))
    assert hits
    for hit in hits:
        citation = unwrap(
            read_citation(
                store, "sample", reference.version, hit.part, hit.start, hit.end - hit.start
            )
        )
        assert hit.text == supplied[hit.start : hit.end] == citation.text


def test_query_operators_are_literal_not_controls(store: Path) -> None:
    unwrap(
        put_text(
            store,
            "sample",
            "item",
            Document("Words", (TextPart("Part", "alpha OR beta literal"),)),
            "one",
        )
    )
    assert unwrap(search_text(store, "sample", "alpha OR beta"))
    assert not unwrap(search_text(store, "sample", "alpha NOT beta"))
    assert isinstance(search_text(store, "sample", "*"), Failure)


def test_wrong_scope_is_rejected_on_all_reads(store: Path) -> None:
    reference = unwrap(
        put_text(
            store, "sample", "report", Document("Title", (TextPart("Part", "words"),)), "request"
        )
    )
    results = [
        inspect_text(store, "other", reference.version),
        list_text(store, "other"),
        search_text(store, "other", "words"),
        read_citation(store, "other", reference.version, 1),
        operation_status(store, "other", "request"),
    ]
    assert all(isinstance(result, Failure) and result.code == "denied" for result in results)


def test_failed_transaction_has_no_partial_version(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import toolsmith.storage.text as implementation

    def fail_after_insert(*_arguments: object, **_keywords: object) -> None:
        raise RuntimeError("injected programmer failure")

    monkeypatch.setattr(implementation, "text_reference", fail_after_insert)
    with pytest.raises(RuntimeError, match="injected"):
        put_text(store, "sample", "one", Document("Test", (TextPart("Part", "words"),)), "request")
    assert unwrap(inspect_store(store, "sample")).items == 0
    assert isinstance(operation_status(store, "sample", "request"), Failure)


def test_current_schema_only_and_cooperating_lock(store: Path) -> None:
    with open_store(store, "sample", write=True) as selected:
        locked = inspect_store(store, "sample")
        assert isinstance(locked, Failure) and locked.code == "deferred"
        selected.connection.execute("PRAGMA user_version = 9")
    result = inspect_store(store, "sample")
    assert isinstance(result, Failure) and result.code == "integrity"
