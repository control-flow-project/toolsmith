import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from toolsmith.files import private_directory, private_file, read_descriptor
from toolsmith.result import ToolsmithError, boundary
from toolsmith.semantic.profile import ASSETS, MODEL, PROFILE_ID, REVISION


@dataclass(frozen=True)
class ModelInfo:
    model: str
    revision: str
    profile: str
    verified_bytes: int


def read_assets(directory: Path) -> dict[str, bytes]:
    with private_directory(directory) as selected:
        if set(os.listdir(selected.descriptor)) != set(ASSETS):
            raise ToolsmithError(
                "integrity", "Model directory must contain exactly the pinned assets"
            )
        output: dict[str, bytes] = {}
        for name, (size, digest) in ASSETS.items():
            with private_file(selected, name) as descriptor:
                body = read_descriptor(descriptor, size)
            if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
                raise ToolsmithError(
                    "integrity", "Model assets do not match the pinned MiniLM revision"
                )
            output[name] = body
        return output


@boundary
def inspect_model(directory: Path) -> ModelInfo:
    assets = read_assets(directory)
    return ModelInfo(MODEL, REVISION, PROFILE_ID, sum(len(body) for body in assets.values()))
