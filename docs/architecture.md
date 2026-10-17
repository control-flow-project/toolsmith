# Architecture

```text
Caller imports Toolsmith         Human or agent invokes its short-lived CLI
           |                                      |
           +---------- validated library ----------+
                                 |
          filesystem / parsing / HTTP / search / journal
                                 |
          explicit files; caller-owned SQLite; approved outbound HTTPS
                                 |
                   result or expected failure; return
```

The separately optional text archive composes those same primitives with its
own version/citation/retention schema. It is not a required application database,
a generic storage backend, or another parsing/network/index implementation.
No service transport, daemon, job queue, plugin framework, helper process or
worker thread exists. Toolsmith has no fleet/runtime/domain dependency.

## Current source ownership

```text
src/toolsmith/
├── result.py, validation.py, clock.py, compression.py, sqlite.py
├── scopes.py               Shared validated database-resident search scope
├── files.py, filesystem.py  Safe IO, streams, descriptors, locks and tree publication
├── archives.py             Exact explicitly selected files, not document manifests
├── readers/                Parsing types, UTF-8/JSON, static HTML, feeds and CSV
├── lexical/                Caller-owned derivatives and exact literal passages
├── semantic/               Offline encoder, caller-owned vectors and bulk metadata
│   └── store.py            Optional archive composition, no second vector engine
├── acquisition/
│   ├── client.py           Generic approved raw HTTPS responses
│   ├── transport.py        One DNS/TLS/HTTPS implementation
│   ├── urls.py, config.py   Boundary validation and generic policy parsing
│   ├── budgets.py          Shared durable group/task reservations and cooldowns
│   ├── budget_import.py    Explicit reviewed quota transfer, original state retained
│   └── http.py, policy.py, limits.py
│                           Optional archive receipts/retention composition
├── journal.py              Generic bounded JSON framing; caller-owned event meaning
├── storage/                Optional archive schema, immutable versions/files/receipts
├── retrieval.py            Archive citations and composition of generic lexical search
├── operations/             Archive integrity/backup/restore/staging cleanup
└── cli/                    Thin calls to the same libraries
```

This describes the implemented paths. The [full proposed layout](proposed-layout.md)
moves them into explicit capability namespaces once approved; it creates no aliases,
parallel implementations or runtime placeholders.

No browser/PDF/OCR substitute exists. No application source approvals, financial
schemas/calculations, summary model or agent instructions are copied here.

## Application-owned data and derivatives

Consumers keep canonical pages/articles, identity, permission and source-correction
rules in their own databases. Public lexical/semantic libraries own only indexed
derivative relations, use application transactions and leave its row factory and
schema version unchanged. Initialization is explicit and requires foreign keys
before writes. Expected failures roll back; encoding remains outside transactions.

Authorization is an explicit application-owned SQLite table/view exposing unique
references and current digests. Lexical and semantic queries join this relation
before ranking and output limits; no Python candidate tuple or resupplied article
body is required. The packaged vec1 extension owns one native flat-vector index
in the same database. Exact cosine comparison runs in native code; no Python
scan, second vector copy, remote service or approximate fallback exists. Missing/stale coverage is explicit. BM25 statistics
are database-wide; candidates are not statistical corpus isolation. GAAP therefore
keeps its room-specific databases. Literal passages and indexed lexical/semantic
queries have deliberately different semantics, never fallback behavior.

Bulk readiness reads metadata only. Full source/chunk/vector audits are separate,
explicit operations. Reference relocation reuses exact unchanged vectors without
inference. There is one lexical engine for applications and the optional archive.

Native inference uses exact pinned MiniLM assets and ONNX C API with explicit,
reverse-order lifetimes, one CPU calling thread and no download/backend fallback.
Telemetry is opted out before startup creates a cache/uploader; the caller's prior
environment is restored. Actual acceptance checks native slots, inference, threads
and syscalls rather than treating fixture encoders as native certification.

## Explicit persistent state

```text
<application-owned database>
└── Toolsmith lexical/semantic derivative relations, only if selected

<explicit shared network-state root>/
├── .lock                    Cooperating-caller kernel lock
└── budget.json              One group/task period, reservations, spacing/cooldowns

<explicit journal root>/
├── .lock
└── journal.jsonl            Bounded generic JSON events; application-owned retention

<separately optional archive root>/
├── .lock
├── toolsmith.sqlite3        Current archive schema v3, versions/files/operations
├── objects/<sha256>         Immutable retained file bytes
└── tmp/.stage-<uuid>.tmp    Invocation-owned staging
```

Neither consumer must create the last root. No private/global default is chosen
on import or installation. Cooperating kernel locks/private modes prevent ordinary
mistakes; labels and digests do not isolate arbitrary same-user processes.

## Durability and explicit recovery

Regular-file IO is bounded/no-follow and checks stable descriptor metadata. Tree
inventory reads metadata, not every content digest. Exact-file ZIPs are streamed,
validated and published atomically without overwriting existing destinations.
Mutable state uses explicit atomic replacement; original artifacts are immutable.

Generic HTTP returns raw bytes/receipts without a store. Consumers keep their own
durable job admission via the pre-request hook. One shared budget engine can also
charge externally owned browser operations. Unknown usage stays reserved; changes
to policy or reboot/clock rollback cannot clear quotas. Explicit forward import
takes reviewed counters/cooldowns into an empty root; there is no old-state reader.

Archive HTTP composition owns retained request/result identities and explicit
resume. It calls the same HTTPS producer. Network/native effects stay outside SQL
transactions. Status starts nothing; retries uncertain GETs are explicitly requested
and disclosed, within remaining admission limits.

Archive schema v3 uses the generic native vector index, current-text view and
change counter. Explicit migration preserves verified v1/v2 source stores and
converts their derivatives into this schema. It uses the generic lexical
engine. An explicit offline v1/v2-to-v3 migration verifies originals, copies into a new
destination, rebuilds only derivatives and verifies before publication. The source
remains unchanged as the rollback copy. Ordinary reads accept only the current
schema: no dual runtime reader, automatic migration, reset or hidden fallback.
