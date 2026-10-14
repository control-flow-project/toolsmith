import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from toolsmith import lexical
from toolsmith.files import MAX_FILE_BYTES, read_private
from toolsmith.readers.models import Document, TextPart
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.semantic import check_index
from toolsmith.storage.database import Store, open_store, row_integer, row_optional_text, row_text
from toolsmith.storage.models import file_name, media_type, validate_document
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

    def source(reference: str) -> str | None:
        row = store.connection.execute(
            "SELECT text FROM part WHERE 'part:' || id = ?",
            (reference,),
        ).fetchone()
        return None if row is None else row_text(row, "text", 4 * 1024 * 1024)

    count = unwrap(lexical.check_index(store.connection, source))
    if count != store.connection.execute("SELECT count(*) FROM part").fetchone()[0]:
        raise ToolsmithError("integrity", "Lexical index is missing retained parts")
    if (
        store.connection.execute(
            "SELECT 1 FROM lexical_document d LEFT JOIN part p ON d.reference = 'part:' || p.id "
            "LEFT JOIN text_version v ON v.id = p.version_id WHERE p.id IS NULL OR d.title != v.title LIMIT 1"
        ).fetchone()
        is not None
    ):
        raise ToolsmithError(
            "integrity", "Lexical title or source binding differs from retained text"
        )
    probe = sqlite3.connect(":memory:")
    try:
        probe.deserialize(store.connection.serialize())
        probe.execute("PRAGMA trusted_schema = OFF")
        probe.execute("INSERT INTO lexical_search (lexical_search) VALUES ('integrity-check')")
    finally:
        probe.close()
    return int(store.connection.execute("SELECT count(*) FROM lexical_chunk").fetchone()[0])


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
            store.connection.execute("DELETE FROM lexical_search")
            store.connection.execute("DELETE FROM lexical_document")
            for part in store.connection.execute(
                "SELECT p.id, p.text, v.title FROM part p JOIN text_version v ON v.id = p.version_id ORDER BY p.id"
            ):
                unwrap(
                    lexical.index_source(
                        store.connection,
                        lexical.Source(
                            "part:" + str(row_integer(part, "id")),
                            row_text(part, "text", 4 * 1024 * 1024),
                            row_text(part, "title"),
                        ),
                        expected_digest=None,
                    )
                )
        chunks = validate_database(store)
        return IntegrityReport(store.collection, 0, chunks, True)
