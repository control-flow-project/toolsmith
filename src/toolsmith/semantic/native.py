import ctypes
import importlib.metadata
import math
import os
import sys
import weakref
from _thread import allocate_lock
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Protocol, cast

from toolsmith.result import ToolsmithError
from toolsmith.semantic.profile import DIMENSIONS, MAX_TOKENS

RUNTIME_VERSION = "1.30.0"
API_VERSION = 30
API_HEADER_SHA256 = "e035e30c27e74c8c00e0f483e576e12b4067d17f12e9237fd6eff8b346c9b381"
_startup_lock = allocate_lock()
SLOTS = {
    "CreateEnv": 3,
    "DisableTelemetryEvents": 6,
    "CreateSessionFromArray": 8,
    "Run": 9,
    "CreateSessionOptions": 10,
    "SetSessionExecutionMode": 13,
    "DisableMemPattern": 17,
    "SetIntraOpNumThreads": 24,
    "SetInterOpNumThreads": 25,
    "CreateTensorWithDataAsOrtValue": 49,
    "GetTensorMutableData": 51,
    "GetTensorElementType": 60,
    "GetDimensionsCount": 61,
    "GetDimensions": 62,
    "GetTensorTypeAndShape": 65,
    "CreateCpuMemoryInfo": 69,
    "ReleaseEnv": 92,
    "ReleaseStatus": 93,
    "ReleaseMemoryInfo": 94,
    "ReleaseSession": 95,
    "ReleaseValue": 96,
    "ReleaseTensorTypeAndShapeInfo": 99,
    "ReleaseSessionOptions": 100,
    "AddSessionConfigEntry": 130,
}
type ArgumentType = (
    type[ctypes.c_void_p] | type[ctypes.c_int] | type[ctypes.c_size_t] | type[ctypes.c_char_p]
)


class NativeFunction(Protocol):
    restype: object
    argtypes: list[object]

    def __call__(self, *arguments: object) -> object: ...


@dataclass(frozen=True)
class Tensor:
    shape: tuple[int, int, int]
    values: tuple[float, ...]


class Api:
    def __init__(self) -> None:
        if sys.platform != "linux":
            raise ToolsmithError(
                "unavailable", "The selected native semantic runtime requires Linux"
            )
        try:
            distribution = importlib.metadata.distribution("onnxruntime")
        except importlib.metadata.PackageNotFoundError as error:
            raise ToolsmithError(
                "unavailable", "Explicitly install the semantic extra before loading MiniLM"
            ) from error
        if distribution.version != RUNTIME_VERSION:
            raise ToolsmithError(
                "unavailable", "Semantic inference requires the exact pinned ONNX Runtime version"
            )
        library = distribution.locate_file("onnxruntime/capi/libonnxruntime.so." + RUNTIME_VERSION)
        self._library = ctypes.CDLL(str(library))
        get_base = cast(NativeFunction, self._library.OrtGetApiBase)
        get_base.argtypes = []
        get_base.restype = ctypes.c_void_p
        address = get_base()
        if type(address) is not int or address == 0:
            raise ToolsmithError("unavailable", "Native ONNX API base is unavailable")
        base = ctypes.cast(ctypes.c_void_p(address), ctypes.POINTER(ctypes.c_void_p))
        version_function = cast(NativeFunction, ctypes.CFUNCTYPE(ctypes.c_char_p)(base[1]))
        if version_function() != RUNTIME_VERSION.encode():
            raise ToolsmithError("unavailable", "Native ONNX library and pinned metadata differ")
        get_api = cast(NativeFunction, ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_uint32)(base[0]))
        table = get_api(API_VERSION)
        if type(table) is not int or table == 0:
            raise ToolsmithError("unavailable", "Native ONNX API 30 is unavailable")
        self._table = ctypes.cast(ctypes.c_void_p(table), ctypes.POINTER(ctypes.c_void_p))

    def invoke(
        self, name: str, types: tuple[ArgumentType, ...], *arguments: object, release: bool = False
    ) -> None:
        address = self._table[SLOTS[name]]
        if address is None:
            raise ToolsmithError("unavailable", "Required native ONNX API function is unavailable")
        function = cast(
            NativeFunction, ctypes.CFUNCTYPE(None if release else ctypes.c_void_p, *types)(address)
        )
        status = function(*arguments)
        if not release and status is not None:
            self.invoke("ReleaseStatus", (ctypes.c_void_p,), status, release=True)
            raise ToolsmithError("unavailable", "The selected native ONNX operation failed")

    def resource(
        self,
        stack: ExitStack,
        create: str,
        release: str,
        types: tuple[ArgumentType, ...],
        *arguments: object,
    ) -> ctypes.c_void_p:
        output = ctypes.c_void_p()
        self.invoke(create, (*types, ctypes.c_void_p), *arguments, ctypes.byref(output))
        if not output.value:
            raise ToolsmithError("integrity", "Native ONNX operation returned an empty resource")
        stack.callback(self.invoke, release, (ctypes.c_void_p,), output, release=True)
        return output


class NativeSession:
    def __init__(self, model: bytes) -> None:
        self._api = Api()
        self._closed = False
        with ExitStack() as resources:
            with _startup_lock:
                previous = os.environ.get("ORT_DISABLE_TELEMETRY")
                os.environ["ORT_DISABLE_TELEMETRY"] = "1"
                try:
                    env = self._api.resource(
                        resources,
                        "CreateEnv",
                        "ReleaseEnv",
                        (ctypes.c_int, ctypes.c_char_p),
                        4,
                        b"toolsmith",
                    )
                finally:
                    if previous is None:
                        os.environ.pop("ORT_DISABLE_TELEMETRY", None)
                    else:
                        os.environ["ORT_DISABLE_TELEMETRY"] = previous
            self._api.invoke("DisableTelemetryEvents", (ctypes.c_void_p,), env)
            options = self._api.resource(
                resources, "CreateSessionOptions", "ReleaseSessionOptions", ()
            )
            for name, value in (
                ("SetSessionExecutionMode", 0),
                ("SetIntraOpNumThreads", 1),
                ("SetInterOpNumThreads", 1),
            ):
                self._api.invoke(name, (ctypes.c_void_p, ctypes.c_int), options, value)
            self._api.invoke("DisableMemPattern", (ctypes.c_void_p,), options)
            for key in (b"session.intra_op.allow_spinning", b"session.inter_op.allow_spinning"):
                self._api.invoke(
                    "AddSessionConfigEntry",
                    (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p),
                    options,
                    key,
                    b"0",
                )
            self._session = self._api.resource(
                resources,
                "CreateSessionFromArray",
                "ReleaseSession",
                (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p),
                env,
                ctypes.c_char_p(model),
                len(model),
                options,
            )
            self._memory = self._api.resource(
                resources,
                "CreateCpuMemoryInfo",
                "ReleaseMemoryInfo",
                (ctypes.c_int, ctypes.c_int),
                0,
                0,
            )
            self._resources = resources.pop_all()
        self._finalizer = weakref.finalize(self, self._resources.close)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._finalizer()

    def run(self, feed: tuple[tuple[tuple[int, ...], ...], ...]) -> Tensor:
        if self._closed:
            raise ToolsmithError("unavailable", "The explicitly owned encoder has been closed")
        if not isinstance(feed, tuple) or len(feed) != 3:
            raise ToolsmithError(
                "invalid_input", "Native encoder requires three bounded input tensors"
            )
        batch = len(feed[0])
        width = len(feed[0][0]) if batch else 0
        if (
            not 1 <= batch <= 16
            or not 1 <= width <= MAX_TOKENS
            or any(
                len(rows) != batch
                or any(
                    len(row) != width
                    or any(type(value) is not int or not 0 <= value < 2**63 for value in row)
                    for row in rows
                )
                for rows in feed
            )
        ):
            raise ToolsmithError("invalid_input", "Native encoder input tensor bounds differ")
        shape = (ctypes.c_int64 * 2)(batch, width)
        buffers = [
            (ctypes.c_int64 * (batch * width))(*(value for row in rows for value in row))
            for rows in feed
        ]
        with ExitStack() as resources:
            inputs = [
                self._api.resource(
                    resources,
                    "CreateTensorWithDataAsOrtValue",
                    "ReleaseValue",
                    (
                        ctypes.c_void_p,
                        ctypes.c_void_p,
                        ctypes.c_size_t,
                        ctypes.c_void_p,
                        ctypes.c_size_t,
                        ctypes.c_int,
                    ),
                    self._memory,
                    buffer,
                    ctypes.sizeof(buffer),
                    shape,
                    2,
                    7,
                )
                for buffer in buffers
            ]
            names = (ctypes.c_char_p * 3)(b"input_ids", b"token_type_ids", b"attention_mask")
            values = (ctypes.c_void_p * 3)(*(value.value for value in inputs))
            output_names = (ctypes.c_char_p * 1)(b"last_hidden_state")
            output = ctypes.c_void_p()
            self._api.invoke(
                "Run",
                (
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_size_t,
                    ctypes.c_void_p,
                    ctypes.c_size_t,
                    ctypes.c_void_p,
                ),
                self._session,
                None,
                names,
                values,
                3,
                output_names,
                1,
                ctypes.byref(output),
            )
            if not output.value:
                raise ToolsmithError("integrity", "Native encoder returned an empty output tensor")
            resources.callback(
                self._api.invoke, "ReleaseValue", (ctypes.c_void_p,), output, release=True
            )
            information = self._api.resource(
                resources,
                "GetTensorTypeAndShape",
                "ReleaseTensorTypeAndShapeInfo",
                (ctypes.c_void_p,),
                output,
            )
            dimensions = ctypes.c_size_t()
            element_type = ctypes.c_int()
            self._api.invoke(
                "GetDimensionsCount",
                (ctypes.c_void_p, ctypes.c_void_p),
                information,
                ctypes.byref(dimensions),
            )
            self._api.invoke(
                "GetTensorElementType",
                (ctypes.c_void_p, ctypes.c_void_p),
                information,
                ctypes.byref(element_type),
            )
            if dimensions.value != 3 or element_type.value != 1:
                raise ToolsmithError(
                    "integrity", "Native encoder output is not a float32 token tensor"
                )
            actual_shape = (ctypes.c_int64 * 3)()
            self._api.invoke(
                "GetDimensions",
                (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t),
                information,
                actual_shape,
                3,
            )
            if tuple(actual_shape) != (batch, width, DIMENSIONS):
                raise ToolsmithError(
                    "integrity", "Native encoder output shape differs from the bounded inputs"
                )
            data = ctypes.c_void_p()
            self._api.invoke(
                "GetTensorMutableData",
                (ctypes.c_void_p, ctypes.c_void_p),
                output,
                ctypes.byref(data),
            )
            if not data.value:
                raise ToolsmithError("integrity", "Native encoder tensor data is unavailable")
            count = batch * width * DIMENSIONS
            result = tuple(ctypes.cast(data, ctypes.POINTER(ctypes.c_float * count)).contents)
            if not all(math.isfinite(value) for value in result):
                raise ToolsmithError("integrity", "Native encoder returned nonfinite token values")
            return Tensor((batch, width, DIMENSIONS), result)
