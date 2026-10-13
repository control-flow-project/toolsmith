import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from toolsmith.result import Failure, ToolsmithError, unwrap
from toolsmith.semantic import inspect_model, load_model
from toolsmith.semantic.model import MiniLM


@pytest.fixture
def assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "model"
    directory.mkdir(mode=0o700)
    contents = {"model.onnx": b"pinned fixture", "tokenizer.json": b"{}"}
    for name, body in contents.items():
        (directory / name).write_bytes(body)
        (directory / name).chmod(0o600)
    monkeypatch.setattr(
        "toolsmith.semantic.assets.ASSETS",
        {name: (len(body), hashlib.sha256(body).hexdigest()) for name, body in contents.items()},
    )
    return directory


def test_asset_check_is_offline_and_imports_no_optional_dependency(assets: Path) -> None:
    with patch("toolsmith.semantic.model.importlib.import_module") as imported:
        assert unwrap(inspect_model(assets)).verified_bytes == len(b"pinned fixture{}")
        imported.assert_not_called()


@pytest.mark.parametrize("change", ["bytes", "mode", "symlink", "unknown", "directory", "pipe"])
def test_unsafe_or_changed_assets_fail_before_loading(assets: Path, change: str) -> None:
    import os

    if change == "bytes":
        (assets / "model.onnx").write_bytes(b"different")
    elif change == "mode":
        (assets / "model.onnx").chmod(0o644)
    elif change == "symlink":
        (assets / "model.onnx").rename(assets.parent / "outside")
        (assets / "model.onnx").symlink_to(assets.parent / "outside")
    elif change == "unknown":
        (assets / "unreviewed.py").write_text("raise RuntimeError('not executed')")
    elif change == "directory":
        assets.chmod(0o755)
    else:
        (assets / "model.onnx").unlink()
        os.mkfifo(assets / "model.onnx", 0o600)
    with patch("toolsmith.semantic.model.importlib.import_module") as imported:
        assert isinstance(load_model(assets), Failure)
        imported.assert_not_called()


def test_missing_optional_dependency_is_an_expected_error(assets: Path) -> None:
    with patch(
        "toolsmith.semantic.model.importlib.import_module", side_effect=ImportError("absent")
    ):
        result = load_model(assets)
        assert isinstance(result, Failure) and result.code == "unavailable"
        assert str(assets) not in result.message


def test_read_only_private_assets_can_be_verified_without_write_access(assets: Path) -> None:
    for path in assets.iterdir():
        path.chmod(0o400)
    assert unwrap(inspect_model(assets)).verified_bytes > 0


def test_model_load_uses_verified_bytes_without_python_runtime_wrapper(assets: Path) -> None:
    tokenizer = SimpleNamespace(no_truncation=lambda: None, no_padding=lambda: None)
    calls: list[bytes] = []

    def session(model: bytes) -> object:
        assert model == b"pinned fixture"
        calls.append(model)
        return SimpleNamespace(close=lambda: None)

    modules = {
        "tokenizers": SimpleNamespace(Tokenizer=SimpleNamespace(from_str=lambda body: tokenizer)),
    }
    with (
        patch("toolsmith.semantic.model.NativeSession", side_effect=session),
        patch("toolsmith.semantic.model.importlib.import_module", side_effect=modules.__getitem__),
        unwrap(load_model(assets)) as model,
    ):
        assert isinstance(model, MiniLM)
    assert calls == [b"pinned fixture"]


def test_encoder_rejects_oversize_batches_without_inference() -> None:
    tokenizer = SimpleNamespace(
        encode=lambda text, add_special_tokens=True: SimpleNamespace(
            ids=list(range(257)), type_ids=[0] * 257
        )
    )
    model = MiniLM(tokenizer, SimpleNamespace())
    for texts in ((), ("some words",), tuple(["words"] * 17)):
        with pytest.raises(ToolsmithError):
            model.encode(texts)
