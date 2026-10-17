import os
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from toolsmith.files import PrivateDirectory, child_directory, open_private, private_directory
from toolsmith.result import ToolsmithError


def relative_components(value: str) -> tuple[str, ...]:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 4096
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ToolsmithError("invalid_input", "Use a bounded canonical relative filename")
    parts = tuple(value.split("/"))
    if len(parts) > 64 or any(part in {"", ".", ".."} for part in parts):
        raise ToolsmithError("invalid_input", "Relative filenames cannot escape their root")
    return parts


@contextmanager
def relative_parent(
    root: PrivateDirectory, relative: str, *, create: bool = False
) -> Iterator[tuple[PrivateDirectory, str]]:
    parts = relative_components(relative)
    if type(create) is not bool:
        raise ToolsmithError("invalid_input", "Parent creation requires explicit Boolean intent")
    with ExitStack() as stack:
        parent = root
        for name in parts[:-1]:
            parent = stack.enter_context(child_directory(parent, name, create=create))
        yield parent, parts[-1]


@contextmanager
def relative_file(
    root: Path, relative: str, flags: int = os.O_RDONLY, *, create_parents: bool = False
) -> Iterator[int]:
    with (
        private_directory(root) as directory,
        relative_parent(directory, relative, create=create_parents) as (parent, name),
        open_private(parent, name, flags) as descriptor,
    ):
        yield descriptor
