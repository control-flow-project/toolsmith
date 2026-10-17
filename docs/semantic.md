# Optional semantic retrieval

Library and foreground CLI only. No server, encoder process, background indexing,
model API, automatic download, GPU path or hybrid/lexical fallback. Base installs
do not import or require the optional encoder dependencies. English is a caller
declaration, not language detection or multilingual certification.

## Explicit offline model preparation

Install the Toolsmith wheel with `[semantic]` into the caller's existing environment.
The extra pins ONNX Runtime 1.30.0 and Tokenizers 0.23.2; the development lock also
records the vendor's transitive dependencies. NumPy is not imported for inference. Nothing is
installed automatically by the library. Operator preparation is the only download:

```sh
MODEL_DIRECTORY="$PWD/private-minilm"
mkdir -m 700 "$MODEL_DIRECTORY"
BASE=https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/1110a243fdf4706b3f48f1d95db1a4f5529b4d41
curl --fail --location --max-time 120 "$BASE/onnx/model.onnx" --output "$MODEL_DIRECTORY/model.onnx"
curl --fail --location --max-time 60 "$BASE/tokenizer.json" --output "$MODEL_DIRECTORY/tokenizer.json"
chmod 600 "$MODEL_DIRECTORY/model.onnx" "$MODEL_DIRECTORY/tokenizer.json"
toolsmith semantic model-check --model-directory "$MODEL_DIRECTORY"
```

Use a new owned private directory with an existing parent, no symlinks. It must
contain **exactly** those two files. Check rejects unreviewed assets, wrong bytes,
permissions, hard links, pipes and path traversal. Do not point it at an arbitrary
Hugging Face cache. Failed checks never load an encoder or execute remote code.
No network or global Hugging Face cache is used in inference; verified bytes are
passed to ONNX and tokenizer constructors, avoiding verification/path reopening.
Installation does not prepare assets. Preparation commands are explicit operator
commands, not subprocesses spawned by Toolsmith.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `model.onnx` | 90,405,214 | `6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452` |
| `tokenizer.json` | 466,247 | `be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037` |

The [upstream model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
describes English sentence/paragraph embeddings, 384 dimensions and a 256-token
limit. Model rights remain upstream Apache-2.0, separate from Toolsmith's MIT license.
Toolsmith does not redistribute model weights. The immutable profile binds exact
assets, CPU float32 backend, mask-mean pooling, L2 normalization, ceiling and
complete-offset chunking. Other backends' vectors are not silently adopted.

ONNX is configured sequentially with intra/inter-op counts of one and spinning
disabled, following [the upstream threading contract](https://onnxruntime.ai/docs/performance/tune-performance/threading.html).
Tokenizer calls are serial, not batch-worker calls. Model objects are explicitly
owned/reused by a caller; there is no global singleton. Calls are synchronous.

## Generic SQLite library

The optional encoder uses pinned ONNX Runtime 1.30.0 C API 30 and Tokenizers
0.23.2. Indexing/retrieval uses the packaged SQLite vec1 0.8 extension, compiled
without worker threads. The base wheel contains that extension; no model,
compiler, optional Python inference package or network call is required to inspect
or search already encoded vectors.

Consumers keep canonical text and authorization in their own SQLite database.
Enable foreign keys and call `initialize_index` once. It creates only derivative
relations and loads the packaged extension; it does not set application schema
versions, change row factories or commit an existing transaction. Existing or
partial index schemas fail. The previous raw-vector schema has an explicit
`migrate_index` forward conversion; there is no alternate runtime reader.

```python
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from toolsmith.result import unwrap
from toolsmith.semantic import (
    Scope, Source, encode_query, initialize_index, load_model,
    prepare_embedding, publish_embedding, search_embeddings,
)

with closing(sqlite3.connect(":memory:")) as connection:
    connection.execute("PRAGMA foreign_keys = ON")
    unwrap(initialize_index(connection))
    connection.execute(
        "CREATE TABLE permitted_text "
        "(reference TEXT PRIMARY KEY, text_digest TEXT NOT NULL)"
    )
    source = Source("article:42", "Complete canonical text selected for this entry.")
    with unwrap(load_model(Path("/absolute/private-minilm"))) as encoder:
        prepared = unwrap(prepare_embedding(source, encoder))
        with connection:
            connection.execute("INSERT INTO permitted_text VALUES (?, ?)",
                (source.reference, hashlib.sha256(source.text.encode()).hexdigest()))
            unwrap(publish_embedding(connection, prepared, source,
                "2026-10-17T00:00:00Z", expected_digest=None))
        query = unwrap(encode_query("plain English question", encoder))
        report = unwrap(search_embeddings(
            connection, query, Scope("permitted_text"), maximum_records=20))
```

The scope is one application-owned table/view exposing a unique current reference
and lowercase SHA-256 text digest per row. `Scope` supports explicit reference/
digest column names and main/temp schema selection; identifiers are validated,
not arbitrary SQL snippets. Views can express the application's permissions,
article eligibility, room, date or other filters. Toolsmith owns none of those
rules. One million rows are valid: no Python tuple of a million IDs, JSON list,
article-body resubmission or corpus-size cutoff is required for a query.

A generic indexed entry is one opaque reference and its selected canonical text.
An article and its summary remain one business record in the consumer. The
consumer chooses which text represents that entry; indexing separate headline/
body/summary references is an explicit consumer representation choice, not a
requirement. Long entry text is divided into complete token-aware chunks, and
search returns that entry's best matching chunk.

## Exact ranking and scale

Vectors are stored once inside a native SQLite flat-vector index, with normalized
reference/span metadata alongside it. The question is encoded once. SQLite pushes
permitted chunk IDs into native selection before top-k, computes cosine distances
in C and returns bounded ranked hits. Python validates the query and returned
vectors; it does not unpack and compare every vector in the collection.

This is **exact flat search**, not ANN. It still compares eligible vectors using
native CPU instructions. It does not silently approximate, truncate the eligible
corpus, switch to lexical search or use a second backend. Equal-distance ordering
is unspecified. A returned hit is navigation, not proof that its source is true or
that an embedding correctly represents its meaning.

There is no 10,000-entry or 100,000-scanned-chunk ceiling. A million eligible
entries can be searched in one request; only output is bounded to 1..100 entries,
default twenty. The native top-k working set accounts for multiple chunks per
entry so one long entry cannot consume all requested result positions.
Missing/stale entries are excluded before ranking and reported separately.

Synthetic million-entry acceptance is in `scripts/accept_corpus.py`; actual
model acceptance is separate in `scripts/accept_semantic.py`. The synthetic
fixture proves capacity, late-position matches, permission filtering, bounded
Python vector decoding and no added threads. It is not a million-article
embedding-quality or production-latency certification. See verification.md for
measured hardware/run evidence.

## Bounds and correctness

The pinned English MiniLM profile remains 384 dimensions, CPU float32, mask-mean
pooling and L2 normalization. Queries over 256 model tokens fail, never silently
truncate. Sources are bounded to 4 MiB UTF-8; each complete chunk uses at most 254
source tokens plus two special tokens, with 32-token overlap and actual tokenizer
checks. At most 20,000 chunks belong to one source. These are model/per-entry work
bounds, not limits on total stored entries or query corpus size.

Prepared vectors cannot forge profiles, omit characters, contain nonfinite/nonunit
values or misidentify spans. Source corrections and invalidation share the
consumer's transaction. Encoding happens outside it; publication rechecks current
canonical text and the expected previous index digest. A conflict rolls back
without replacing a newer index. Native index writes, savepoints and rollback
participate in the same SQLite transaction; there is no sidecar file to reconcile.

`inspect_index(connection, references)` reads selected metadata only and has no
arbitrary reference-count cap. It returns exactly the requested records, so use
sensible batches when materializing large metadata outputs. `indexed_digest` and
`check_index` are explicit vector/source audits, not cheap readiness calls.
Reference relocation reuses exact vectors without inference; clearing removes only
derivatives. No operation creates or repairs missing canonical originals.

`inspect_coverage(connection, scope)` returns aggregate entries/indexed/missing/
stale counts. `pending_references(connection, scope, maximum_records)` returns one
bounded pending batch without loading the corpus. Both are index-owned metadata
ports; archive and application code must not query private derivative tables to
implement their own readiness or pending selection.

## CLI and optional archive

Standalone commands use the same functions:

```sh
toolsmith search semantic query "plain English question" --database "$PWD/app.sqlite3" --scope permitted_text --model-directory "$MODEL_DIRECTORY" --limit 20
toolsmith search semantic status --database "$PWD/app.sqlite3" --scope permitted_text
toolsmith search semantic check --database "$PWD/app.sqlite3" --scope canonical_text
```

`canonical_text` additionally exposes a `text` column for the explicit complete
audit. Queries/status do not need that column. `index --sources FILE --limit N`
accepts an explicit bounded foreground JSON batch, not the entire required corpus.

The separately optional archive uses current immutable parts and the same vector
engine. Status and pending-batch selection run in SQL rather than materializing
every part. A generation counter detects current-text changes while the question
is encoded outside the store lock. Search returns exact version/part/page/span
citations; old versions remain citable but are not current search input.

```sh
toolsmith --root "$PWD/store" --collection sample semantic index --model-directory "$MODEL_DIRECTORY" --limit 10
toolsmith --root "$PWD/store" --collection sample semantic status
toolsmith --root "$PWD/store" --collection sample semantic search "plain English question" --model-directory "$MODEL_DIRECTORY" --limit 20
```

Archive schema v3 includes the native index and current-text counter. Explicit
`maintenance migrate` verifies and copies reviewed v1/v2 stores into a new v3
destination, preserving the source as rollback data. Raw vectors are converted
without encoding again. Ordinary reads reject older or unknown schemas.

Databases have no Toolsmith byte ceiling. Backup/restore use an explicit aggregate
20 GiB budget and stream database files; individual retained artifacts remain
bounded to 128 MiB. No reset, automatic repair, source deletion or background
cleanup is performed.
