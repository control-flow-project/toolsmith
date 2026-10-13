import argparse
import hashlib
import json
import os
import re
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from verify import require_limits

from toolsmith.files import read_bytes
from toolsmith.operations.backup import backup_store, restore_store
from toolsmith.operations.integrity import check_integrity
from toolsmith.result import Failure, unwrap
from toolsmith.semantic import (
    Candidate,
    Source,
    check_index,
    encode_query,
    fingerprint,
    initialize_index,
    invalidate_embedding,
    load_model,
    prepare_embedding,
    publish_embedding,
    search_embeddings,
)
from toolsmith.semantic.native import API_HEADER_SHA256, API_VERSION, SLOTS
from toolsmith.semantic.profile import PROFILE_ID
from toolsmith.semantic.store import index_text, inspect_text_index, search_semantic_text
from toolsmith.storage.database import initialize_store
from toolsmith.storage.models import document_from_json
from toolsmith.storage.text import put_text
from toolsmith.validation import parse_json, text


def verify_abi(header: Path) -> None:
    content = unwrap(read_bytes(header, 1024 * 1024))
    if hashlib.sha256(content).hexdigest() != API_HEADER_SHA256:
        raise RuntimeError("Acceptance header does not match the pinned upstream source")
    supplied = content.decode()
    if not re.search(r"#define ORT_API_VERSION\s+" + str(API_VERSION) + r"\b", supplied):
        raise RuntimeError("Acceptance header is not the pinned API version")
    body = supplied.split("struct OrtApi {", 1)[1]
    names = re.findall(
        r"ORT_API2_STATUS\((\w+)|ORT_CLASS_RELEASE\((\w+)\)|\(ORT_API_CALL\*\s*(\w+)\)", body
    )
    ordered = [
        status or ("Release" + release if release else ordinary)
        for status, release, ordinary in names
    ]
    for name, slot in SLOTS.items():
        if ordered[slot] != name:
            raise RuntimeError("Pinned native API slot differs: " + name)


def retained_sources(path: Path) -> tuple[Source, ...]:
    supplied = parse_json(unwrap(read_bytes(path)), 16 * 1024 * 1024)
    if not isinstance(supplied, list) or not 1 <= len(supplied) <= 100:
        raise ValueError("Supply a bounded retained original corpus")
    sources = []
    for ordinal, row in enumerate(supplied):
        if not isinstance(row, dict):
            raise ValueError("Retained source must be an object")
        sources.append(
            Source(
                "retained:" + str(ordinal),
                text(row.get("text"), 4 * 1024 * 1024, "Retained original"),
            )
        )
    return tuple(sources)


def main() -> int:
    require_limits()
    parser = argparse.ArgumentParser(
        description="Actual offline MiniLM, native ABI and portable fleet recipes; no production writes"
    )
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--api-header", type=Path, required=True)
    parser.add_argument(
        "--examples", type=Path, default=Path(__file__).resolve().parents[1] / "examples"
    )
    parser.add_argument("--retained-news", type=Path)
    options = parser.parse_args()
    verify_abi(options.api_header)
    threads = len(os.listdir("/proc/self/task"))
    environment = dict(os.environ)
    started = time.perf_counter()
    with (
        patch("socket.socket.connect", side_effect=AssertionError("Inference must be offline")),
        patch("socket.socket.connect_ex", side_effect=AssertionError("Inference must be offline")),
        unwrap(load_model(options.model_directory)) as encoder,
    ):
        cold = time.perf_counter() - started
        if len(os.listdir("/proc/self/task")) != threads or dict(os.environ) != environment:
            raise RuntimeError("Encoder created worker threads or changed caller configuration")
        if "numpy" in sys.modules or "onnxruntime" in sys.modules or "torch" in sys.modules:
            raise RuntimeError("Inference imported a forbidden global wrapper")
        with tempfile.TemporaryDirectory(prefix="toolsmith-semantic-") as temporary:
            root = Path(temporary) / "store"
            unwrap(initialize_store(root, "demo"))
            for name, item in (
                ("news-body.json", "news-body"),
                ("news-summary.json", "news-summary"),
                ("agreement.json", "agreement"),
            ):
                document = document_from_json(
                    parse_json(unwrap(read_bytes(options.examples / name)))
                )
                unwrap(put_text(root, "demo", item, document, item))
            report = unwrap(index_text(root, "demo", options.model_directory, encoder=encoder))
            if report.status.pending != 0 or report.newly_indexed != 5:
                raise RuntimeError("Portable news/agreement examples were not fully indexed")
            cases = [
                ("financial institutions disrupted by their cloud provider", "news-body", 1),
                ("assets outside the guarantor group", "agreement", 2),
                ("changing lender payment priority without consent", "agreement", 3),
            ]
            timings = []
            for query, item, part in cases:
                started = time.perf_counter()
                hits = unwrap(
                    search_semantic_text(
                        root, "demo", query, options.model_directory, encoder=encoder, item=item
                    )
                )
                timings.append((time.perf_counter() - started) * 1000)
                if (
                    hits.missing
                    or hits.stale
                    or not hits.hits
                    or hits.hits[0].citation.part != part
                ):
                    raise RuntimeError("Actual MiniLM did not retrieve the expected exact source")
            unwrap(check_integrity(root, "demo"))
            backup, restored = Path(temporary) / "backup", Path(temporary) / "restored"
            unwrap(backup_store(root, "demo", backup))
            unwrap(restore_store(backup, "demo", restored))
            if unwrap(inspect_text_index(restored, "demo")).indexed != 5:
                raise RuntimeError("Backup/restore lost semantic derivatives")
            long = Source("long", "A borrower transfers assets outside the guarantor group. " * 100)
            prepared = unwrap(prepare_embedding(long, encoder))
            if (
                len(prepared.chunks) <= 1
                or prepared.chunks[0].start != 0
                or prepared.chunks[-1].end != len(long.text)
            ):
                raise RuntimeError("Actual token chunking omitted the long source")
            oversized = encode_query("borrower " * 300, encoder)
            if not isinstance(oversized, Failure) or oversized.code != "limit":
                raise RuntimeError("Actual query tokenizer silently truncated")
            connection = sqlite3.connect(":memory:")
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                unwrap(initialize_index(connection))
                sources = (
                    retained_sources(options.retained_news) if options.retained_news else (long,)
                )
                for source in sources:
                    vectors = unwrap(prepare_embedding(source, encoder))
                    unwrap(
                        publish_embedding(
                            connection,
                            vectors,
                            source,
                            "2026-10-13T00:00:00Z",
                            expected_digest=None,
                        )
                    )
                unwrap(
                    check_index(
                        connection, {source.reference: source.text for source in sources}.get
                    )
                )
                queries = (
                    [
                        ("European Central Bank monetary policy meeting in Berlin", 0),
                        ("Bank of England cloud outage exercise operational resilience", 2),
                        ("Delhi protest Rahul Gandhi", 1),
                        ("Ukraine strikes Moscow Yandex data centre", 3),
                    ]
                    if options.retained_news
                    else [("borrower transfers assets", 0)]
                )
                candidates = tuple(
                    Candidate(source.reference, fingerprint(source.text)) for source in sources
                )
                for query, ordinal in queries:
                    generic_hits = unwrap(
                        search_embeddings(
                            connection, unwrap(encode_query(query, encoder)), candidates
                        )
                    )
                    if (
                        not generic_hits.hits
                        or generic_hits.hits[0].reference != sources[ordinal].reference
                    ):
                        raise RuntimeError("Retained original semantic ranking differs")
                with connection:
                    unwrap(invalidate_embedding(connection, sources[0].reference))
                missing = unwrap(
                    search_embeddings(
                        connection, unwrap(encode_query("borrower", encoder)), candidates
                    )
                )
                if missing.missing != 1:
                    raise RuntimeError("Mutable-source invalidation did not preserve coverage")
            finally:
                connection.close()
    if len(os.listdir("/proc/self/task")) != threads or dict(os.environ) != environment:
        raise RuntimeError("Native resources or caller configuration were not disposed")
    print(
        json.dumps(
            {
                "profile": PROFILE_ID,
                "native_api": API_VERSION,
                "cold_seconds": round(cold, 3),
                "warm_query_median_ms": round(statistics.median(timings), 3),
                "fleet_examples": "passed",
                "generic_sqlite": "passed",
                "backup_restore": "passed",
                "complete_long_source": "passed",
                "retained_originals": len(sources) if options.retained_news else 0,
                "new_worker_threads": 0,
                "inference_network_calls": 0,
                "production_writes": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
