import hashlib
import math
import struct
from dataclasses import dataclass

from toolsmith.result import ToolsmithError
from toolsmith.validation import canonical_json, text

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DIMENSIONS = 384
MAX_TOKENS = 256
OVERLAP_TOKENS = 32
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_CHUNKS = 20_000
MAX_CANDIDATES = 10_000
MAX_SEARCH_CHUNKS = 100_000
ASSETS = {
    "model.onnx": (90_405_214, "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"),
    "tokenizer.json": (466_247, "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"),
}
PROFILE_JSON = canonical_json(
    {
        "model": MODEL,
        "revision": REVISION,
        "backend": "onnx-cpu-float32",
        "assets": ASSETS,
        "dimensions": DIMENSIONS,
        "pooling": "mean-mask-l2",
        "pooling_accumulator": "float64",
        "language": "en",
        "max_tokens": MAX_TOKENS,
        "overlap_tokens": OVERLAP_TOKENS,
        "chunking": "complete-offsets-v1",
    }
).decode()
PROFILE_ID = hashlib.sha256(PROFILE_JSON.encode()).hexdigest()


@dataclass(frozen=True)
class Source:
    reference: str
    text: str
    language: str = "en"


@dataclass(frozen=True)
class Candidate:
    reference: str
    digest: str


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    start: int
    end: int
    digest: str
    vector: bytes


@dataclass(frozen=True)
class Prepared:
    reference: str
    digest: str
    characters: int
    chunks: tuple[Chunk, ...]
    profile: str = PROFILE_ID


def fingerprint(body: str) -> str:
    return hashlib.sha256(text(body, MAX_SOURCE_BYTES, "Source text").encode()).hexdigest()


def validate_source(source: Source) -> None:
    if not isinstance(source, Source) or source.language != "en":
        raise ToolsmithError("invalid_input", "Supply an explicitly English semantic source")
    source_reference(source.reference)
    text(source.text, MAX_SOURCE_BYTES, "Source text")


def source_reference(value: object) -> str:
    reference = text(value, 200, "Source reference")
    if any(ord(character) < 32 or ord(character) == 127 for character in reference):
        raise ToolsmithError("invalid_input", "References cannot contain control characters")
    return reference


def pack_vector(values: tuple[float, ...]) -> bytes:
    if (
        not isinstance(values, tuple)
        or len(values) != DIMENSIONS
        or any(type(value) not in {float, int} or not math.isfinite(value) for value in values)
        or abs(math.sqrt(math.fsum(value * value for value in values)) - 1) > 0.0001
    ):
        raise ToolsmithError("integrity", "Vectors require 384 finite L2-normalized values")
    encoded = struct.pack("<384f", *values)
    unpack_vector(encoded)
    return encoded


def unpack_vector(encoded: object) -> tuple[float, ...]:
    if not isinstance(encoded, bytes) or len(encoded) != DIMENSIONS * 4:
        raise ToolsmithError("integrity", "Invalid vector byte length or storage type")
    values: tuple[float, ...] = struct.unpack("<384f", encoded)
    if (
        not all(math.isfinite(value) for value in values)
        or abs(math.sqrt(math.fsum(value * value for value in values)) - 1) > 0.0001
    ):
        raise ToolsmithError("integrity", "Stored vector is nonfinite or not L2 normalized")
    return values
