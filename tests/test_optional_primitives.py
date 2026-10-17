import hashlib
import os
from pathlib import Path
from unittest.mock import patch

from conftest import ControlledClock
from semantic_support import index_database, publish

from toolsmith.files import FileStamp, copy_file, file_stamp, replace_bytes
from toolsmith.filesystem import inventory, publish_directory, sync_directory_tree
from toolsmith.journal import MAX_JOURNAL_BYTES, append_record, read_journal, record_bytes
from toolsmith.lexical import Region, find_text
from toolsmith.result import Failure, unwrap
from toolsmith.semantic import Source, clear_index, inspect_index, relocate_embedding
from toolsmith.validation import JsonValue


def test_journal_reads_and_appends_past_the_removed_100000_record_ceiling(
    tmp_path: Path, clock: ControlledClock
) -> None:
    root = tmp_path / "large-journal"
    root.mkdir(mode=0o700)
    path = root / "journal.jsonl"
    path.touch(mode=0o600)
    previous = "0" * 64
    with path.open("wb") as stream:
        for sequence in range(1, 100_001):
            value: dict[str, JsonValue] = {
                "sequence": sequence,
                "at": "2026-10-17T00:00:00+00:00",
                "previous": previous,
                "event": None,
            }
            previous = hashlib.sha256(record_bytes(value)).hexdigest()
            value["sha256"] = previous
            stream.write(record_bytes(value) + b"\n")
    assert path.stat().st_size < MAX_JOURNAL_BYTES
    appended = unwrap(append_record(root, {"next": True}, clock=clock))
    assert appended.sequence == 100_001
    records = unwrap(read_journal(root))
    assert len(records) == 100_001 and records[-1] == appended


def test_literal_search_preserves_punctuation_regions_counts_and_offsets() -> None:
    body = "Rate is 1.25%.\fRATE IS 1.25%."
    split = body.index("\f")
    result = unwrap(
        find_text(body, "1.25%", 1, regions=(Region(0, split), Region(split + 1, len(body))))
    )
    assert result.total == 2 and result.truncated and len(result.matches) == 1
    assert result.matches[0].text == "Rate is 1.25%."
    assert result.matches[0].match_start == 8
    assert unwrap(find_text(body, "1x25%")).total == 0
    assert unwrap(find_text(body, "RATE", case_sensitive=True)).total == 1


def test_literal_search_accepts_all_regions_in_a_byte_bounded_source() -> None:
    body = "ordinary " * 10_001 + "target"
    regions = tuple(Region(number * 9, (number + 1) * 9) for number in range(10_001))
    selected = (*regions, Region(90_009, len(body)))
    result = unwrap(find_text(body, "target", 1, regions=selected))
    assert result.total == 1 and result.matches[0].region == 10_001


def test_private_tree_and_atomic_publication_are_generic(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    (root / "nested").mkdir(mode=0o700)
    unwrap(replace_bytes(root / "state.json", b"state"))
    unwrap(replace_bytes(root / "nested/data", b"data"))
    entries = unwrap(inventory(root))
    assert {entry.name for entry in entries} == {
        "nested/data",
        "state.json",
    }
    assert unwrap(sync_directory_tree(root)) == 2
    destination = tmp_path / "published"
    assert unwrap(publish_directory(root, destination))
    assert (destination / "nested/data").read_bytes() == b"data"
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    assert isinstance(publish_directory(other, destination), Failure)
    assert other.exists() and (destination / "state.json").read_bytes() == b"state"


def test_tree_rejects_symlinks_special_files_and_unbounded_directory_count(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    (root / "link").symlink_to(tmp_path / "missing")
    assert isinstance(inventory(root), Failure)
    (root / "link").unlink()
    for name in ("a", "b"):
        (root / name).mkdir(mode=0o700)
    assert isinstance(inventory(root, maximum_records=1), Failure)


def test_inventory_snapshot_does_not_copy_changed_sources(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"original")
    expected = unwrap(file_stamp(source))
    source.write_bytes(b"changed")
    assert isinstance(copy_file(source, tmp_path / "copy", 100, expected_stamp=expected), Failure)
    assert not (tmp_path / "copy").exists()
    assert isinstance(
        copy_file(source, tmp_path / "copy", 100, expected_stamp=FileStamp(0, 0, 0, 0, 0)), Failure
    )


def test_generic_journal_preserves_hash_chain_and_has_no_domain_schema(tmp_path: Path) -> None:
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    first = unwrap(append_record(root, {"caller_kind": "not-a-financial-schema", "text": "β"}))
    second = unwrap(append_record(root, {"anything": [1, 2]}))
    assert second.sequence == 2 and second.previous == first.sha256
    assert unwrap(read_journal(root)) == (first, second)
    with (root / "journal.jsonl").open("ab") as stream:
        stream.write(b"partial")
    assert isinstance(read_journal(root), Failure)
    before = (root / "journal.jsonl").read_bytes()
    assert isinstance(append_record(root, {"new": "event"}), Failure)
    assert (root / "journal.jsonl").read_bytes() == before


def test_failed_journal_write_restores_only_its_own_partial_append(tmp_path: Path) -> None:
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    unwrap(append_record(root, {"first": 1}))
    before = (root / "journal.jsonl").read_bytes()
    write = os.write
    calls = 0

    def failing(descriptor: int, content: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return write(descriptor, content[:3])
        raise OSError("Controlled write failure")

    with patch("toolsmith.files.os.write", side_effect=failing):
        assert isinstance(append_record(root, {"second": 2}), Failure)
    assert (root / "journal.jsonl").read_bytes() == before
    assert len(unwrap(read_journal(root))) == 1


def test_reference_relocation_reuses_vectors_and_clear_leaves_application_data() -> None:
    with index_database() as connection:
        source = Source("original", "Rain and wet weather")
        publish(connection, source)
        metadata = unwrap(inspect_index(connection, (source.reference,)))[0]
        assert metadata.digest is not None
        assert unwrap(
            relocate_embedding(
                connection,
                source.reference,
                Source("new", source.text),
                expected_digest=metadata.digest,
            )
        )
        states = unwrap(inspect_index(connection, ("original", "new")))
        assert states[0].digest is None and states[1].digest == metadata.digest
        connection.execute("CREATE TABLE application_state (id INTEGER)")
        connection.execute("INSERT INTO application_state VALUES (7)")
        connection.commit()
        assert unwrap(clear_index(connection)) == 1
        assert connection.execute("SELECT id FROM application_state").fetchone()[0] == 7


def test_journal_filename_replacement_never_reports_delivery_to_new_file(tmp_path: Path) -> None:
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    unwrap(append_record(root, {"first": 1}))
    original_write = os.write
    changed = False

    def replace_name(descriptor: int, content: bytes) -> int:
        nonlocal changed
        if not changed:
            changed = True
            (root / "journal.jsonl").rename(root / "old.jsonl")
            (root / "journal.jsonl").write_bytes(b"")
            (root / "journal.jsonl").chmod(0o600)
        return original_write(descriptor, content)

    with patch("toolsmith.files.os.write", side_effect=replace_name):
        result = append_record(root, {"second": 2})
    assert isinstance(result, Failure) and result.code == "conflict"
    assert (root / "journal.jsonl").read_bytes() == b""
