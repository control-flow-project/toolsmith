import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hatch_build import build_vector


def test_native_build_replaces_complete_artifacts_without_truncating_open_files(
    tmp_path: Path,
) -> None:
    target = tmp_path / "src/toolsmith/semantic/_vec1.so"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"Previous loaded library")

    def compile_output(
        arguments: list[str], *, cwd: Path, check: bool
    ) -> subprocess.CompletedProcess[bytes]:
        assert cwd.parent == tmp_path / ".temp" and check
        output = Path(arguments[arguments.index("-o") + 1])
        assert output.parent == cwd
        output.write_bytes(b"Complete new artifact")
        return subprocess.CompletedProcess(arguments, 0)

    with (
        target.open("rb") as previous,
        patch("hatch_build.subprocess.run", side_effect=compile_output),
    ):
        assert build_vector(tmp_path) == target
        assert previous.read() == b"Previous loaded library"
    assert target.read_bytes() == b"Complete new artifact"
    assert not list((tmp_path / ".temp").iterdir())


def test_failed_native_build_keeps_the_previous_artifact_and_disposes_owned_outputs(
    tmp_path: Path,
) -> None:
    target = tmp_path / "src/toolsmith/semantic/_vec1.so"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"Previous loaded library")
    failure = subprocess.CalledProcessError(2, ["compiler"])
    with (
        patch("hatch_build.subprocess.run", side_effect=failure),
        pytest.raises(subprocess.CalledProcessError),
    ):
        build_vector(tmp_path)
    assert target.read_bytes() == b"Previous loaded library"
    assert not list((tmp_path / ".temp").iterdir())
