# Capacity and limit audit

Search corpus size and returned output are different quantities. A query over a
million eligible entries returning twenty hits must not search only the first
ten thousand entries. Neither lexical nor semantic search has a Toolsmith
corpus-count ceiling. No operation silently drops eligible entries to fit one.
`SearchReport.candidates` counts every selected scope entry, including missing or
stale derivatives; it is not a preselected or capped subset.

An entry is one consumer-assigned reference. A consumer can index one article
body, one latest article summary, or one document page as an entry. Indexing both
body and summary separately creates two entries; Toolsmith does not silently
combine them. One million such references means one million eligible entries.

## Removed restrictions

| Previous restriction | Current contract |
| --- | --- |
| Semantic: at most 10,000 selected texts | Database-resident authorized scope; no entry-count cutoff |
| Semantic: at most 100,000 scanned chunks | No aggregate scanned-chunk cutoff; SQLite native exact ranking |
| Lexical: at most 100,000 selected texts | FTS query over the complete selected relation |
| Index metadata: at most 100,000 requested references | Explicit requested metadata can be batched without a hard reference-count ceiling |
| CLI query/status requires article bodies or a JSON reference list | Query/status select an existing SQLite table/view |
| CLI full audit requires one whole-corpus JSON file | Audit looks up canonical text from the selected SQLite relation |
| Semantic CLI applies lexical query's 2 KiB cap | Same 16 KiB input and 256-token ceiling as the semantic library |
| Archive database: 128 MiB | No Toolsmith database/index byte ceiling |
| Integrity copies the complete database into Python RAM | SQLite 3.44+ verifies FTS directly through read-only `PRAGMA integrity_check` |
| Backup: at most 10,000 objects / 2 GiB | No object-count cutoff; 20 GiB aggregate logical-byte budget |
| Restore deserializes the complete database into RAM | Stream identity checks; read-only snapshot validation; streamed publication |
| Generic hash/copy: at most 1 GiB even with an explicit larger budget | Caller must supply a byte budget in the native signed-64-bit range |
| Literal lookup: at most 10,000 regions | Validate ordered/nonoverlapping regions within the bounded text |
| Journal: at most 100,000 records | The journal's explicit byte bound controls capacity; sequence uses native int64 |
| CSV: header must be within twenty lines; row budget cannot exceed one million | Explicit larger header/row budgets are accepted within the byte-bounded input |
| Quota accounting: 10,000 requests / 64 GiB counters | Reviewed policy/counter values use native int64; no change to the configured actual allowance |
| Archive HTTPS reimposes lower hidden task counters | Source group allowances remain authoritative; internal shared task counters use native int64 |
| Quota state: 256 groups / 1,024 tasks / 10,000 reservations | The existing 4 MiB serialized-state budget controls capacity instead of extra record-count gates |
| Archive paging: offsets above one million rejected | Native int64 offsets; returned page size remains bounded |

## Retained bounds

These bounds limit an explicit input, output, model operation or untrusted
structure. They are not ceilings on the application database's total entries.

| Surface | Bound and reason |
| --- | --- |
| Semantic query | 16 KiB input, 256 tokens: the selected MiniLM model's actual input capacity; fail instead of truncating |
| Semantic entry | 4 MiB text, 20,000 complete chunks: foreground preparation and individual-record validation budgets |
| Encoder batch | Sixteen chunks: bounded native tensor memory; repeat batches explicitly |
| Semantic output | 1..100 entries, default twenty; this limits returned hits, never eligible input |
| Lexical entry/output | 8 MiB entry; 1..1,000 returned hits, with offset; corpus remains uncapped |
| Lexical expression | 2,048 bytes and at most 32 literal terms/phrases; explicit FTS5 syntax remains distinct |
| Buffered file/retained artifact | 128 MiB; avoid an unbounded response or one retained object in memory; database/index files are not artifacts |
| Streaming IO | Explicit byte budget, 64 KiB transfer buffers; no automatic unbounded read |
| Backup/restore | Default/max 20 GiB aggregate database + artifact bytes; no object-count cutoff |
| Backup manifest | 128 MiB bounded metadata input; writer streams records and enforces the same bound as restore |
| ZIP | 128 MiB/member, 1 GiB aggregate, 10,000 members, 4 MiB central directory, depth 64; bounded untrusted archive expansion/metadata |
| Plain text / JSON | Configurable to 128 MiB; JSON rejects duplicate keys and nonfinite numbers |
| HTML | 4 MiB, 50,000 nodes, depth 128; reading attributes at most 8,192 characters; unused attributes discarded. Inspection preserves typed links, labels at most 1,000 characters with explicit truncation. No deterministic table interpretation. |
| Feed | 2 MiB, two million nodes, depth 32; all distinct entries are returned, without an item-count ceiling |
| XML / JSONL | Default 32 MiB input; XML has explicit node/depth/field bounds and rejects DTD/entities; invalid JSONL never drops a line silently |
| PDF | 32 MiB input; paged text defaults to twenty pages with an explicit continuation; rendering checks DPI/pixels/output bytes before publication |
| Download batch | 32 MiB manifest, 1..16 concurrent network operations, explicit total deadline; no item-count cap, and unfinished inputs are reported |
| Batch search | 32 MiB query input; existing per-query expression/model/output limits apply, never a corpus-count or query-count sample |
| CSV | 32 MiB compressed / 64 MiB expanded, 256 columns; row budget is explicit and configurable |
| Tree inventory | Default 10,000 / maximum 100,000 returned entries, explicit byte budget, depth 64; a bounded materialized tree report |
| Journal | 64 KiB event / 32 MiB journal; caller owns retention, no automatic deletion or replacement |
| Optional archive import | 4 MiB combined text / 1,000 parts per immutable import, with explicit citation paging; not a corpus limit |
| Optional archive list | At most 100 returned records per page; offset does not cap total retained records |
| Public HTTP | At most 128 MiB per response, 100 requests, ten redirects and sixty-second total deadline; separate reviewed quotas apply |
| Shared quota metadata | 4 MiB durable state; caller-configured allowances, periods, spacing and cooldowns remain authoritative |

Network allowlists, TLS/DNS checks, credentials exclusion, private/no-follow file
handling, digest checks and atomic publication remain mandatory. Increasing a
declared batch or byte budget never authorizes bypassing those controls.

HTML/PDF/image table geometry and interpretation belong to the consumer LLM.
The deterministic HTML-table API and CLI were removed. CSV/JSON decoding is format
parsing, not financial or semantic interpretation.

## Performance evidence

The vector engine uses an exact native flat index, not an approximate index. Work
still grows with the eligible vector corpus. No constant-time or ANN claim is
made. Local `accept_corpus.py` measurements, independent numerical-oracle tests,
filtered-query tests and actual MiniLM acceptance are recorded separately in
verification.md. A synthetic capacity fixture is not production latency or
million-document semantic-quality certification.
