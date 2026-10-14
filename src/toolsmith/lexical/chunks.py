from collections.abc import Iterator

CHUNK_CHARACTERS = 1200
CHUNK_OVERLAP = 160


def text_chunks(content: str) -> Iterator[tuple[int, int, str]]:
    for offset in range(0, len(content), CHUNK_CHARACTERS - CHUNK_OVERLAP):
        end = min(len(content), offset + CHUNK_CHARACTERS)
        yield offset, end, content[offset:end]
        if end == len(content):
            break
