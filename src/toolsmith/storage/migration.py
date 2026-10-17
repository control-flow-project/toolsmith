import os
import sqlite3
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from toolsmith import lexical
from toolsmith.files import (
    MAX_FILE_BYTES,
    PrivateDirectory,
    child_directory,
    directory_descriptor,
    directory_lock,
    new_private,
    private_directory,
    private_file,
    read_private,
    rename_new,
)
from toolsmith.operations.integrity import (
    validate_database,
    validate_objects,
    validate_retained,
)
from toolsmith.result import ToolsmithError, boundary, unwrap
from toolsmith.semantic import migrate_index
from toolsmith.storage.database import (
    APPLICATION_ID,
    DATABASE_NAME,
    SCHEMA_VERSION,
    Store,
    StoreInfo,
    configure,
    info,
)
from toolsmith.validation import digest, identity, integer

VERSION_ONE_TABLES = {
    "collection",
    "item",
    "text_version",
    "part",
    "chunk",
    "chunk_search",
    "chunk_search_data",
    "chunk_search_idx",
    "chunk_search_content",
    "chunk_search_docsize",
    "chunk_search_config",
    "blob",
    "file_version",
    "operation",
    "embedding_profile",
    "embedding_document",
    "embedding_chunk",
}


def verify_source(store: Store, collection: str) -> None:
    connection = store.connection
    if connection.execute("PRAGMA application_id").fetchone()[
        0
    ] != APPLICATION_ID or connection.execute("PRAGMA user_version").fetchone()[0] not in {1, 2}:
        raise ToolsmithError(
            "integrity", "Migration requires a verified version-one or version-two archive"
        )
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    expected = (
        VERSION_ONE_TABLES
        if version == 1
        else (
            VERSION_ONE_TABLES
            - {
                "chunk",
                "chunk_search",
                "chunk_search_data",
                "chunk_search_idx",
                "chunk_search_content",
                "chunk_search_docsize",
                "chunk_search_config",
            }
        )
        | {
            "lexical_document",
            "lexical_chunk",
            "lexical_search",
            "lexical_search_data",
            "lexical_search_idx",
            "lexical_search_content",
            "lexical_search_docsize",
            "lexical_search_config",
        }
    )
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if (
        tables != expected
        or connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1"
        ).fetchone()
        is not None
    ):
        raise ToolsmithError("integrity", "Source does not match the reviewed version-one schema")
    binding = connection.execute("SELECT identity FROM collection WHERE id=1").fetchone()
    if binding is None or binding[0] != collection:
        raise ToolsmithError("denied", "Source belongs to another exact collection")
    validate_retained(store)
    validate_objects(store)


@boundary
def migrate_store(
    source: Path, collection: str, destination: Path, maximum_bytes: int = 20 * 1024**3
) -> StoreInfo:
    selected = identity(collection, "Collection")
    maximum = integer(maximum_bytes, 1, 20 * 1024**3, "Migration byte budget")
    if (
        not isinstance(source, Path)
        or not isinstance(destination, Path)
        or source == destination
        or source in destination.parents
    ):
        raise ToolsmithError(
            "invalid_input", "Migration needs a separate new destination, never an in-place reset"
        )
    with (
        private_directory(source) as original,
        directory_lock(original, shared=True),
        child_directory(original, "objects") as original_objects,
        child_directory(original, "tmp") as original_tmp,
    ):
        with private_file(original, DATABASE_NAME):
            pass
        original_connection = sqlite3.connect(
            f"file:/proc/self/fd/{original.descriptor}/{DATABASE_NAME}?mode=ro", uri=True, timeout=0
        )
        try:
            configure(original_connection)
            original_store = Store(
                original, original_objects, original_tmp, original_connection, selected
            )
            verify_source(original_store, selected)
            declared_bytes = original_connection.execute(
                "SELECT coalesce(sum(size),0) FROM blob"
            ).fetchone()[0]
            with private_file(original, DATABASE_NAME) as original_descriptor:
                if declared_bytes + os.fstat(original_descriptor).st_size > maximum:
                    raise ToolsmithError(
                        "limit", "Archive exceeds the explicit migration byte budget"
                    )
            with directory_descriptor(destination.parent) as parent:
                staged_name = ".stage-" + uuid4().hex
                os.mkdir(staged_name, 0o700, dir_fd=parent)
                copied: list[str] = []
                published = False
                try:
                    with (
                        child_directory(PrivateDirectory(parent), staged_name) as staged,
                        child_directory(staged, "objects", create=True) as objects,
                        child_directory(staged, "tmp", create=True) as temporary,
                    ):
                        new_private(staged, DATABASE_NAME, b"")
                        target = sqlite3.connect(
                            f"file:/proc/self/fd/{staged.descriptor}/{DATABASE_NAME}?mode=rw",
                            uri=True,
                            timeout=0,
                        )
                        try:
                            configure(target)
                            original_connection.backup(target)
                            for row in original_connection.execute(
                                "SELECT id FROM blob ORDER BY id"
                            ):
                                name = digest(row[0])
                                copied.append(name)
                                new_private(
                                    objects,
                                    name,
                                    read_private(original_objects, name, MAX_FILE_BYTES),
                                )
                            migrated = Store(staged, objects, temporary, target, selected)
                            verify_source(migrated, selected)
                            with target:
                                target.execute("BEGIN IMMEDIATE")
                                if target.execute("PRAGMA user_version").fetchone()[0] == 1:
                                    target.execute("DROP TABLE chunk_search")
                                    target.execute("DROP TABLE chunk")
                                    unwrap(lexical.initialize_index(target))
                                    for part in target.execute(
                                        "SELECT p.id, p.text, v.title FROM part p JOIN text_version v ON v.id=p.version_id ORDER BY p.id"
                                    ):
                                        unwrap(
                                            lexical.index_source(
                                                target,
                                                lexical.Source(
                                                    "part:" + str(part[0]), part[1], part[2]
                                                ),
                                                expected_digest=None,
                                            )
                                        )

                                def canonical(reference: str) -> str | None:
                                    row = target.execute(
                                        "SELECT text FROM part WHERE 'part:' || id = ?",
                                        (reference,),
                                    ).fetchone()
                                    return None if row is None else row[0]

                                unwrap(migrate_index(target, canonical))
                                target.execute(
                                    "ALTER TABLE collection ADD COLUMN generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0)"
                                )
                                from importlib.resources import files

                                current_schema = (
                                    files("toolsmith.storage").joinpath("schema.sql").read_text()
                                )
                                view = current_schema[
                                    current_schema.index("CREATE VIEW current_text") :
                                ]
                                view_statement, trigger_statement = view.split("CREATE TRIGGER", 1)
                                target.execute(view_statement)
                                target.execute("CREATE TRIGGER" + trigger_statement)
                                target.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                            validate_database(migrated)
                            validate_objects(migrated)
                            result = info(migrated)
                        finally:
                            target.close()
                        with private_file(staged, DATABASE_NAME) as descriptor:
                            os.fsync(descriptor)
                        os.fsync(objects.descriptor)
                        os.fsync(temporary.descriptor)
                        os.fsync(staged.descriptor)
                    rename_new(PrivateDirectory(parent), staged_name, destination.name)
                    os.fsync(parent)
                    published = True
                    return result
                finally:
                    if not published:
                        with child_directory(PrivateDirectory(parent), staged_name) as staged:
                            for name in (DATABASE_NAME, DATABASE_NAME + "-journal", ".lock"):
                                with suppress(FileNotFoundError):
                                    os.unlink(name, dir_fd=staged.descriptor)
                            with child_directory(staged, "objects") as objects:
                                for name in reversed(copied):
                                    with suppress(FileNotFoundError):
                                        os.unlink(name, dir_fd=objects.descriptor)
                            os.rmdir("objects", dir_fd=staged.descriptor)
                            os.rmdir("tmp", dir_fd=staged.descriptor)
                        os.rmdir(staged_name, dir_fd=parent)
        except sqlite3.Error as error:
            raise ToolsmithError(
                "integrity", "Forward archive migration failed; source remains unchanged"
            ) from error
        finally:
            original_connection.close()
