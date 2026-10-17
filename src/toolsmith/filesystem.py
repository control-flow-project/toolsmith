import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from toolsmith.files import (
    PrivateDirectory,
    absolute_path,
    check_private,
    child_directory,
    component,
    directory_descriptor,
    private_directory,
    private_file,
    rename_new,
    stable_identity,
)
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer


@dataclass(frozen=True)
class FileEntry:
    name: str
    content_bytes: int
    identity: tuple[int, int, int, int, int]


def walk_tree(
    directory: PrivateDirectory,
    maximum_records: int,
    maximum_bytes: int,
    *,
    sync: bool = False,
) -> Iterator[FileEntry]:
    maximum = integer(maximum_records, 1, 100000, "Maximum inventory records")
    byte_budget = integer(maximum_bytes, 1, 2**63 - 1, "Inventory byte budget")
    visited, used = 0, 0

    def visit(folder: PrivateDirectory, prefix: str, depth: int) -> Iterator[FileEntry]:
        nonlocal used, visited
        if depth > 64:
            raise ToolsmithError("limit", "Directory nesting exceeds its inventory budget")
        with os.scandir(folder.descriptor) as entries:
            for entry in entries:
                component(entry.name)
                visited += 1
                if visited > maximum:
                    raise ToolsmithError("limit", "Tree exceeds its explicit entry budget")
                name = prefix + entry.name
                if entry.is_dir(follow_symlinks=False):
                    with child_directory(folder, entry.name) as child:
                        yield from visit(child, name + "/", depth + 1)
                elif stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
                    with private_file(folder, entry.name) as descriptor:
                        metadata = check_private(descriptor)
                        used += metadata.st_size
                        if used > byte_budget:
                            raise ToolsmithError("limit", "Tree exceeds its explicit byte budget")
                        if sync:
                            os.fsync(descriptor)
                        yield FileEntry(name, metadata.st_size, stable_identity(metadata))
                else:
                    raise ToolsmithError("denied", "Tree contains a symlink or special file")
        if sync:
            os.fsync(folder.descriptor)

    yield from visit(directory, "", 0)


@boundary
def inventory(
    root: Path, maximum_records: int = 10000, maximum_bytes: int = 1024 * 1024 * 1024
) -> tuple[FileEntry, ...]:
    with private_directory(root) as directory:
        return tuple(
            sorted(
                walk_tree(directory, maximum_records, maximum_bytes), key=lambda entry: entry.name
            )
        )


@boundary
def sync_directory_tree(
    root: Path, maximum_records: int = 10000, maximum_bytes: int = 1024 * 1024 * 1024
) -> int:
    count = 0
    with private_directory(root) as directory:
        for _entry in walk_tree(directory, maximum_records, maximum_bytes, sync=True):
            count += 1
    return count


@boundary
def publish_directory(staging: Path, destination: Path) -> bool:
    absolute_path(staging)
    absolute_path(destination)
    if staging.parent != destination.parent:
        raise ToolsmithError(
            "invalid_input", "Atomic directory publication needs one explicit parent"
        )
    with private_directory(staging):
        pass
    with directory_descriptor(staging.parent) as parent:
        rename_new(PrivateDirectory(parent), staging.name, destination.name)
        os.fsync(parent)
    return True
