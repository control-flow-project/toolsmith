import os
import platform
import shlex
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def compile_vector(source: Path, target: Path, directory: Path) -> None:
    compiler = shlex.split(os.environ.get("CC", "cl" if sys.platform == "win32" else "cc"))
    if sys.platform == "win32":
        arguments = compiler + [
            "/nologo",
            "/O2",
            "/DNDEBUG",
            "/DVEC1_THREADS=0",
            "/LD",
            "/I" + str(source.parent),
            str(source),
            "/link",
            "/OUT:" + str(target),
        ]
        subprocess.run(arguments, cwd=directory, check=True)
    else:
        common = ["-O3", "-DNDEBUG", "-DVEC1_THREADS=0", "-fPIC", "-I" + str(source.parent)]
        objects = []
        variants = (
            ("SCALAR", "AVX2") if platform.machine().lower() in {"x86_64", "amd64"} else (None,)
        )
        for variant in variants:
            output = directory / ((variant or "native") + ".o")
            flags = [] if variant is None else ["-DVEC1SIMD=" + variant]
            if variant == "AVX2":
                flags += ["-mavx2"]
            subprocess.run(
                compiler + common + flags + ["-c", str(source), "-o", str(output)],
                cwd=directory,
                check=True,
            )
            objects.append(str(output))
        subprocess.run(
            compiler
            + [
                "-dynamiclib" if sys.platform == "darwin" else "-shared",
                *objects,
                "-lm",
                "-o",
                str(target),
            ],
            cwd=directory,
            check=True,
        )


def build_vector(root: Path) -> Path:
    temporary = root / ".temp"
    temporary.mkdir(parents=True, exist_ok=True)
    suffix = ".dll" if sys.platform == "win32" else ".dylib" if sys.platform == "darwin" else ".so"
    target = root / "src/toolsmith/semantic" / ("_vec1" + suffix)
    with tempfile.TemporaryDirectory(prefix="native-build-", dir=temporary) as owned:
        directory = Path(owned)
        staged = directory / target.name
        compile_vector(root / "vendor/sqlite/vec1.c", staged, directory)
        os.replace(staged, target)
    return target


class NativeVectorBuild(BuildHookInterface[BuilderConfig]):
    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        target = build_vector(root)
        build_data["pure_python"] = False
        build_data["tag"] = "py3-none-" + sysconfig.get_platform().replace("-", "_").replace(
            ".", "_"
        )
        build_data["artifacts"] = [str(target.relative_to(root))]
