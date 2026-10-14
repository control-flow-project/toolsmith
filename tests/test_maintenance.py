import os
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import ControlledClock

from toolsmith.files import PrivateDirectory, new_private
from toolsmith.operations.backup import backup_store, restore_store
from toolsmith.operations.cleanup import apply_cleanup, preview_cleanup
from toolsmith.operations.integrity import check_integrity, rebuild_index
from toolsmith.readers.models import Document, TextPart
from toolsmith.result import Failure, unwrap
from toolsmith.retrieval import search_text
from toolsmith.storage.artifacts import put_file, read_file
from toolsmith.storage.database import open_store
from toolsmith.storage.text import put_text


def test_backup_restore_is_verified_and_never_overwrites(store: Path, tmp_path: Path) -> None:
    unwrap(
        put_text(
            store,
            "sample",
            "item",
            Document("Report", (TextPart("Part", "retained words"),)),
            "text",
        )
    )
    file = unwrap(
        put_file(store, "sample", b"retained original", "report.txt", "text/plain", "file")
    )
    backup = tmp_path / "backup"
    report = unwrap(backup_store(store, "sample", backup))
    assert report.verified and report.objects == 1
    destination = tmp_path / "restored"
    assert unwrap(restore_store(backup, "sample", destination)).verified
    assert unwrap(read_file(destination, "sample", file.version)) == b"retained original"
    assert unwrap(search_text(destination, "sample", "retained"))
    assert unwrap(check_integrity(destination, "sample")).valid
    assert isinstance(restore_store(backup, "sample", destination), Failure)
    assert isinstance(backup_store(store, "sample", backup), Failure)
    assert isinstance(restore_store(backup, "other", tmp_path / "wrong"), Failure)
    assert not (tmp_path / "wrong").exists()


def test_corrupt_backup_and_byte_limits_fail_before_destination(
    store: Path, tmp_path: Path
) -> None:
    reference = unwrap(put_file(store, "sample", b"original", "file", "text/plain", "file"))
    backup = tmp_path / "backup"
    assert isinstance(backup_store(store, "sample", backup, 1), Failure)
    assert not backup.exists()
    unwrap(backup_store(store, "sample", backup))
    (backup / "objects" / reference.content_sha256).write_bytes(b"modified")
    destination = tmp_path / "restored"
    assert isinstance(restore_store(backup, "sample", destination), Failure)
    assert not destination.exists()


def test_interrupted_restore_never_publishes_metadata_before_objects(
    store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import toolsmith.operations.backup as implementation
    from toolsmith.result import ToolsmithError
    from toolsmith.storage.database import inspect_store

    unwrap(put_file(store, "sample", b"original", "file", "text/plain", "file"))
    backup = tmp_path / "backup"
    unwrap(backup_store(store, "sample", backup))
    original_write = new_private

    def failing_object(directory: PrivateDirectory, name: str, content: bytes) -> None:
        if len(name) == 64:
            raise ToolsmithError("io", "injected object write failure")
        original_write(directory, name, content)

    monkeypatch.setattr(implementation, "new_private", failing_object)
    destination = tmp_path / "partial"
    assert isinstance(restore_store(backup, "sample", destination), Failure)
    assert not (destination / "toolsmith.sqlite3").exists()
    assert isinstance(inspect_store(destination, "sample"), Failure)


@pytest.mark.parametrize("damage", ["postings", "missing_chunks", "forged_chunks"])
def test_index_rebuild_uses_retained_canonical_text(store: Path, damage: str) -> None:
    unwrap(
        put_text(
            store,
            "sample",
            "item",
            Document("Title", (TextPart("Part", "searchable words"),)),
            "text",
        )
    )
    with open_store(store, "sample", write=True) as selected, selected.connection:
        selected.connection.execute("DELETE FROM lexical_search")
        if damage == "missing_chunks":
            selected.connection.execute("DELETE FROM lexical_chunk")
        elif damage == "forged_chunks":
            selected.connection.execute("UPDATE lexical_chunk SET text = 'forged'")
    assert not unwrap(search_text(store, "sample", "words"))
    assert isinstance(check_integrity(store, "sample"), Failure)
    assert unwrap(rebuild_index(store, "sample")).valid
    assert unwrap(search_text(store, "sample", "words"))


def test_corrupt_provenance_prevents_rebuild_mutation(store: Path) -> None:
    unwrap(
        put_text(
            store,
            "sample",
            "item",
            Document("Title", (TextPart("Part", "retained words"),)),
            "text",
        )
    )
    with open_store(store, "sample", write=True) as selected, selected.connection:
        selected.connection.execute("UPDATE text_version SET title = 'forged'")
        original = selected.connection.execute("SELECT title FROM lexical_search").fetchone()[0]
    assert isinstance(check_integrity(store, "sample"), Failure)
    assert isinstance(rebuild_index(store, "sample"), Failure)
    with open_store(store, "sample") as selected:
        assert (
            selected.connection.execute("SELECT title FROM lexical_search").fetchone()[0]
            == original
        )


def test_cleanup_targets_only_previewed_inactive_owned_files(
    store: Path, clock: ControlledClock
) -> None:
    temporary = store / "tmp"
    target = temporary / (".stage-" + "a" * 32 + ".tmp")
    target.write_bytes(b"temporary")
    target.chmod(0o600)
    os.utime(target, (clock.wall() - 100, clock.wall() - 100))
    unknown = temporary / "unknown"
    unknown.write_bytes(b"keep")
    linked = temporary / (".stage-" + "b" * 32 + ".tmp")
    linked.symlink_to(unknown)
    fresh = temporary / (".stage-" + "c" * 32 + ".tmp")
    fresh.write_bytes(b"fresh")
    fresh.chmod(0o600)
    os.utime(fresh, (clock.wall(), clock.wall()))
    plan = unwrap(preview_cleanup(store, "sample", 50, clock=clock))
    assert [entry.name for entry in plan.files] == [target.name]
    target.write_bytes(b"changed")
    assert isinstance(apply_cleanup(store, "sample", plan), Failure)
    assert target.exists() and unknown.exists() and linked.is_symlink() and fresh.exists()
    os.utime(target, (clock.wall() - 100, clock.wall() - 100))
    current = unwrap(preview_cleanup(store, "sample", 50, clock=clock))
    assert isinstance(apply_cleanup(store, "other", current), Failure)
    assert isinstance(apply_cleanup(store, "sample", replace(current, collection="other")), Failure)
    assert unwrap(apply_cleanup(store, "sample", current))["deleted"] == 1
    assert not target.exists() and unknown.exists() and linked.is_symlink() and fresh.exists()


def test_cleanup_plan_is_bound_to_the_selected_root(
    store: Path, tmp_path: Path, clock: ControlledClock
) -> None:
    from toolsmith.storage.database import initialize_store

    plan = unwrap(preview_cleanup(store, "sample", clock=clock))
    other = tmp_path / "other-store"
    unwrap(initialize_store(other, "sample"))
    result = apply_cleanup(other, "sample", plan)
    assert isinstance(result, Failure) and result.code == "denied"
