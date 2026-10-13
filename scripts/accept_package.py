import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from verify import require_limits

ROOT = Path(__file__).resolve().parents[1]

SMOKE = """
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path
parent = Path.cwd()
before = set(parent.iterdir())
import toolsmith
from toolsmith.acquisition.http import acquire_http
from toolsmith.acquisition.policy import SourcePolicy
from toolsmith.readers import read_text, read_html, read_feed
from toolsmith.result import Failure, unwrap
from toolsmith.retrieval import read_citation, search_text
from toolsmith.operations.backup import backup_store, restore_store
from toolsmith.storage.database import initialize_store
from toolsmith.storage.text import put_text
from toolsmith.storage.artifacts import put_file, read_file, export_file
from toolsmith.operations.integrity import check_integrity
assert Path(toolsmith.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert importlib.util.find_spec('dns') is None
assert importlib.util.find_spec('onnxruntime') is None
assert importlib.util.find_spec('tokenizers') is None
from toolsmith.semantic import Candidate, Source, encode_query, initialize_index, inspect_model
assert 'onnxruntime' not in sys.modules and 'numpy' not in sys.modules
assert importlib.metadata.version('ctlflow-toolsmith') == '0.1.0'
assert importlib.metadata.metadata('ctlflow-toolsmith')['License-Expression'] == 'LicenseRef-Proprietary'
assert set(parent.iterdir()) == before
assert unwrap(read_html(b'<main>Meaningful text</main>')).parts[0].text == 'Meaningful text'
assert len(unwrap(read_feed(b'<rss><channel><item><link>https://example.com/a</link></item></channel></rss>', 'https://example.com/feed')).entries) == 1
root = parent / 'store'
unwrap(initialize_store(root, 'sample'))
document = unwrap(read_text(b'Installed package lexical words', 'Installed'))
reference = unwrap(put_text(root, 'sample', 'doc', document, 'text'))
assert unwrap(search_text(root, 'sample', 'lexical'))
assert unwrap(read_citation(root, 'sample', reference.version, 1)).text == document.parts[0].text
file = unwrap(put_file(root, 'sample', b'original bytes', 'original.txt', 'text/plain', 'file'))
assert unwrap(read_file(root, 'sample', file.version)) == b'original bytes'
unwrap(export_file(root, 'sample', file.version, parent / 'exported.txt'))
failure = acquire_http(root, 'sample', parent / 'network', 'https://example.com/', SourcePolicy('source', ('example.com',), 'text_only'), 'http', item='online')
assert isinstance(failure, Failure) and failure.code == 'unavailable'
assert unwrap(check_integrity(root, 'sample')).valid
unwrap(backup_store(root, 'sample', parent / 'backup'))
unwrap(restore_store(parent / 'backup', 'sample', parent / 'restored'))
assert unwrap(check_integrity(parent / 'restored', 'sample')).valid
print(json.dumps({'installed_library':'passed','base_dependencies':0,'optional_http_absent':True,'schema_license_and_typed_result':'passed'}))
"""


def run(arguments: list[str], directory: Path, *, expected: int = 0) -> str:
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(name, None)
    result = subprocess.run(
        arguments, cwd=directory, env=environment, capture_output=True, text=True, timeout=180
    )
    if result.returncode != expected:
        raise RuntimeError("Installed-package command failed: " + result.stdout + result.stderr)
    return result.stdout


def check_archives(wheel: Path, source: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "toolsmith/storage/schema.sql" in names
        assert "toolsmith/semantic/schema.sql" in names
        assert "toolsmith/py.typed" in names
        assert any(name.endswith("/licenses/LICENSE") for name in names)
        assert not any(name.startswith(("tests/", "scripts/", "docs/")) for name in names)
        metadata = archive.read(next(name for name in names if name.endswith("/METADATA"))).decode()
        assert "Private :: Do Not Upload" in metadata
        assert "License-Expression: LicenseRef-Proprietary" in metadata
        assert all(
            "extra == 'http'" in line or "extra == 'semantic'" in line
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist:")
        )
    with tarfile.open(source, "r:gz") as archive:
        source_names = archive.getnames()
        assert any(name.endswith("/tests/test_http.py") for name in source_names)
        assert any(name.endswith("/docs/specification.md") for name in source_names)
        assert any(name.endswith("/src/toolsmith/storage/schema.sql") for name in source_names)
        names += source_names
    assert not any(
        part in {".analysis", ".venv", ".temp", ".data", ".verification", "__pycache__"}
        for name in names
        for part in Path(name).parts
    )
    assert not any(name.endswith((".sqlite3", ".env", ".pyc")) for name in names)
    assert not any(name.endswith((".onnx", ".safetensors")) for name in names)


def main() -> int:
    require_limits()
    wheel = ROOT / "dist/ctlflow_toolsmith-0.1.0-py3-none-any.whl"
    source = ROOT / "dist/ctlflow_toolsmith-0.1.0.tar.gz"
    check_archives(wheel, source)
    uv = os.environ.get("TOOLSMITH_UV") or shutil.which("uv")
    if uv is None:
        raise RuntimeError("Installed-package verification requires the existing uv executable")
    interpreter = os.environ.get("TOOLSMITH_PYTHON", sys.executable)
    with tempfile.TemporaryDirectory(prefix="toolsmith-installed-") as directory:
        parent = Path(directory)
        for label, artifact in (("wheel", wheel), ("sdist", source)):
            environment = parent / (label + "-venv")
            run([uv, "venv", "--python", interpreter, str(environment)], parent)
            python = environment / "bin/python"
            run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--exclude-newer",
                    "2026-10-04T00:00:00Z",
                    "--no-deps",
                    str(artifact),
                ],
                parent,
            )
            workspace = parent / (label + "-workspace")
            workspace.mkdir(mode=0o700)
            print(run([str(python), "-c", SMOKE], workspace), end="")
            capability = json.loads(
                run([str(environment / "bin/toolsmith"), "--json", "capabilities"], workspace)
            )
            assert capability["ok"] is True
            command = json.loads(
                run(
                    [
                        str(environment / "bin/toolsmith"),
                        "--json",
                        "--root",
                        str(workspace / "store"),
                        "--collection",
                        "sample",
                        "text",
                        "search",
                        "lexical",
                    ],
                    workspace,
                )
            )
            assert command["ok"] is True and command["result"]
            print(label + " installed CLI/library acceptance passed", flush=True)
            model_directory = os.environ.get("TOOLSMITH_MODEL_DIRECTORY")
            api_header = os.environ.get("TOOLSMITH_API_HEADER")
            if model_directory is not None and api_header is not None:
                run(
                    [
                        uv,
                        "pip",
                        "install",
                        "--python",
                        str(python),
                        "--exclude-newer",
                        "2026-10-04T00:00:00Z",
                        str(artifact) + "[semantic]",
                    ],
                    parent,
                )
                print(
                    run(
                        [
                            str(python),
                            str(ROOT / "scripts/accept_semantic.py"),
                            "--model-directory",
                            model_directory,
                            "--api-header",
                            api_header,
                        ],
                        workspace,
                    ),
                    end="",
                )
                semantic_cli = json.loads(
                    run(
                        [
                            str(environment / "bin/toolsmith"),
                            "--json",
                            "--root",
                            str(workspace / "store"),
                            "--collection",
                            "sample",
                            "semantic",
                            "index",
                            "--model-directory",
                            model_directory,
                        ],
                        workspace,
                    )
                )
                assert (
                    semantic_cli["ok"] is True and semantic_cli["result"]["status"]["pending"] == 0
                )
                searched = json.loads(
                    run(
                        [
                            str(environment / "bin/toolsmith"),
                            "--json",
                            "--root",
                            str(workspace / "store"),
                            "--collection",
                            "sample",
                            "semantic",
                            "search",
                            "lexical words",
                            "--model-directory",
                            model_directory,
                        ],
                        workspace,
                    )
                )
                assert (
                    searched["ok"] is True
                    and searched["result"]["hits"][0]["citation"]["item"] == "doc"
                )
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(parent / "wheel-venv/bin/python"),
                "--exclude-newer",
                "2026-10-04T00:00:00Z",
                str(wheel) + "[http]",
            ],
            parent,
        )
        print(
            run(
                [
                    str(parent / "wheel-venv/bin/python"),
                    "-c",
                    "import importlib.util; assert importlib.util.find_spec('dns') is not None; print('optional HTTP installation passed')",
                ],
                parent,
            ),
            end="",
        )
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(parent / "wheel-venv/bin/python"),
                "--exclude-newer",
                "2026-10-04T00:00:00Z",
                str(wheel) + "[semantic]",
            ],
            parent,
        )
        print(
            run(
                [
                    str(parent / "wheel-venv/bin/python"),
                    "-c",
                    "import importlib.util,sys; from toolsmith.semantic import inspect_model; assert importlib.util.find_spec('tokenizers') is not None; assert importlib.util.find_spec('onnxruntime') is not None; assert 'onnxruntime' not in sys.modules and 'numpy' not in sys.modules; assert importlib.util.find_spec('torch') is None; print('optional semantic installation passed')",
                ],
                parent,
            ),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
