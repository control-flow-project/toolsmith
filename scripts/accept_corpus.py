import argparse
import hashlib
import json
import os
import resource
import sqlite3
import struct
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from verify import require_limits

from toolsmith.result import unwrap
from toolsmith.scopes import Scope
from toolsmith.semantic import initialize_index, search_embeddings
from toolsmith.semantic.profile import PROFILE_ID, PROFILE_JSON, unpack_vector


def main() -> int:
    require_limits()
    parser = argparse.ArgumentParser(
        description="Synthetic full-corpus SQLite capacity acceptance; not embedding-quality certification"
    )
    parser.add_argument("--entries", type=int, default=1_000_000)
    options = parser.parse_args()
    if options.entries < 1_000_000:
        raise ValueError("Capacity acceptance requires at least one million entries")
    text = "Synthetic capacity record"
    digest = hashlib.sha256(text.encode()).hexdigest()
    ordinary = struct.pack("<384f", 0.0, 1.0, *([0.0] * 382))
    target = struct.pack("<384f", 1.0, *([0.0] * 383))
    started = time.perf_counter()
    threads = len(os.listdir("/proc/self/task"))
    with tempfile.TemporaryDirectory(prefix="toolsmith-million-") as temporary:
        database = Path(temporary) / "corpus.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA cache_size = -65536")
            unwrap(initialize_index(connection))
            with connection:
                connection.execute(
                    "CREATE TABLE entry (reference TEXT PRIMARY KEY, text_digest TEXT NOT NULL, ordinal INTEGER NOT NULL UNIQUE)"
                )
                connection.execute(
                    "INSERT INTO embedding_profile VALUES (?, ?)", (PROFILE_ID, PROFILE_JSON)
                )
                connection.executemany(
                    "INSERT INTO entry VALUES (?, ?, ?)",
                    ((f"entry:{number:07}", digest, number) for number in range(options.entries)),
                )
                connection.execute(
                    "INSERT INTO embedding_document SELECT reference, ?, text_digest, ?, 1, '2026-10-17T00:00:00Z' FROM entry",
                    (PROFILE_ID, len(text)),
                )
                connection.execute(
                    "INSERT INTO embedding_chunk (id, reference, ordinal, start_offset, end_offset, text_digest) SELECT ordinal + 1, reference, 0, 0, ?, text_digest FROM entry",
                    (len(text),),
                )
                connection.execute(
                    "INSERT INTO embedding_vector(rowid, vector, chunk_id) SELECT id, CASE WHEN id = ? THEN ? ELSE ? END, id FROM embedding_chunk",
                    (options.entries, target, ordinary),
                )
                connection.execute(
                    "CREATE VIEW last_entries AS SELECT reference, text_digest FROM entry WHERE ordinal >= "
                    + str(options.entries - 100)
                )
            built = time.perf_counter() - started
            measurements = []
            for label, scope in (
                ("full-corpus-first", Scope("entry")),
                ("full-corpus-repeat", Scope("entry")),
                ("filtered-last-100", Scope("last_entries")),
            ):
                beginning = time.perf_counter()
                with patch(
                    "toolsmith.semantic.index.unpack_vector", wraps=unpack_vector
                ) as decoded:
                    report = unwrap(search_embeddings(connection, target, scope, 20))
                elapsed = time.perf_counter() - beginning
                if (
                    report.hits[0].reference != f"entry:{options.entries - 1:07}"
                    or report.hits[0].score != 1.0
                ):
                    raise RuntimeError("The strongest match beyond the former cutoff was lost")
                expected = 100 if label.startswith("filtered") else options.entries
                if report.indexed != expected or len(report.hits) != 20 or decoded.call_count != 21:
                    raise RuntimeError(
                        "Corpus coverage, output bound or native-only distance contract differs"
                    )
                measurements.append(
                    {
                        "query": label,
                        "entries": report.indexed,
                        "seconds": round(elapsed, 6),
                        "python_vectors_validated": decoded.call_count,
                    }
                )
            if len(os.listdir("/proc/self/task")) != threads:
                raise RuntimeError("Native vector search added worker threads")
            print(
                json.dumps(
                    {
                        "synthetic": True,
                        "engine": connection.execute("SELECT vec1_info()").fetchone()[0],
                        "entries": options.entries,
                        "dimensions": 384,
                        "database_bytes": database.stat().st_size,
                        "build_seconds": round(built, 3),
                        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        "queries": measurements,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        finally:
            connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
