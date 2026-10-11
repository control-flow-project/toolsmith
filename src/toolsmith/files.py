import hashlib
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import integer

MAX_FILE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class PrivateDirectory:
    descriptor: int


def require_filesystem() -> None:
    if sys.platform != "linux" or not hasattr(os, "O_NOFOLLOW"):
        raise ToolsmithError(
            "unavailable", "Safe persistence requires Linux no-follow directory operations"
        )


def absolute_path(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute() or ".." in value.parts:
        raise ToolsmithError(
            "invalid_input", "An explicit absolute Path without parent traversal is required"
        )
    return value


def component(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\x00" in name
    ):
        raise ToolsmithError(
            "denied", "Private file operations require a single explicit leaf component"
        )
    return name


@contextmanager
def directory_descriptor(path: Path) -> Iterator[int]:
    require_filesystem()
    absolute_path(path)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            replacement = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = replacement
        yield descriptor
    finally:
        os.close(descriptor)


def check_private(descriptor: int, *, directory: bool = False) -> os.stat_result:
    metadata = os.fstat(descriptor)
    correct_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if (
        not correct_type
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or not directory
        and metadata.st_nlink != 1
    ):
        raise ToolsmithError(
            "denied",
            "Private state must be owned by the caller, regular and inaccessible to other users",
        )
    return metadata


@contextmanager
def private_directory(path: Path, *, create: bool = False) -> Iterator[PrivateDirectory]:
    absolute_path(path)
    if path == Path("/"):
        raise ToolsmithError(
            "invalid_input", "The filesystem root cannot be a private state directory"
        )
    with directory_descriptor(path.parent) as parent:
        if create:
            try:
                os.mkdir(path.name, 0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
        try:
            check_private(descriptor, directory=True)
            yield PrivateDirectory(descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def new_directory(path: Path) -> Iterator[PrivateDirectory]:
    absolute_path(path)
    with directory_descriptor(path.parent) as parent:
        try:
            os.mkdir(path.name, 0o700, dir_fd=parent)
        except FileExistsError as error:
            raise ToolsmithError(
                "conflict", "Destination already exists; nothing was overwritten"
            ) from error
        os.fsync(parent)
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
        try:
            check_private(descriptor, directory=True)
            yield PrivateDirectory(descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def child_directory(
    parent: PrivateDirectory, name: str, *, create: bool = False
) -> Iterator[PrivateDirectory]:
    component(name)
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent.descriptor)
            os.fsync(parent.descriptor)
        except FileExistsError:
            pass
    descriptor = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent.descriptor
    )
    try:
        check_private(descriptor, directory=True)
        yield PrivateDirectory(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def private_file(directory: PrivateDirectory, name: str, *, create: bool = False) -> Iterator[int]:
    component(name)
    flags = os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    if create:
        flags |= os.O_CREAT
    descriptor = os.open(name, flags, 0o600, dir_fd=directory.descriptor)
    try:
        check_private(descriptor)
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def directory_lock(
    directory: PrivateDirectory, name: str = ".lock", *, shared: bool = False
) -> Iterator[None]:
    import fcntl

    with private_file(directory, name, create=True) as descriptor:
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ToolsmithError(
                "deferred", "Another invocation is using the selected state", 0.1
            ) from error
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)


def read_descriptor(descriptor: int, maximum: int) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ToolsmithError("denied", "Input must be a regular file, not a device, pipe or socket")
    if before.st_size > maximum:
        raise ToolsmithError("limit", "File exceeds its explicit byte limit")
    content = bytearray()
    while len(content) <= maximum:
        chunk = os.read(descriptor, min(65_536, maximum + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
    after = os.fstat(descriptor)
    if len(content) > maximum:
        raise ToolsmithError("limit", "File exceeded its explicit byte limit while reading")
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or len(content) != after.st_size:
        raise ToolsmithError("conflict", "Input changed during its bounded read")
    return bytes(content)


def read_private(directory: PrivateDirectory, name: str, maximum: int) -> bytes:
    with private_file(directory, name) as descriptor:
        return read_descriptor(descriptor, maximum)


def write_descriptor(descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise ToolsmithError("io", "The explicit file write did not make progress")
        remaining = remaining[written:]
    os.fsync(descriptor)


def new_private(directory: PrivateDirectory, name: str, content: bytes) -> None:
    component(name)
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory.descriptor,
    )
    try:
        write_descriptor(descriptor, content)
    finally:
        os.close(descriptor)
    os.fsync(directory.descriptor)


def replace_private(directory: PrivateDirectory, name: str, content: bytes) -> None:
    component(name)
    temporary = ".stage-" + uuid4().hex + ".tmp"
    try:
        new_private(directory, temporary, content)
        os.replace(
            temporary, name, src_dir_fd=directory.descriptor, dst_dir_fd=directory.descriptor
        )
        os.fsync(directory.descriptor)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory.descriptor)


def put_object(objects: PrivateDirectory, temporary: PrivateDirectory, content: bytes) -> str:
    checksum = hashlib.sha256(content).hexdigest()
    staged = ".stage-" + uuid4().hex + ".tmp"
    try:
        new_private(temporary, staged, content)
        try:
            os.link(
                staged,
                checksum,
                src_dir_fd=temporary.descriptor,
                dst_dir_fd=objects.descriptor,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            existing = read_private(objects, checksum, MAX_FILE_BYTES)
            if existing != content:
                raise ToolsmithError(
                    "integrity", "Stored object does not match its immutable content identity"
                ) from error
        os.fsync(objects.descriptor)
    finally:
        try:
            os.unlink(staged, dir_fd=temporary.descriptor)
            os.fsync(temporary.descriptor)
        except FileNotFoundError:
            pass
    return checksum


@boundary
def read_bytes(path: Path, maximum_bytes: int = MAX_FILE_BYTES) -> bytes:
    absolute_path(path)
    maximum = integer(maximum_bytes, 1, MAX_FILE_BYTES, "Maximum bytes")
    with directory_descriptor(path.parent) as parent:
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
        try:
            return read_descriptor(descriptor, maximum)
        finally:
            os.close(descriptor)


@boundary
def write_new_bytes(path: Path, content: bytes) -> dict[str, int | bool]:
    absolute_path(path)
    if not isinstance(content, bytes) or len(content) > MAX_FILE_BYTES:
        raise ToolsmithError("invalid_input", "Output must be bounded bytes")
    with directory_descriptor(path.parent) as parent:
        directory = PrivateDirectory(parent)
        staged = ".stage-" + uuid4().hex + ".tmp"
        try:
            new_private(directory, staged, content)
            try:
                os.link(
                    staged, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False
                )
            except FileExistsError as error:
                raise ToolsmithError(
                    "conflict", "Destination already exists; no file was overwritten"
                ) from error
            os.fsync(parent)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(staged, dir_fd=parent)
    return {"exported": True, "bytes": len(content)}
