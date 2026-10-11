# Architecture

```text
Caller imports toolsmith            Human or agent invokes toolsmith CLI
           |                                      |
           +---------- validated library ----------+
                                 |
              selected reader / storage / acquisition / maintenance
                                 |
              explicit local files and SQLite; approved outbound HTTPS
                                 |
                      result or expected failure; return
```

There is no service transport, job queue, plugin framework or second implementation.
The package does not depend on Crossfire, fleetd, any agent runtime or domain project.
Consumers can continue using all fleet functions without installing Toolsmith.

## Source ownership

```text
toolsmith/
├── AGENTS.md, LICENSE, README.md, pyproject.toml, uv.lock
├── docs/
├── src/toolsmith/
│   ├── result.py, validation.py, clock.py, files.py
│   ├── readers/             UTF-8, static HTML, RSS/Atom
│   ├── storage/             One SQLite schema, versions, artifacts, operation records
│   ├── acquisition/         Explicit policy, quotas, bounded DNS/TLS/HTTPS, resume
│   ├── retrieval.py         Literal lexical search and exact citations
│   ├── operations/          Integrity, index rebuild, backup/restore, staging cleanup
│   └── cli/                 Argument parsing and calls to the same library
├── scripts/                 Development verification and package acceptance
└── tests/                   Controlled fixtures, integration and architecture checks
```

No empty browser, PDF, OCR, embedding or migration modules exist. Schema one is
the only schema. A future migration must be based on a real deployed predecessor,
not a speculative compatibility layer.

## Persistent state

```text
<explicit private collection root>/
├── .lock                    Cooperating-reader/writer kernel lock
├── toolsmith.sqlite3        Collection, text/file versions, chunks, FTS, operations
├── objects/<sha256>         Immutable permitted file bytes
└── tmp/.stage-<uuid>.tmp    Invocation-owned staging

<explicit shared network-state root>/
├── .lock
└── <source-group-hash>.json Policy binding, current quota window, reservations/cooldown
```

Each store has one collection. Every store API checks its identity before lookup,
mutation or search. BM25 ranks only that collection, not unrelated tenants' text.
Names and caller-supplied labels do not grant filesystem authority or isolate
arbitrary programs running as the same user.

Text versions bind exact validated item/provenance/parts; recording time is separate.
An item's current pointer changes on a new import, but old versions remain citable.
Replaying a completed request does not revert the current pointer. Request identities
bind exact validated input and reject reuse with different input.

Retained text parts are authoritative. Chunk spans and lexical postings are derived
by one chunking implementation used for both normal writes and explicit rebuilds.
Integrity checks verify complete coverage, not just the spans of remaining chunks.
The cleanup plan also has one owning validator shared by library and CLI calls.

File bytes are fsynced before transactional metadata references them. A crash may
leave an unreferenced object; metadata never intentionally references unwritten bytes.
Initialization publishes a complete schema from staging; unpublished staging can
be retried without adopting a partial database. SQLite writes roll back on failure.

Read locks are shared; writes are exclusive and nonblocking. Contention returns
`deferred`, not a waiting background job. Acquisition holds the store write lock
for its bounded invocation and releases network-state locks between reservations.
Network I/O never occurs inside a SQLite transaction.

HTTP resumes use the saved validated request and existing request count. Policy
and network-root bindings cannot be changed under the same operation identity.
Completed results are reused. Interrupted GETs can be retried only explicitly,
with uncertainty reported; unknown response usage remains conservatively reserved.
