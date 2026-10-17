import os
from pathlib import Path

import pytest

from toolsmith.files import private_directory, write_descriptor
from toolsmith.paths import relative_components, relative_file, relative_parent
from toolsmith.result import ToolsmithError


def test_relative_files_create_private_parents_and_read(tmp_path: Path) -> None:
    with relative_file(
        tmp_path, "nested/other/value", os.O_WRONLY | os.O_CREAT | os.O_EXCL, create_parents=True
    ) as descriptor:
        write_descriptor(descriptor, b"first")
    with relative_file(tmp_path, "nested/other/value", os.O_RDWR | os.O_APPEND) as descriptor:
        write_descriptor(descriptor, b" second")
    with relative_file(tmp_path, "nested/other/value") as descriptor:
        assert os.read(descriptor, 100) == b"first second"
    assert (tmp_path / "nested").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "nested/other/value").stat().st_mode & 0o777 == 0o600
    with private_directory(tmp_path) as root, relative_parent(root, "nested/other/value") as item:
        assert item[1] == "value"


def test_truncate_checks_private_identity_before_modifying(tmp_path: Path) -> None:
    path = tmp_path / "value"
    path.write_bytes(b"preserve")
    path.chmod(0o600)
    os.link(path, tmp_path / "alias")
    with (
        pytest.raises(ToolsmithError, match="Private state"),
        relative_file(tmp_path, "value", os.O_WRONLY | os.O_TRUNC),
    ):
        pytest.fail("A hardlinked file was opened for truncation")
    assert path.read_bytes() == b"preserve"
    (tmp_path / "alias").unlink()
    with relative_file(tmp_path, "value", os.O_WRONLY | os.O_TRUNC):
        pass
    assert path.read_bytes() == b""


@pytest.mark.parametrize("name", ["../value", "/value", "a//b", "a/./b", "a\\b", "a\n", ""])
def test_relative_names_cannot_escape(name: str) -> None:
    with pytest.raises(ToolsmithError):
        relative_components(name)


def test_relative_files_reject_links_and_unsupported_flags(tmp_path: Path) -> None:
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError), relative_file(tmp_path, "link/value", os.O_WRONLY | os.O_CREAT):
        pytest.fail("A linked parent was opened")
    for flags in (-1, os.O_RDONLY | os.O_TRUNC, os.O_EXCL, os.O_DIRECTORY):
        with pytest.raises(ToolsmithError), relative_file(tmp_path, "value", flags):
            pytest.fail("Unsupported file flags were accepted")
