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
from toolsmith import lexical
from toolsmith.acquisition.budgets import BudgetPolicy, inspect_budget, reserve_budget, settle_budget
from toolsmith.acquisition.configuration import check_budget, configure_budget, inspect_configuration
from toolsmith.files import replace_bytes
from toolsmith.readers import inspect_html
from toolsmith.readers import decode_table, project_table
from toolsmith.journal import append_record, read_journal
import sqlite3
import hashlib
from contextlib import closing
assert Path(toolsmith.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert importlib.util.find_spec('dns') is None
assert importlib.util.find_spec('onnxruntime') is None
assert importlib.util.find_spec('tokenizers') is None
from toolsmith.semantic import Scope, Source, encode_query, initialize_index, inspect_model
assert 'onnxruntime' not in sys.modules and 'numpy' not in sys.modules
assert importlib.metadata.version('ctlflow-toolsmith') == '0.5.0'
assert importlib.util.find_spec('aiohttp') is None
assert importlib.util.find_spec('pypdfium2') is None
from toolsmith.readers import read_xml, read_json_lines, read_pdf
assert unwrap(read_xml(b'<root><value>one</value></root>')).root.name == 'root'
assert len(unwrap(read_json_lines(b'{"id":1}\\n{"id":2}\\n'))) == 2
assert isinstance(read_pdf(b'%PDF-1.7\\n'), Failure)
assert 'pypdfium2' not in sys.modules
metadata = importlib.metadata.metadata('ctlflow-toolsmith')
assert metadata['License-Expression'] == 'MIT'
assert metadata.get_all('License-File') == ['LICENSE']
assert not any(value.startswith('Private ::') for value in metadata.get_all('Classifier', []))
assert set(parent.iterdir()) == before
assert unwrap(read_html(b'<main>Meaningful text</main>')).parts[0].text == 'Meaningful text'
assert len(unwrap(read_feed(b'<rss><channel><item><title>A</title><link>https://example.com/a</link></item></channel></rss>', 'https://example.com/feed')).entries) == 1
assert unwrap(read_feed(b'<feed xmlns="http://www.w3.org/2005/Atom"><link rel="next" href="?page=2"/></feed>', 'https://example.com/feed')).next_url == 'https://example.com/feed?page=2'
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
with closing(sqlite3.connect(':memory:')) as connection:
    connection.execute('PRAGMA foreign_keys = ON')
    unwrap(lexical.initialize_index(connection))
    source = lexical.Source('source', 'Restricted Payments mean dividends')
    unwrap(lexical.index_source(connection, source, expected_digest=None))
    hits = unwrap(lexical.search(connection, '"Restricted Payments"', lexical.Scope('lexical_document')))
    assert len(hits.hits) == 1
    matching = unwrap(lexical.matching_scope(connection, 'Restricted'))
    assert unwrap(lexical.search(connection, 'Payments', matching)).hits[0].reference == 'source'
    assert unwrap(lexical.indexed_scope(connection))
settings = parent / 'acquisition'
selected = BudgetPolicy('publisher', 60, 10, 10000, 10, 10000)
configuration = unwrap(configure_budget(settings, (selected,), {'hosts':['example.com']}))
assert unwrap(inspect_configuration(settings)) == configuration
held = unwrap(reserve_budget(settings, selected, 'assignment', 100, expected_configuration_digest=configuration.digest))
unwrap(settle_budget(settings, selected, held, 40))
assert unwrap(inspect_budget(settings, selected, 'assignment')).task_bytes == 40
before_audit = (settings / 'budget.json').read_bytes()
assert unwrap(check_budget(settings, (selected,))) == 0
assert (settings / 'budget.json').read_bytes() == before_audit
assert unwrap(inspect_html(b'<main>Public text</main><input type="password">')).password_controls
linked = unwrap(inspect_html(b'<nav><a href="/section">Section</a></nav><main data-unused="' + b'x' * 20000 + b'"><a href="/article">Article</a></main>'))
assert tuple(link.target for link in linked.links) == ('/section', '/article')
assert linked.links[1].label == 'Article' and not linked.links[1].label_truncated
assert unwrap(replace_bytes(parent / 'explicit-output.txt', b'private output')) == 14
assert not (parent / '.lock').exists()
assert unwrap(project_table(unwrap(decode_table(b'Name,Value\\nA,10\\n')), ('Value',), {'Name':'A'})).matched == 1
journal = parent / 'journal'
journal.mkdir(mode=0o700)
record = unwrap(append_record(journal, {'generic':'event'}))
assert unwrap(read_journal(journal)) == (record,)
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


def check_license(metadata: str, license_text: str) -> None:
    assert "License-Expression: MIT\n" in metadata
    assert "License-File: LICENSE\n" in metadata
    assert "Classifier: Private ::" not in metadata
    assert license_text == (ROOT / "LICENSE").read_text()


def check_archives(wheel: Path, source: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "toolsmith/storage/schema.sql" in names
        assert "toolsmith/semantic/schema.sql" in names
        assert "toolsmith/lexical/schema.sql" in names
        assert "toolsmith/py.typed" in names
        native_suffixes = ("/_vec1.so", "/_vec1.dylib", "/_vec1.dll")
        assert sum(name.endswith(native_suffixes) for name in names) == 1
        license_path = next(name for name in names if name.endswith("/licenses/LICENSE"))
        assert not any(name.startswith(("tests/", "scripts/", "docs/")) for name in names)
        metadata = archive.read(next(name for name in names if name.endswith("/METADATA"))).decode()
        check_license(metadata, archive.read(license_path).decode())
        assert all(
            any("extra == '" + name + "'" in line for name in ("http", "pdf", "semantic"))
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist:")
        )
    with tarfile.open(source, "r:gz") as archive:
        source_names = archive.getnames()
        metadata_file = archive.extractfile(
            next(name for name in source_names if name.endswith("/PKG-INFO"))
        )
        license_file = archive.extractfile(
            next(name for name in source_names if name.endswith("/LICENSE"))
        )
        assert metadata_file is not None and license_file is not None
        with metadata_file, license_file:
            check_license(metadata_file.read().decode(), license_file.read().decode())
        assert any(name.endswith("/tests/test_http.py") for name in source_names)
        assert any(name.endswith("/docs/specification.md") for name in source_names)
        assert any(name.endswith("/src/toolsmith/storage/schema.sql") for name in source_names)
        for required in (
            "/hatch_build.py",
            "/vendor/sqlite/vec1.c",
            "/vendor/sqlite/sqlite3.h",
            "/vendor/sqlite/sqlite3ext.h",
            "/vendor/sqlite/README.md",
        ):
            assert any(name.endswith(required) for name in source_names), required
        assert not any(name.endswith((".so", ".dll", ".dylib", ".o")) for name in source_names)
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
    wheels = list((ROOT / "dist").glob("ctlflow_toolsmith-0.5.0-py3-none-*.whl"))
    if len(wheels) != 1 or wheels[0].name.endswith("-any.whl"):
        raise RuntimeError("Expected one platform-tagged native wheel")
    wheel = wheels[0]
    source = ROOT / "dist/ctlflow_toolsmith-0.5.0.tar.gz"
    check_archives(wheel, source)
    uv = os.environ.get("TOOLSMITH_UV") or shutil.which("uv")
    if uv is None:
        raise RuntimeError("Installed-package verification requires the existing uv executable")
    interpreter = os.environ.get("TOOLSMITH_PYTHON", sys.executable)
    with tempfile.TemporaryDirectory(prefix="toolsmith-installed-") as directory:
        parent = Path(directory)
        constraints = parent / "security-constraints.txt"
        constraints.write_text("certifi==2026.10.19\nfilelock==4.2.1\n")
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
                    "2026-10-17T00:00:00Z",
                    "--exclude-newer-package",
                    "certifi=2026-10-25T00:00:00Z",
                    "--exclude-newer-package",
                    "filelock=2026-10-25T00:00:00Z",
                    "--constraint",
                    str(constraints),
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
            run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--exclude-newer",
                    "2026-10-17T00:00:00Z",
                    "--exclude-newer-package",
                    "certifi=2026-10-25T00:00:00Z",
                    "--exclude-newer-package",
                    "filelock=2026-10-25T00:00:00Z",
                    "--constraint",
                    str(constraints),
                    str(artifact) + "[http,pdf]",
                ],
                parent,
            )
            print(run([str(python), str(ROOT / "scripts/accept_primitives.py")], workspace), end="")
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
                        "2026-10-17T00:00:00Z",
                        "--exclude-newer-package",
                        "certifi=2026-10-25T00:00:00Z",
                        "--exclude-newer-package",
                        "filelock=2026-10-25T00:00:00Z",
                        "--constraint",
                        str(constraints),
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
                "2026-10-17T00:00:00Z",
                "--exclude-newer-package",
                "certifi=2026-10-25T00:00:00Z",
                "--exclude-newer-package",
                "filelock=2026-10-25T00:00:00Z",
                "--constraint",
                str(constraints),
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
                "2026-10-17T00:00:00Z",
                "--exclude-newer-package",
                "certifi=2026-10-25T00:00:00Z",
                "--exclude-newer-package",
                "filelock=2026-10-25T00:00:00Z",
                "--constraint",
                str(constraints),
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
