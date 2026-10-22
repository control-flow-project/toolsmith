import hashlib
import os
from pathlib import Path
from unittest.mock import patch

from semantic_support import FixtureEncoder, index_database

from toolsmith.operations.backup import MAX_BACKUP_BYTES, backup_store, restore_store
from toolsmith.operations.integrity import check_integrity
from toolsmith.result import Failure, unwrap
from toolsmith.scopes import Scope
from toolsmith.semantic import encode_query, fingerprint, search_embeddings
from toolsmith.semantic.profile import PROFILE_ID, PROFILE_JSON, pack_vector
from toolsmith.storage.database import open_store


def test_more_than_100000_chunks_are_searched_without_truncation() -> None:
    chunks_per_entry = 16_668
    body = "x" * chunks_per_entry
    with index_database() as connection:
        connection.execute("INSERT INTO embedding_profile VALUES (?,?)", (PROFILE_ID, PROFILE_JSON))
        vector = pack_vector(tuple(float(axis == 1) for axis in range(384)))
        target = pack_vector(tuple(float(axis == 0) for axis in range(384)))
        with connection:
            connection.executemany(
                "INSERT INTO embedding_document VALUES (?,?,?,?,?,?)",
                (
                    (
                        f"entry:{number}",
                        PROFILE_ID,
                        fingerprint(body),
                        len(body),
                        chunks_per_entry,
                        "2026-10-17T00:00:00Z",
                    )
                    for number in range(6)
                ),
            )
            connection.executemany(
                "INSERT INTO embedding_chunk (reference,ordinal,start_offset,end_offset,text_digest) VALUES (?,?,?,?,?)",
                (
                    (f"entry:{number}", ordinal, ordinal, ordinal + 1, fingerprint("x"))
                    for number in range(6)
                    for ordinal in range(chunks_per_entry)
                ),
            )
            connection.execute(
                "INSERT INTO embedding_vector(rowid,vector,chunk_id) SELECT id, CASE WHEN reference='entry:5' THEN ? ELSE ? END, id FROM embedding_chunk",
                (target, vector),
            )
        report = unwrap(
            search_embeddings(
                connection,
                unwrap(encode_query("wet", FixtureEncoder())),
                Scope("embedding_document"),
                1,
            )
        )
        assert report.indexed == 6 and report.hits[0].reference == "entry:5"
        assert connection.execute("SELECT count(*) FROM embedding_chunk").fetchone()[0] > 100_000


def test_database_over_128_mib_round_trips_without_whole_database_memory_copy(
    store: Path, tmp_path: Path
) -> None:
    with open_store(store, "sample", write=True) as selected, selected.connection:
        selected.connection.execute("CREATE TABLE capacity_payload (content BLOB)")
        selected.connection.execute("INSERT INTO capacity_payload VALUES (zeroblob(134221824))")
        selected.connection.execute("DROP TABLE capacity_payload")
    assert (store / "toolsmith.sqlite3").stat().st_size > 128 * 1024**2
    read = os.read
    largest = 0

    def bounded_read(descriptor: int, count: int) -> bytes:
        nonlocal largest
        largest = max(largest, count)
        return read(descriptor, count)

    with patch("toolsmith.files.os.read", side_effect=bounded_read):
        backup = unwrap(backup_store(store, "sample", tmp_path / "backup"))
        restored = unwrap(restore_store(tmp_path / "backup", "sample", tmp_path / "restored"))
    assert backup.bytes == restored.bytes and largest <= 65_536
    assert unwrap(check_integrity(tmp_path / "restored", "sample")).valid


def test_artifacts_above_the_old_16_mib_limit_remain_readable_and_restorable(
    store: Path, tmp_path: Path
) -> None:
    from toolsmith.storage.artifacts import put_file, read_file

    content = b"x" * (17 * 1024**2)
    reference = unwrap(
        put_file(store, "sample", content, "larger.bin", "application/octet-stream", "larger")
    )
    assert unwrap(read_file(store, "sample", reference.version)) == content
    backup = unwrap(backup_store(store, "sample", tmp_path / "larger-backup"))
    assert backup.bytes >= len(content) and backup.objects == 1
    unwrap(restore_store(tmp_path / "larger-backup", "sample", tmp_path / "larger-restored"))
    assert unwrap(read_file(tmp_path / "larger-restored", "sample", reference.version)) == content


def test_backup_has_no_10000_object_ceiling_and_keeps_20_gib_budget(
    store: Path, tmp_path: Path
) -> None:
    with open_store(store, "sample", write=True) as selected, selected.connection:
        for number in range(10_001):
            body = str(number).encode()
            checksum = hashlib.sha256(body).hexdigest()
            path = store / "objects" / checksum
            path.write_bytes(body)
            path.chmod(0o600)
            selected.connection.execute("INSERT INTO blob VALUES (?,?)", (checksum, len(body)))
    report = unwrap(backup_store(store, "sample", tmp_path / "backup"))
    assert report.objects == 10_001
    assert (
        unwrap(restore_store(tmp_path / "backup", "sample", tmp_path / "restored")).objects
        == 10_001
    )
    assert MAX_BACKUP_BYTES == 20 * 1024**3
    assert isinstance(
        backup_store(store, "sample", tmp_path / "too-large", MAX_BACKUP_BYTES + 1), Failure
    )
    assert not (tmp_path / "too-large").exists()


def test_backup_writer_and_reader_share_the_same_manifest_byte_budget(
    store: Path, tmp_path: Path
) -> None:
    with patch("toolsmith.operations.backup.MAX_MANIFEST_BYTES", 1):
        result = backup_store(store, "sample", tmp_path / "oversized-manifest")
    assert isinstance(result, Failure) and result.code == "limit"
    assert (tmp_path / "oversized-manifest/manifest.json").stat().st_size == 0
    assert isinstance(
        restore_store(tmp_path / "oversized-manifest", "sample", tmp_path / "restored"), Failure
    )
    assert not (tmp_path / "restored").exists()
