from typing import Protocol

from toolsmith.result import ToolsmithError, boundary
from toolsmith.semantic.profile import (
    MAX_CHUNKS,
    MAX_TOKENS,
    OVERLAP_TOKENS,
    Chunk,
    Prepared,
    Source,
    fingerprint,
    pack_vector,
    validate_source,
)
from toolsmith.validation import text


class Encoder(Protocol):
    def offsets(self, text: str) -> tuple[tuple[int, int], ...]: ...
    def tokens(self, text: str) -> int: ...
    def encode(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


def source_spans(body: str, encoder: Encoder) -> tuple[tuple[int, int], ...]:
    offsets = encoder.offsets(body)
    if not isinstance(offsets, tuple) or not offsets or len(offsets) > len(body):
        raise ToolsmithError("integrity", "Tokenizer must supply bounded complete offsets")
    previous_start = -1
    previous_end = -1
    for pair in offsets:
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or type(pair[0]) is not int
            or type(pair[1]) is not int
            or not 0 <= pair[0] < pair[1] <= len(body)
            or pair[0] < previous_start
            or pair[1] <= previous_end
        ):
            raise ToolsmithError("integrity", "Tokenizer offsets must be ordered source spans")
        previous_start, previous_end = pair
    spans: list[tuple[int, int]] = []
    position, start = 0, 0
    while position < len(offsets):
        target = min(position + MAX_TOKENS - 2, len(offsets))
        end = len(body) if target == len(offsets) else offsets[target][0]
        while target > position and encoder.tokens(body[start:end]) > MAX_TOKENS:
            target -= 1
            end = offsets[target][0]
        count = encoder.tokens(body[start:end])
        if type(count) is not int or not 2 < count <= MAX_TOKENS or end <= start:
            raise ToolsmithError("integrity", "Cannot form a complete bounded token chunk")
        if spans and end <= spans[-1][1]:
            raise ToolsmithError("integrity", "Tokenizer chunking did not make progress")
        spans.append((start, end))
        if len(spans) > MAX_CHUNKS:
            raise ToolsmithError("limit", "Source exceeds the semantic chunk limit")
        if end == len(body):
            break
        position = max(position + 1, target - OVERLAP_TOKENS)
        start = offsets[position][0]
        if start > end:
            raise ToolsmithError("integrity", "Chunking would omit source characters")
    if not spans or spans[0][0] != 0 or spans[-1][1] != len(body):
        raise ToolsmithError("integrity", "Semantic chunks do not cover the complete source")
    return tuple(spans)


@boundary
def prepare_embedding(source: Source, encoder: Encoder) -> Prepared:
    validate_source(source)
    try:
        spans = source_spans(source.text, encoder)
        chunks: list[Chunk] = []
        for offset in range(0, len(spans), 16):
            batch = spans[offset : offset + 16]
            vectors = encoder.encode(tuple(source.text[start:end] for start, end in batch))
            if not isinstance(vectors, tuple) or len(vectors) != len(batch):
                raise ToolsmithError("integrity", "Encoder batch omitted source chunks")
            for ordinal, ((start, end), values) in enumerate(
                zip(batch, vectors, strict=True), offset
            ):
                chunks.append(
                    Chunk(
                        ordinal,
                        start,
                        end,
                        fingerprint(source.text[start:end]),
                        pack_vector(values),
                    )
                )
        return Prepared(source.reference, fingerprint(source.text), len(source.text), tuple(chunks))
    except (ValueError, RuntimeError) as error:
        raise ToolsmithError(
            "unavailable", "Selected encoder could not encode the complete source"
        ) from error


@boundary
def encode_query(query: str, encoder: Encoder) -> bytes:
    text(query, 16_384, "Semantic query")
    validate_source(Source("query", query))
    try:
        count = encoder.tokens(query)
        if type(count) is not int or count <= 2:
            raise ToolsmithError("invalid_input", "Query requires encodable text")
        if count > MAX_TOKENS:
            raise ToolsmithError("limit", "Query exceeds 256 tokens; it was not truncated")
        vectors = encoder.encode((query,))
        if not isinstance(vectors, tuple) or len(vectors) != 1:
            raise ToolsmithError("integrity", "Encoder query batch has an invalid shape")
        return pack_vector(vectors[0])
    except (ValueError, RuntimeError) as error:
        raise ToolsmithError(
            "unavailable", "Selected encoder could not encode the query"
        ) from error
