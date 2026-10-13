import importlib
import math
from pathlib import Path
from types import TracebackType
from typing import Protocol, cast

from toolsmith.result import ToolsmithError, boundary
from toolsmith.semantic.assets import read_assets
from toolsmith.semantic.native import NativeSession, Tensor
from toolsmith.semantic.profile import DIMENSIONS, MAX_TOKENS, Source, validate_source


class Encoding(Protocol):
    ids: list[int]
    type_ids: list[int]
    offsets: list[tuple[int, int]]


class Tokenizer(Protocol):
    def encode(self, sequence: str, add_special_tokens: bool = True) -> Encoding: ...
    def no_truncation(self) -> None: ...
    def no_padding(self) -> None: ...


class TokenizerFactory(Protocol):
    def from_str(self, content: str) -> Tokenizer: ...


class Session(Protocol):
    def run(self, feed: tuple[tuple[tuple[int, ...], ...], ...]) -> Tensor: ...
    def close(self) -> None: ...


class MiniLM:
    def __init__(self, tokenizer: Tokenizer, session: Session) -> None:
        self._tokenizer = tokenizer
        self._session = session
        self._closed = False

    def __enter__(self) -> "MiniLM":
        if self._closed:
            raise ToolsmithError("unavailable", "The explicitly owned encoder has been closed")
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._session.close()

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        validate_source(Source("tokens", text))
        return tuple(self._tokenizer.encode(text, add_special_tokens=False).offsets)

    def tokens(self, text: str) -> int:
        validate_source(Source("tokens", text))
        return len(self._tokenizer.encode(text).ids)

    def encode(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if self._closed:
            raise ToolsmithError("unavailable", "The explicitly owned encoder has been closed")
        if not isinstance(texts, tuple) or not 1 <= len(texts) <= 16:
            raise ToolsmithError("invalid_input", "Encoding requires one to sixteen text chunks")
        encoded: list[Encoding] = []
        for text in texts:
            validate_source(Source("encode", text))
            item = self._tokenizer.encode(text)
            if (
                len(item.ids) > MAX_TOKENS
                or len(item.ids) <= 2
                or len(item.ids) != len(item.type_ids)
            ):
                raise ToolsmithError("limit", "Encoding exceeds token bounds; no truncation")
            encoded.append(item)
        width = max(len(item.ids) for item in encoded)
        feed = (
            tuple(tuple(item.ids + [0] * (width - len(item.ids))) for item in encoded),
            tuple(tuple(item.type_ids + [0] * (width - len(item.ids))) for item in encoded),
            tuple(tuple([1] * len(item.ids) + [0] * (width - len(item.ids))) for item in encoded),
        )
        tensor = self._session.run(feed)
        if (
            tensor.shape != (len(texts), width, DIMENSIONS)
            or len(tensor.values) != len(texts) * width * DIMENSIONS
        ):
            raise ToolsmithError("integrity", "MiniLM returned an invalid token tensor shape")
        vectors: list[tuple[float, ...]] = []
        for document, item in enumerate(encoded):
            offset = document * width * DIMENSIONS
            pooled = tuple(
                math.fsum(
                    tensor.values[offset + token * DIMENSIONS + axis]
                    for token in range(len(item.ids))
                )
                / len(item.ids)
                for axis in range(DIMENSIONS)
            )
            norm = math.sqrt(math.fsum(value * value for value in pooled))
            if not math.isfinite(norm) or norm <= 0:
                raise ToolsmithError("integrity", "MiniLM returned an invalid pooled vector")
            vectors.append(tuple(value / norm for value in pooled))
        return tuple(vectors)


@boundary
def load_model(directory: Path) -> MiniLM:
    assets = read_assets(directory)
    try:
        factory = cast(TokenizerFactory, importlib.import_module("tokenizers").Tokenizer)
        tokenizer = factory.from_str(assets["tokenizer.json"].decode("utf-8"))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        return MiniLM(tokenizer, NativeSession(assets["model.onnx"]))
    except ImportError as error:
        raise ToolsmithError(
            "unavailable", "Explicitly install the optional semantic extra before loading MiniLM"
        ) from error
    except (OSError, ValueError, RuntimeError) as error:
        raise ToolsmithError(
            "unavailable", "Verified local MiniLM assets could not be loaded"
        ) from error
