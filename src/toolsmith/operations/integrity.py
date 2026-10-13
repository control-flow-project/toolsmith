import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from toolsmith.files import MAX_FILE_BYTES, read_private
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.semantic import check_index
from toolsmith.storage.database import Store, open_store, row_integer, row_optional_text, row_text
from toolsmith.storage.index import index_part, text_chunks
from toolsmith.storage.models import Document, TextPart, file_name, media_type, validate_document
from toolsmith.validation import canonical_json, digest, json_value, parse_json, text


@dataclass(frozen=True)
class IntegrityReport:
    collection: str
    checked_objects: int
    checked_chunks: int
    valid: bool


def validate_retained(store: Store) -> None:
    connection = store.connection
    if [row[0] for row in connection.execute("PRAGMA integrity_check")] != [
        "ok"
    ] or connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ToolsmithError("integrity", "Database integrity or foreign-key verification failed")
    if (
        connection.execute(
            "SELECT 1 FROM item i LEFT JOIN text_version v ON v.id = i.latest_version WHERE v.id IS NULL OR v.item_id != i.id LIMIT 1"
        ).fetchone()
        is not None
    ):
        raise ToolsmithError(
            "integrity", "Current text version belongs to a different item or is missing"
        )
    for version in connection.execute("SELECT * FROM text_version"):
        parts: list[TextPart] = []
        for ordinal, part in enumerate(
            connection.execute(
                "SELECT * FROM part WHERE version_id = ? ORDER BY ordinal", (version["id"],)
            ),
            start=1,
        ):
            warnings = parse_json(row_text(part, "warnings", 65_536).encode())
            if not isinstance(warnings, list) or row_integer(part, "ordinal") != ordinal:
                raise ToolsmithError("integrity", "Text part ordinals or warnings are invalid")
            parts.append(
                TextPart(
                    row_text(part, "label", 200),
                    row_text(part, "text", 4 * 1024 * 1024),
                    part["physical_page"],
                    tuple(text(warning, 1024, "Warning") for warning in warnings),
                )
            )
            if hashlib.sha256(parts[-1].text.encode()).hexdigest() != part["text_digest"]:
                raise ToolsmithError("integrity", "Retained part digest differs from its text")
            if int(bool(parts[-1].text.strip())) != part["has_text"]:
                raise ToolsmithError("integrity", "Retained part text-presence metadata differs")
        document = validate_document(
            Document(
                row_text(version, "title"),
                tuple(parts),
                row_text(version, "method", 80),
                row_optional_text(version, "source_url"),
                row_optional_text(version, "published_at"),
                row_optional_text(version, "observed_at"),
            )
        )
        calculated = hashlib.sha256(
            canonical_json({"item": row_text(version, "item_id"), "document": json_value(document)})
        ).hexdigest()
        if calculated != version["id"] or sum(
            len(part.text.encode()) for part in parts
        ) != row_integer(version, "content_bytes"):
            raise ToolsmithError(
                "integrity",
                "Retained text or provenance differs from its immutable version identity",
            )
    for version in connection.execute("SELECT * FROM file_version"):
        calculated = hashlib.sha256(
            canonical_json(
                {
                    "content": digest(version["blob_id"]),
                    "name": file_name(version["name"]),
                    "media_type": media_type(version["media_type"]),
                    "source_url": row_optional_text(version, "source_url"),
                }
            )
        ).hexdigest()
        if calculated != version["id"]:
            raise ToolsmithError(
                "integrity", "File provenance differs from its immutable version identity"
            )


def validate_embeddings(store: Store) -> None:
    def source(reference: str) -> str | None:
        identifier = reference.removeprefix("part:")
        if (
            not reference.startswith("part:")
            or not identifier.isascii()
            or not identifier.isdecimal()
            or len(identifier) > 19
        ):
            raise ToolsmithError("integrity", "Stored semantic reference is not a retained part")
        part_id = int(identifier)
        if not 1 <= part_id <= 2**63 - 1 or identifier != str(part_id):
            raise ToolsmithError("integrity", "Stored semantic part identity exceeds native bounds")
        row = store.connection.execute(
            "SELECT p.text FROM part p JOIN item i ON i.latest_version = p.version_id WHERE p.id = ?",
            (part_id,),
        ).fetchone()
        return None if row is None else row_text(row, "text", 4 * 1024 * 1024)

    unwrap(check_index(store.connection, source))


def validate_database(store: Store) -> int:
    validate_retained(store)
    validate_embeddings(store)
    connection = store.connection
    for part in connection.execute("SELECT id, text FROM part ORDER BY id"):
        chunks = connection.execute(
            "SELECT start_offset, end_offset, text FROM chunk WHERE part_id = ? ORDER BY start_offset",
            (part["id"],),
        )
        for expected in text_chunks(row_text(part, "text", 4 * 1024 * 1024)):
            actual = next(chunks, None)
            if actual is None or tuple(actual) != expected:
                raise ToolsmithError(
                    "integrity", "Indexed chunks do not completely match the retained text"
                )
        if next(chunks, None) is not None:
            raise ToolsmithError("integrity", "Index contains unexpected retained-text chunks")
    mismatch = connection.execute(
        "SELECT 1 FROM chunk c JOIN part p ON p.id = c.part_id JOIN text_version v ON v.id = p.version_id LEFT JOIN chunk_search f ON f.rowid = c.id WHERE f.rowid IS NULL OR f.text != c.text OR f.title != v.title LIMIT 1"
    ).fetchone()
    orphan = connection.execute(
        "SELECT 1 FROM chunk_search f LEFT JOIN chunk c ON c.id = f.rowid WHERE c.id IS NULL LIMIT 1"
    ).fetchone()
    if mismatch is not None or orphan is not None:
        raise ToolsmithError("integrity", "Lexical index differs from the canonical retained text")
    probe = sqlite3.connect(":memory:")
    try:
        probe.deserialize(connection.serialize())
        probe.execute("PRAGMA trusted_schema = OFF")
        probe.execute("INSERT INTO chunk_search (chunk_search) VALUES ('integrity-check')")
    finally:
        probe.close()
    return int(connection.execute("SELECT count(*) FROM chunk").fetchone()[0])


def validate_objects(store: Store) -> int:
    count = 0
    for row in store.connection.execute("SELECT id, size FROM blob ORDER BY id"):
        checksum = digest(row_text(row, "id"), "Object identity")
        content = read_private(store.objects, checksum, MAX_FILE_BYTES)
        if (
            len(content) != row_integer(row, "size", MAX_FILE_BYTES)
            or hashlib.sha256(content).hexdigest() != checksum
        ):
            raise ToolsmithError(
                "integrity", "A retained object's bytes do not match its recorded identity"
            )
        count += 1
    return count


@boundary
def check_integrity(root: Path, collection: str) -> IntegrityReport:
    with open_store(root, collection) as store:
        chunks = validate_database(store)
        objects = validate_objects(store)
        return IntegrityReport(store.collection, objects, chunks, True)


@boundary
def rebuild_index(root: Path, collection: str) -> IntegrityReport:
    with open_store(root, collection, write=True) as store:
        with store.connection:
            validate_retained(store)
            store.connection.execute("DELETE FROM chunk_search")
            store.connection.execute("DELETE FROM chunk")
            for part in store.connection.execute(
                "SELECT p.id, p.text, v.title FROM part p JOIN text_version v ON v.id = p.version_id ORDER BY p.id"
            ):
                index_part(
                    store,
                    row_integer(part, "id"),
                    row_text(part, "title"),
                    row_text(part, "text", 4 * 1024 * 1024),
                )
        chunks = validate_database(store)
        return IntegrityReport(store.collection, 0, chunks, True)
