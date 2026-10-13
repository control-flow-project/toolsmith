import ctypes
import os
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from toolsmith.result import ToolsmithError
from toolsmith.semantic.native import NativeSession


class FixtureApi:
    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.settings: dict[str, object] = {}

    def invoke(self, name: str, types: object, *arguments: object, release: bool = False) -> None:
        if release:
            self.released.append(name)
        elif name.startswith("Set"):
            self.settings[name] = arguments[1]

    def resource(
        self, stack: ExitStack, create: str, release: str, types: object, *arguments: object
    ) -> ctypes.c_void_p:
        if create == "CreateEnv":
            assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"
        if create == self.fail:
            raise ToolsmithError("unavailable", "Controlled native construction failure")
        self.acquired.append(create)
        stack.callback(self.released.append, release)
        return ctypes.c_void_p(len(self.acquired))


@pytest.mark.parametrize(
    "failure",
    [None, "CreateEnv", "CreateSessionOptions", "CreateSessionFromArray", "CreateCpuMemoryInfo"],
)
def test_native_acquisition_disposes_reverse_order_and_restores_process_environment(
    failure: str | None,
) -> None:
    api = FixtureApi(failure)
    before = dict(os.environ)
    with patch("toolsmith.semantic.native.Api", return_value=api):
        if failure is None:
            session = NativeSession(b"fixture")
            session.close()
            session.close()
            assert api.settings == {
                "SetSessionExecutionMode": 0,
                "SetIntraOpNumThreads": 1,
                "SetInterOpNumThreads": 1,
            }
            with pytest.raises(ToolsmithError):
                session.run(())
        else:
            with pytest.raises(ToolsmithError):
                NativeSession(b"fixture")
    assert dict(os.environ) == before
    releases = {
        "CreateEnv": "ReleaseEnv",
        "CreateSessionOptions": "ReleaseSessionOptions",
        "CreateSessionFromArray": "ReleaseSession",
        "CreateCpuMemoryInfo": "ReleaseMemoryInfo",
    }
    assert api.released == [releases[name] for name in reversed(api.acquired)]


def test_existing_process_opt_out_value_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "operator-value")
    with patch("toolsmith.semantic.native.Api", return_value=FixtureApi()):
        session = NativeSession(b"fixture")
        session.close()
    assert os.environ["ORT_DISABLE_TELEMETRY"] == "operator-value"
