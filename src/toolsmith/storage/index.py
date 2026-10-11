from collections.abc import Iterator

from toolsmith.storage.database import Store

CHUNK_CHARACTERS = 1200
CHUNK_OVERLAP = 160


def text_chunks(content: str) -> Iterator[tuple[int, int, str]]:
    for offset in range(0, len(content), CHUNK_CHARACTERS - CHUNK_OVERLAP):
        end = min(len(content), offset + CHUNK_CHARACTERS)
        yield offset, end, content[offset:end]
        if end == len(content):
            break


def index_part(store: Store, part_id: int, title: str, content: str) -> None:
    for offset, end, chunk in text_chunks(content):
        cursor = store.connection.execute(
            "INSERT INTO chunk (part_id, start_offset, end_offset, text) VALUES (?, ?, ?, ?)",
            (part_id, offset, end, chunk),
        )
        store.connection.execute(
            "INSERT INTO chunk_search (rowid, text, title) VALUES (?, ?, ?)",
            (cursor.lastrowid, chunk, title),
        )
