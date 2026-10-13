from dataclasses import replace

import pytest
from semantic_support import FixtureEncoder

from toolsmith.result import Failure, ToolsmithError, unwrap
from toolsmith.semantic import Source, encode_query, prepare_embedding
from toolsmith.semantic.profile import fingerprint, pack_vector, unpack_vector


@pytest.mark.parametrize("count", [1, 254, 255, 900, 3600])
def test_complete_exact_coverage_without_token_truncation(count: int) -> None:
    body = "  " + " \n".join("évidence" + str(index) for index in range(count)) + "\n  "
    prepared = unwrap(prepare_embedding(Source("document:page-7", body), FixtureEncoder()))
    covered = bytearray(len(body))
    for ordinal, chunk in enumerate(prepared.chunks):
        assert chunk.ordinal == ordinal
        assert chunk.digest == fingerprint(body[chunk.start : chunk.end])
        assert FixtureEncoder().tokens(body[chunk.start : chunk.end]) <= 256
        covered[chunk.start : chunk.end] = b"\x01" * (chunk.end - chunk.start)
        assert len(unpack_vector(chunk.vector)) == 384
    assert all(covered), "Every original source character remains covered"


@pytest.mark.parametrize(
    "source",
    [
        Source("ref", " "),
        Source("ref", "text", "fr"),
        Source("bad\nref", "text"),
        Source("ref", "\ud800"),
        Source("ref", "a" * (4 * 1024 * 1024 + 1)),
    ],
)
def test_source_boundary_rejects_unsupported_or_unbounded_input(source: Source) -> None:
    assert isinstance(prepare_embedding(source, FixtureEncoder()), Failure)


def test_query_ceiling_is_an_explicit_error_not_truncation() -> None:
    assert len(unwrap(encode_query("word " * 254, FixtureEncoder()))) == 1536
    failed = encode_query("word " * 255, FixtureEncoder())
    assert isinstance(failed, Failure) and failed.code == "limit"


@pytest.mark.parametrize(
    "values",
    [
        (),
        tuple([0.0] * 384),
        tuple([float("nan")] * 384),
        tuple([float("inf")] * 384),
        tuple([1.0] * 384),
    ],
)
def test_nonfinite_shape_and_nonunit_vectors_are_rejected(values: tuple[float, ...]) -> None:
    with pytest.raises(ToolsmithError):
        pack_vector(values)


@pytest.mark.parametrize("encoded", [b"", bytes(1536), "not bytes"])
def test_invalid_persistent_vector_encoding(encoded: object) -> None:
    with pytest.raises(ToolsmithError):
        unpack_vector(encoded)


def test_encoder_cannot_omit_chunks_or_return_unordered_offsets() -> None:
    class Missing(FixtureEncoder):
        def encode(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            return ()

    class Unordered(FixtureEncoder):
        def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
            return ((3, 4), (0, 2))

    class WrongTokens(FixtureEncoder):
        def tokens(self, text: str) -> int:
            return 1000

    for encoder in (Missing(), Unordered(), WrongTokens()):
        assert isinstance(prepare_embedding(Source("ref", "some words"), encoder), Failure)


def test_prepared_identity_binds_source_and_profile() -> None:
    prepared = unwrap(prepare_embedding(Source("ref", "some words"), FixtureEncoder()))
    assert prepared.digest == fingerprint("some words")
    assert replace(prepared, profile="other").profile != prepared.profile
