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

The backend loads the pinned ONNX Runtime 1.30.0 native C API (API 30) directly,
not the Python wrapper: NumPy/Torch are never imported for inference. Native
resources close in reverse acquisition order; use `with unwrap(load_model(...))`
or explicitly close the returned model. Store functions close models they own;
an explicitly injected encoder remains caller-owned.

The upstream POSIX provider otherwise initializes a telemetry uploader at startup,
before its disable-events API can be called. Toolsmith serializes initialization,
sets the documented process telemetry opt-out during construction, and restores
the previous environment value even on failure. ONNX process-wide telemetry stays
disabled. No host config, user cache, uploader or thread tuning is created. This
is an explicit privacy policy, not a promise to control other same-process code.

The fleet can embed three singular tables in its **own** SQLite database without
using Toolsmith's text archive, filesystem store or CLI. Enable foreign keys, call
`initialize_index` once when creating that schema (or include `SCHEMA_SQL` in the
owner's schema construction), and manage transactions using the existing owner.
Repeated initialization is rejected; no legacy/alternative schema is adopted.

```python
import sqlite3
from toolsmith.result import unwrap
from toolsmith.semantic import (
    Candidate, Source, encode_query, fingerprint, initialize_index, load_model,
    prepare_embedding, publish_embedding, search_embeddings,
)
from pathlib import Path

connection = sqlite3.connect(":memory:")
connection.execute("PRAGMA foreign_keys = ON")
unwrap(initialize_index(connection))
encoder = unwrap(load_model(Path("/absolute/private-minilm")))
source = Source("document:section:body", "Complete original source text")
prepared = unwrap(prepare_embedding(source, encoder))
with connection:
    unwrap(publish_embedding(connection, prepared, source,
        "2026-10-13T00:00:00Z", expected_digest=None))
query = unwrap(encode_query("source text", encoder))
report = unwrap(search_embeddings(connection, query,
    (Candidate(source.reference, fingerprint(source.text)),)))
for hit in report.hits:
    exact_text = source.text[hit.start:hit.end]
encoder.close()
connection.close()
```

All operational functions return the shared typed `Result`. `Source`, `Prepared`,
`Candidate`, `Hit`, `SearchReport` and `IndexReport` are immutable records. The
encoder is a typed call boundary, not a plugin registry or parallel product backend.
Prepared vectors cannot omit source characters, forge spans, use another profile
or contain NaN/infinite/nonunit values. Batches are at most sixteen chunks.

References are opaque, bounded caller identifiers, not authorization. Source text
is at most 4 MiB UTF-8. Chunks use up to 254 source tokens plus two special tokens,
32-token overlap and re-tokenization checks. Queries over 256 tokens **fail**, not
truncate. All spans count Python Unicode characters, not UTF-8 bytes. Search is
exact cosine, bounded top-k (1..100), one best chunk per candidate with stable
reference tie-breaking. Candidate sets are explicit, unique and at most 10,000.
The caller selects them **after authorization** and supplies current source digests.
At most 100,000 vector chunks may be scanned in one query; larger selections fail
explicitly rather than running unbounded work or silently dropping candidates.
Missing or stale vectors are excluded and counted in coverage; this is not a
silent fallback or a claim that the full archive was indexed.

`inspect_index(connection, references)` returns cheap bulk digest/character/chunk
metadata without reading source bodies or vectors. Use it for readiness, not
integrity certification. `indexed_digest` fully validates existing vectors and
complete source spans without inference; it is intentionally not a cheap readiness
call. `relocate_embedding` reuses exact unchanged vectors under a new reference;
`clear_index` removes only derivatives, never application tables or canonical text.
Repeated
identical publication reuses vectors. Changed publication must supply the previous
digest; a competing update produces `conflict` and rolls back only its savepoint.
Consumers must also recheck their canonical source at publication: an index's
previous digest cannot prove the source did not change while encoding.

Source corrections and `invalidate_embedding` belong in **the same transaction**.
External callers retain full canonical source ownership, not a second copy here.
Do not hold a transaction over model encoding. `check_index(connection, lookup)`
is explicit whole-index verification against the owner's canonical source lookup.
It does not import optional model packages. It checks profiles, digests, complete
spans and finite normalized vectors, not whether the model truthfully encoded a
particular meaning. No such provenance certification is claimed.

## Text-store CLI and library

`index_text`, `inspect_text_index`, `search_semantic_text` and `clear_text_index`
live in `toolsmith.semantic.store`. These compose the generic library over the
one ordinary collection store. There is no separate vector database.

```sh
toolsmith --root "$PWD/store" --collection sample semantic index --model-directory "$MODEL_DIRECTORY" --limit 10
toolsmith --root "$PWD/store" --collection sample semantic status
toolsmith --root "$PWD/store" --collection sample semantic search "plain English question" --model-directory "$MODEL_DIRECTORY" --limit 20
toolsmith --root "$PWD/store" --collection sample semantic search "plain English question" --model-directory "$MODEL_DIRECTORY" --item selected-document
```

Indexing is one bounded foreground batch of 1..100 parts, default ten. Repeat
explicitly until status.pending=0. Existing complete current parts are reused;
when none are pending, no model load occurs. Imports keep old exact citable
versions, atomically invalidate changed/removed text vectors, and rebind unchanged
text vectors to updated title/page/provenance without re-encoding. Page parts are independent
semantic candidates; full agreements must not be truncated to one short chunk.
Search returns exact retained citations with title/method/source time and page
metadata, score and full match span, plus indexed/missing/stale coverage. The
display citation is capped at 16,384 characters; match_end preserves the full
chunk extent for explicit citation paging. Status is coverage, not a health check.

## Recovery and limits

`maintenance integrity`, backup and verified restore include vector validation
and preserve vectors. They require no encoder or downloaded assets. Missing or
corrupt canonical originals are failures, never reconstructed from embeddings.
For a corrupt **derived-only** index, explicitly use `semantic clear`, then
`semantic index`; clearing retains every source, original version, file and quote.
Do not clear production before reviewing a verified backup. No automatic repair,
source deletion, background cleanup or inference at import time is implemented.

The generic port does not set the consumer database's size/retention policies.
The Toolsmith collection retains its documented bounded database. Exact search
scans selected vectors; it is not an ANN/distributed engine or a scalability claim
for an unbounded corpus. Similarity is discovery, never proof or legal analysis.
