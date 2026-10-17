import hashlib
import io
import os
import stat
import struct
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from toolsmith.files import (
    FileDigest,
    PrivateDirectory,
    absolute_path,
    check_private,
    child_directory,
    directory_descriptor,
    regular_descriptor,
    rename_new,
    stable_identity,
    stream_file,
    write_chunk,
)
from toolsmith.result import ToolsmithError, boundary
from toolsmith.validation import digest, integer, text

MAX_MEMBERS = 10000
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class MemberSource:
    name: str
    path: Path


@dataclass(frozen=True)
class MemberDigest:
    name: str
    sha256: str
    content_bytes: int


@dataclass(frozen=True)
class ArchiveReport:
    members: tuple[MemberDigest, ...]
    archive: FileDigest


def member_name(value: object) -> str:
    selected = text(value, 1024, "Archive member")
    path = PurePosixPath(selected)
    if (
        path.is_absolute()
        or path.as_posix() != selected
        or not path.parts
        or len(path.parts) > 64
        or any(part in {".", ".."} for part in path.parts)
        or "\\" in selected
        or ":" in selected
        or any(ord(character) < 32 or ord(character) == 127 for character in selected)
    ):
        raise ToolsmithError("denied", "Archive member must be an exact safe relative file path")
    return selected


@boundary
def pack_files(
    sources: tuple[MemberSource, ...],
    destination: Path,
    maximum_bytes: int = MAX_ARCHIVE_BYTES,
    *,
    expected: tuple[MemberDigest, ...] | None = None,
) -> ArchiveReport:
    absolute_path(destination)
    maximum = integer(maximum_bytes, 1, MAX_ARCHIVE_BYTES, "Archive byte budget")
    if not isinstance(sources, tuple) or not 1 <= len(sources) <= MAX_MEMBERS:
        raise ToolsmithError("invalid_input", "Supply an explicit bounded member tuple")
    names: set[str] = set()
    for source in sources:
        if not isinstance(source, MemberSource):
            raise ToolsmithError("invalid_input", "Supply typed member sources")
        selected = member_name(source.name)
        if selected in names:
            raise ToolsmithError("conflict", "Archive member names must be unique")
        names.add(selected)
    if sum(46 + len(name.encode("utf-8")) for name in names) > 4 * 1024 * 1024:
        raise ToolsmithError("limit", "Archive central directory exceeds the shared 4 MiB budget")
    if any(
        str(parent) in names
        for name in names
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    ):
        raise ToolsmithError("conflict", "Archive file names collide with parent directories")
    identities: dict[str, MemberDigest] | None = None
    if expected is not None:
        if not isinstance(expected, tuple) or any(
            not isinstance(member, MemberDigest) for member in expected
        ):
            raise ToolsmithError("invalid_input", "Supply typed exact expected member identities")
        identities = {}
        for expected_member in expected:
            name = member_name(expected_member.name)
            digest(expected_member.sha256)
            integer(expected_member.content_bytes, 0, MAX_MEMBER_BYTES, "Member bytes")
            if name in identities:
                raise ToolsmithError("conflict", "Expected member names must be unique")
            identities[name] = expected_member
        if set(identities) != names:
            raise ToolsmithError(
                "conflict", "Expected identities must match the exact selected files"
            )
    with directory_descriptor(destination.parent) as parent:
        staged = ".stage-" + uuid4().hex + ".tmp"
        descriptor = os.open(
            staged,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent,
        )
        try:
            members: list[MemberDigest] = []
            expanded = 0
            with (
                os.fdopen(os.dup(descriptor), "w+b") as stream,
                zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive,
            ):
                for source in sources:
                    info = zipfile.ZipInfo(source.name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o600) << 16
                    with (
                        regular_descriptor(source.path) as incoming,
                        archive.open(info, "w") as member,
                    ):
                        result = stream_file(
                            incoming, min(MAX_MEMBER_BYTES, maximum - expanded), sink=member.write
                        )
                        expanded += result.content_bytes
                        members.append(
                            MemberDigest(source.name, result.sha256, result.content_bytes)
                        )
                stream.flush()
            os.fsync(descriptor)
            if identities is not None and any(
                identities[member.name] != member for member in members
            ):
                raise ToolsmithError(
                    "conflict",
                    "Archive source differs from its expected identity; nothing was published",
                )
            os.lseek(descriptor, 0, os.SEEK_SET)
            archive_digest = stream_file(descriptor, maximum)
            rename_new(PrivateDirectory(parent), staged, destination.name)
            os.fsync(parent)
            return ArchiveReport(tuple(members), archive_digest)
        finally:
            os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(staged, dir_fd=parent)


def central_directory(stream: io.BufferedReader) -> None:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    if size > MAX_ARCHIVE_BYTES:
        raise ToolsmithError("limit", "Archive exceeds its byte budget")
    stream.seek(max(0, size - 65557))
    tail = stream.read(65557)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise ToolsmithError("invalid_input", "Archive lacks a complete central directory")
    disk, directory_disk, on_disk, total, directory_bytes, directory_offset, comment = (
        struct.unpack("<4H2IH", tail[offset + 4 : offset + 22])
    )
    if (
        disk
        or directory_disk
        or on_disk != total
        or total > MAX_MEMBERS
        or directory_bytes > 4 * 1024 * 1024
        or directory_offset + directory_bytes > size
        or offset + 22 + comment != len(tail)
    ):
        raise ToolsmithError(
            "denied", "Archive directory exceeds the single-volume structural budget"
        )
    stream.seek(0)


@boundary
def read_archive_member(source: Path, name: str, maximum_bytes: int = 4 * 1024 * 1024) -> bytes:
    selected = member_name(name)
    maximum = integer(maximum_bytes, 1, MAX_MEMBER_BYTES, "Maximum member bytes")
    with regular_descriptor(source) as descriptor:
        before = os.fstat(descriptor)
        try:
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                central_directory(stream)
                with zipfile.ZipFile(stream) as archive:
                    records = archive.infolist()
                    names: set[str] = set()
                    requested = None
                    for record in records:
                        current = member_name(record.filename)
                        if (
                            current in names
                            or record.is_dir()
                            or record.flag_bits & 1
                            or stat.S_IFMT(record.external_attr >> 16) not in {0, stat.S_IFREG}
                            or record.compress_type
                            not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                            or record.file_size > MAX_MEMBER_BYTES
                        ):
                            raise ToolsmithError(
                                "denied", "Archive contains unsafe, duplicate or oversized members"
                            )
                        names.add(current)
                        if current == selected:
                            requested = record
                    if requested is None:
                        raise ToolsmithError("not_found", "Exact archive member was not found")
                    if requested.file_size > maximum:
                        raise ToolsmithError(
                            "limit", "Selected archive member exceeds its explicit byte budget"
                        )
                    with archive.open(requested) as member:
                        content = member.read(maximum + 1)
                    if len(content) > maximum or len(content) != requested.file_size:
                        raise ToolsmithError(
                            "limit", "Selected archive member exceeds its declared size"
                        )
                if stable_identity(before) != stable_identity(os.fstat(descriptor)):
                    raise ToolsmithError("conflict", "Archive changed during member inspection")
                return content
        except (zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError) as error:
            raise ToolsmithError("integrity", "Archive member or checksum is invalid") from error


@boundary
def unpack_files(
    source: Path,
    destination: Path,
    expected: tuple[MemberDigest, ...],
    maximum_bytes: int = MAX_ARCHIVE_BYTES,
) -> ArchiveReport:
    absolute_path(destination)
    maximum = integer(maximum_bytes, 1, MAX_ARCHIVE_BYTES, "Expanded archive budget")
    if not isinstance(expected, tuple) or not 1 <= len(expected) <= MAX_MEMBERS:
        raise ToolsmithError("invalid_input", "Supply exact expected member identities")
    members: dict[str, MemberDigest] = {}
    for member in expected:
        if not isinstance(member, MemberDigest):
            raise ToolsmithError("invalid_input", "Supply typed expected members")
        name = member_name(member.name)
        digest(member.sha256)
        integer(member.content_bytes, 0, MAX_MEMBER_BYTES, "Member bytes")
        if name in members:
            raise ToolsmithError("conflict", "Expected member identities must be unique")
        members[name] = member
    if sum(member.content_bytes for member in members.values()) > maximum:
        raise ToolsmithError("limit", "Expected members exceed the expanded byte budget")
    if any(
        str(parent) in members
        for name in members
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    ):
        raise ToolsmithError("conflict", "Expected file names collide with parent directories")
    with regular_descriptor(source) as incoming, directory_descriptor(destination.parent) as parent:
        before = os.fstat(incoming)
        temporary = ".stage-" + uuid4().hex
        os.mkdir(temporary, 0o700, dir_fd=parent)
        written: list[str] = []
        directories: set[str] = set()
        published = False
        try:
            with os.fdopen(os.dup(incoming), "rb") as stream:
                central_directory(stream)
                with zipfile.ZipFile(stream) as archive:
                    records = archive.infolist()
                    if len(records) != len(members) or {
                        record.filename for record in records
                    } != set(members):
                        raise ToolsmithError(
                            "integrity", "Archive differs from the exact expected file set"
                        )
                    with child_directory(PrivateDirectory(parent), temporary) as staging:
                        for record in records:
                            name = member_name(record.filename)
                            mode = record.external_attr >> 16
                            expected_member = members[name]
                            if (
                                record.is_dir()
                                or record.flag_bits & 1
                                or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                                or record.compress_type
                                not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                                or record.file_size != expected_member.content_bytes
                            ):
                                raise ToolsmithError(
                                    "denied", "Archive contains an unsafe or mismatched member"
                                )
                            parts = PurePosixPath(name).parts
                            folder = staging
                            descriptors: list[int] = []
                            try:
                                for position, part in enumerate(parts[:-1], 1):
                                    relative = "/".join(parts[:position])
                                    if relative not in directories:
                                        os.mkdir(part, 0o700, dir_fd=folder.descriptor)
                                        directories.add(relative)
                                    descriptor = os.open(
                                        part,
                                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                        dir_fd=folder.descriptor,
                                    )
                                    check_private(descriptor, directory=True)
                                    descriptors.append(descriptor)
                                    folder = PrivateDirectory(descriptor)
                                outgoing = os.open(
                                    parts[-1],
                                    os.O_WRONLY
                                    | os.O_CREAT
                                    | os.O_EXCL
                                    | os.O_NOFOLLOW
                                    | os.O_CLOEXEC,
                                    0o600,
                                    dir_fd=folder.descriptor,
                                )
                                written.append(name)
                                try:
                                    checksum = hashlib.sha256()
                                    consumed = 0
                                    with archive.open(record) as content:
                                        while chunk := content.read(
                                            min(65536, expected_member.content_bytes + 1 - consumed)
                                        ):
                                            consumed += len(chunk)
                                            if consumed > expected_member.content_bytes:
                                                raise ToolsmithError(
                                                    "limit",
                                                    "Archive member exceeds its expected byte count",
                                                )
                                            checksum.update(chunk)
                                            write_chunk(outgoing, chunk)
                                    if (
                                        consumed != expected_member.content_bytes
                                        or checksum.hexdigest() != expected_member.sha256
                                    ):
                                        raise ToolsmithError(
                                            "integrity",
                                            "Archive member does not match its exact identity",
                                        )
                                    os.fsync(outgoing)
                                finally:
                                    os.close(outgoing)
                                os.fsync(folder.descriptor)
                            finally:
                                for descriptor in reversed(descriptors):
                                    os.close(descriptor)
                if stable_identity(before) != stable_identity(os.fstat(incoming)):
                    raise ToolsmithError("conflict", "Archive changed during verification")
            os.lseek(incoming, 0, os.SEEK_SET)
            archive_digest = stream_file(incoming, maximum)
            if stable_identity(before) != stable_identity(os.fstat(incoming)):
                raise ToolsmithError("conflict", "Archive changed before publication")
            rename_new(PrivateDirectory(parent), temporary, destination.name)
            os.fsync(parent)
            published = True
            return ArchiveReport(expected, archive_digest)
        except (zipfile.BadZipFile, RuntimeError, EOFError) as error:
            raise ToolsmithError("integrity", "ZIP content or checksum is invalid") from error
        finally:
            if not published:
                with child_directory(PrivateDirectory(parent), temporary) as staging:
                    for name in reversed(written):
                        with suppress(FileNotFoundError):
                            os.unlink(name, dir_fd=staging.descriptor)
                    for name in sorted(directories, key=lambda name: name.count("/"), reverse=True):
                        os.rmdir(name, dir_fd=staging.descriptor)
                os.rmdir(temporary, dir_fd=parent)
