import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_product_has_no_process_server_thread_or_domain_owner() -> None:
    forbidden_imports = {
        "subprocess",
        "multiprocessing",
        "threading",
        "concurrent",
        "selenium",
        "playwright",
        "flask",
        "fastapi",
        "uvicorn",
    }
    forbidden_calls = {
        "listen",
        "serve_forever",
        "start_server",
        "system",
        "popen",
        "fork",
        "forkpty",
        "posix_spawn",
        "posix_spawnp",
        "execv",
        "execve",
        "execl",
        "execlp",
        "execvp",
        "spawn",
        "create_subprocess_exec",
        "create_subprocess_shell",
        "to_thread",
        "run_in_executor",
        "set_default_executor",
    }
    violations = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for imported in node.names:
                    if (
                        imported.name.split(".")[0] in forbidden_imports
                        or imported.name == "http.server"
                    ):
                        violations.append(path.name + ":" + imported.name)
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and (node.module.split(".")[0] in forbidden_imports or node.module == "http.server")
            ):
                violations.append(path.name + ":" + node.module)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_calls
            ):
                violations.append(path.name + ":" + node.func.attr)
            if isinstance(node, ast.Name) and node.id == "Any":
                violations.append(path.name + ":Any")
        assert len(path.read_text().splitlines()) <= 600, path.name
    assert violations == []
    assert not list((ROOT / "src").rglob("SKILL.md"))


def test_dependencies_are_optional_and_distribution_is_mit_licensed() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["project"]["dependencies"] == []
    assert set(config["project"]["optional-dependencies"]) == {"http", "pdf", "semantic"}
    assert not any(value.startswith("Private ::") for value in config["project"]["classifiers"])
    assert config["project"]["scripts"] == {"toolsmith": "toolsmith.cli:main"}
    assert config["project"]["license"] == "MIT"
    assert config["project"]["license-files"] == ["LICENSE"]
    license_text = (ROOT / "LICENSE").read_text()
    assert license_text.startswith("MIT License\n\nCopyright (c) 2026 Jeswin P Kumar\n")


def test_repository_has_no_github_actions_workflows() -> None:
    directory = ROOT / ".github/workflows"
    assert not list(directory.glob("*.yml"))
    assert not list(directory.glob("*.yaml"))


def test_semantic_core_has_no_store_runtime_or_domain_dependency() -> None:
    forbidden = {
        "torch",
        "sentence_transformers",
        "transformers",
        "badbets_research",
        "crossfire",
        "fleetd",
    }
    violations = []
    for path in (ROOT / "src/toolsmith/semantic").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.split(".")[0] in forbidden:
                    violations.append(node.module)
                if path.name != "store.py" and node.module.startswith("toolsmith.storage"):
                    violations.append(node.module)
    assert violations == []


def test_generic_capabilities_do_not_import_archive_or_consumers() -> None:
    selected = [
        ROOT / "src/toolsmith/files.py",
        ROOT / "src/toolsmith/filesystem.py",
        ROOT / "src/toolsmith/archives.py",
        ROOT / "src/toolsmith/journal.py",
        ROOT / "src/toolsmith/sqlite.py",
    ]
    selected += list((ROOT / "src/toolsmith/readers").glob("*.py"))
    selected += list((ROOT / "src/toolsmith/lexical").glob("*.py"))
    selected += [
        ROOT / "src/toolsmith/acquisition" / name
        for name in (
            "client.py",
            "batch.py",
            "budgets.py",
            "budget_import.py",
            "config.py",
            "urls.py",
            "transport.py",
        )
    ]
    forbidden = (
        "toolsmith.storage",
        "toolsmith.operations",
        "badbets_research",
        "agreement_tools",
        "crossfire",
        "fleetd",
    )
    violations: list[str] = []
    for path in selected:
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith(forbidden)
            ):
                violations.append(path.name + ":" + node.module)
    assert violations == []


def test_archive_uses_current_index_ports_not_superseded_indexes() -> None:
    from toolsmith.storage import models as archive_models

    assert not hasattr(archive_models, "Document")
    assert not hasattr(archive_models, "TextPart")
    assert not (ROOT / "src/toolsmith/storage/index.py").exists()
    schema = (ROOT / "src/toolsmith/storage/schema.sql").read_text()
    assert "CREATE TABLE chunk" not in schema and "chunk_search" not in schema
    text_writer = (ROOT / "src/toolsmith/storage/text.py").read_text()
    semantic_store = (ROOT / "src/toolsmith/semantic/store.py").read_text()
    assert "embedding_document" not in text_writer and "embedding_document" not in semantic_store
    assert "indexed_digest" not in semantic_store
    for family in ("lexical", "semantic"):
        index_schema = (ROOT / "src/toolsmith" / family / "schema.sql").read_text()
        assert "IF NOT EXISTS" not in index_schema
