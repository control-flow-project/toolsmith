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
        "asyncio",
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
    assert set(config["project"]["optional-dependencies"]) == {"http", "semantic"}
    assert not any(value.startswith("Private ::") for value in config["project"]["classifiers"])
    assert config["project"]["scripts"] == {"toolsmith": "toolsmith.cli:main"}
    assert config["project"]["license"] == "MIT"
    assert config["project"]["license-files"] == ["LICENSE"]
    license_text = (ROOT / "LICENSE").read_text()
    assert license_text.startswith("MIT License\n\nCopyright (c) 2026 Jeswin P Kumar\n")


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
