import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from toolsmith.clock import Clock, SystemClock
from toolsmith.result import ToolsmithError, boundary
from toolsmith.storage.database import open_store
from toolsmith.validation import fields, identity, integer, json_value, number

STAGED = re.compile(r"\.stage-[0-9a-f]{32}\.tmp\Z")


@dataclass(frozen=True)
class TemporaryFile:
    name: str
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class CleanupPlan:
    collection: str
    store_device: int
    store_inode: int
    created_at: float
    minimum_age_seconds: float
    files: tuple[TemporaryFile, ...]


def metadata(name: str, value: os.stat_result) -> TemporaryFile:
    return TemporaryFile(
        name, value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns
    )


@boundary
def preview_cleanup(
    root: Path, collection: str, minimum_age_seconds: float = 86_400, *, clock: Clock | None = None
) -> CleanupPlan:
    age = number(minimum_age_seconds, 0, 365 * 86_400, "Minimum age")
    now = (clock or SystemClock()).wall()
    with open_store(root, collection) as store:
        selected: list[TemporaryFile] = []
        for name in sorted(os.listdir(store.temporary.descriptor)):
            if not STAGED.fullmatch(name):
                continue
            value = os.stat(name, dir_fd=store.temporary.descriptor, follow_symlinks=False)
            if (
                stat.S_ISREG(value.st_mode)
                and value.st_uid == os.getuid()
                and value.st_nlink == 1
                and not stat.S_IMODE(value.st_mode) & 0o077
                and value.st_mtime <= now - age
            ):
                selected.append(metadata(name, value))
            if len(selected) > 1000:
                raise ToolsmithError(
                    "limit", "Cleanup preview exceeds 1,000 files; no deletion occurred"
                )
        root_metadata = os.fstat(store.directory.descriptor)
        return CleanupPlan(
            store.collection, root_metadata.st_dev, root_metadata.st_ino, now, age, tuple(selected)
        )


def validate_cleanup_plan(plan: object) -> CleanupPlan:
    value = fields(
        json_value(plan),
        {"collection", "store_device", "store_inode", "created_at", "minimum_age_seconds", "files"},
    )
    collection = identity(value["collection"], "Collection")
    created = number(value["created_at"], 0, 2**53, "Preview time")
    age = number(value["minimum_age_seconds"], 0, 365 * 86_400, "Minimum age")
    entries = value["files"]
    if not isinstance(entries, list) or len(entries) > 1000:
        raise ToolsmithError("invalid_input", "Cleanup files must be a bounded list")
    selected: list[TemporaryFile] = []
    for entry in entries:
        file = fields(entry, {"name", "device", "inode", "size", "modified_ns", "changed_ns"})
        name = file["name"]
        if not isinstance(name, str) or not STAGED.fullmatch(name):
            raise ToolsmithError("denied", "Cleanup selects only tool-owned staging filenames")
        selected.append(
            TemporaryFile(
                name,
                *(
                    integer(file[key], 0, 2**64 - 1, "File identity")
                    for key in ("device", "inode", "size", "modified_ns", "changed_ns")
                ),
            )
        )
    if len({entry.name for entry in selected}) != len(selected):
        raise ToolsmithError("invalid_input", "Cleanup preview contains duplicate files")
    return CleanupPlan(
        collection,
        integer(value["store_device"], 0, 2**64 - 1, "Store device"),
        integer(value["store_inode"], 0, 2**64 - 1, "Store inode"),
        created,
        age,
        tuple(selected),
    )


@boundary
def apply_cleanup(root: Path, collection: str, plan: CleanupPlan) -> dict[str, int]:
    checked = validate_cleanup_plan(plan)
    if checked.collection != collection:
        raise ToolsmithError("denied", "Cleanup preview belongs to another collection")
    with open_store(root, collection, write=True) as store:
        root_metadata = os.fstat(store.directory.descriptor)
        if (root_metadata.st_dev, root_metadata.st_ino) != (
            checked.store_device,
            checked.store_inode,
        ):
            raise ToolsmithError("denied", "Cleanup preview belongs to another store directory")
        for file in checked.files:
            try:
                current = os.stat(
                    file.name, dir_fd=store.temporary.descriptor, follow_symlinks=False
                )
            except FileNotFoundError as error:
                raise ToolsmithError(
                    "conflict", "A cleanup candidate changed; regenerate the preview"
                ) from error
            if (
                metadata(file.name, current) != file
                or not stat.S_ISREG(current.st_mode)
                or current.st_nlink != 1
                or current.st_uid != os.getuid()
                or stat.S_IMODE(current.st_mode) & 0o077
                or current.st_mtime > checked.created_at - checked.minimum_age_seconds
            ):
                raise ToolsmithError(
                    "conflict", "A cleanup candidate changed; no files were deleted"
                )
        for file in checked.files:
            os.unlink(file.name, dir_fd=store.temporary.descriptor)
        os.fsync(store.temporary.descriptor)
    return {"deleted": len(checked.files), "bytes": sum(file.size for file in checked.files)}
