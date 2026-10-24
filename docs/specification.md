# Toolsmith specification

Toolsmith provides optional generic library functions and a thin CLI. It owns
no fleet behavior, skills, application services, servers, daemons or background
work. Importing or installing it starts nothing. Commands perform bounded work
and return. Product code cannot spawn processes, listen on sockets or start
threads. Outbound approved HTTP/DNS requests are explicit acquisition effects.

The library and CLI use one implementation, typed expected results and validated
boundaries. No compatibility aliases, local/remote alternatives, speculative
adapters, placeholders or automatic fallback are allowed. Runtime dependencies
are absent from the base package. Selected HTTP and semantic capabilities require
their optional dependencies. No global config, storage root or credential is
selected implicitly.

## Capabilities

The 2026-10-13 consumer-coverage extension also requires archive-independent
parsing types, streaming regular-file hash/copy, bounded CSV-format reading,
article/access-screen and feed-date fidelity, caller-owned lexical indexes,
cheap bulk semantic index state, independent approved HTTP responses and shared
group/task acquisition budgets. Every addition needs a concrete consumer call,
an ownership decision and executable verification in the capability mapping.
Do not copy application schemas, summaries, permissions or financial logic.
Adopting projects replace their applicable generic implementation completely;
other fleets remain free not to install Toolsmith. Directory reorganization is
proposed only after this coverage work; no import aliases are retained.

- Bounded UTF-8 text, meaningful HTML and RSS/Atom reading.

HTML inspection reports markup signals and rejects document-title access screens;
it does not infer computed CSS visibility. Static text reading still rejects
unresolved access dialogs. Browser-owning callers validate computed-visible DOM
through that same text reader; Toolsmith neither runs a browser nor bypasses gates.
Inspection also returns typed untrusted anchor/feed links, including navigation
links separately from cleaned prose. Targets remain literal: callers resolve and
authorize them before any request. Labels are bounded to 1,000 characters with
an explicit truncation flag. The parser retains only attributes used by reading,
visibility, resource and link inspection. Unused attributes do not acquire an
independent value-size limit; the complete input/node/depth budgets still apply.
Duplicate HTML attributes retain their first value; later duplicates never
replace link targets or visibility attributes. This tolerance does not relax
XML/feed validation or the untrusted-link authorization boundary.
RSS/Atom results expose a resolved feed-level next-page link, if declared,
including inherited XML base resolution. Conflicting or unsafe next links fail.
Pagination is metadata only; callers own authorization, requests and completeness.
- Explicit safe regular-file reads and private artifact storage/export.
- Immutable local text/file versions and exact citations, with lexical FTS5 search.
- Approved HTTPS acquisition, bounded DNS/TLS/body/redirect handling and persistent
  local request pacing, quotas and cooldowns shared by cooperating callers.
- Recorded operation outcomes and explicit interrupted HTTP resumption.
- Consistent backup/verified restore, integrity checks, index rebuilding and
  preview-bound cleanup of inactive tool-owned staging files.
- MIT-licensed installable package, command contracts and operational documentation.
- Optional offline English MiniLM embeddings, complete token-aware source chunks,
  exact cosine retrieval and transaction-safe SQLite derivatives. The generic
  library accepts a caller-owned connection; store/CLI operations compose the
  same functions over retained text with exact version/part/span citations.

Browser automation and process-based PDF/OCR conflict with the no-helper-process
rule and are not implemented. Do not substitute HTML parsing for a browser or
UTF-8 reading for PDF/OCR. Hybrid retrieval remains excluded: lexical and semantic
queries are explicit, never substituted or blended. No domain connectors, source
catalogs, financial calculators, taxonomy, generative model calls, agent
instructions or public hosting belong here.

## Licensing and distribution

Toolsmith's first-party source, documentation and built artifacts are public and
MIT-licensed under LICENSE, copyright Jeswin P Kumar. Distribution metadata declares
the SPDX expression `MIT` and includes the license in wheel and sdist. Third-party
dependencies/model assets retain their own licenses; weights are not redistributed.
Consumer projects and retained source data are not relicensed by Toolsmith.
Local stores, credentials, .analysis and verification fixtures remain excluded
from published source and artifacts. Registry publication is a separate release
action, not an effect of building, installing or importing this package.

## Local state

Each explicit private root holds one collection, one `toolsmith.sqlite3`, immutable
`objects/`, and tool-owned staging in `tmp/`. Cooperating callers share that root;
there is no copy per agent. Public calls supply the exact collection identity and
check it before access. A different collection fails. SQLite FTS ranking therefore
does not include another collection. Collection labels are accident prevention,
not isolation from arbitrary full-access processes under the same OS account.

Persistent source-limit state lives in a separately explicit private network-state
directory, shared by every cooperating caller using the same upstream quota. One
bounded format-two `budget.json` holds group/task charges, reservations, pacing,
cooldowns and optional caller-owned JSON configuration. Configuration replacement
and allowance changes publish together under the same directory lock; readers
share that lock without creating files. Compare-and-swap uses the inspected
configuration digest. A request against a configured budget must supply that
same digest to reserve its charge, so a simultaneous approval edit cannot authorize
a request under stale settings. Outstanding reservations prevent limit changes;
charged groups cannot disappear and a reviewed period cannot be shortened.
Read-only budget checking never saves or rolls over state on disk.
It uses validated files and kernel locks, not another database or process. Boot,
wall and monotonic observations preserve elapsed quota periods and reject clock
rollback. Changing a policy cannot silently clear charges. Explicit quiesced
quota import accepts reviewed current generic counters, not consumer-specific
state files, and preserves their period and unknown charged usage.
There is no guarantee over callers selecting other state roots or bypassing tools.

Linux, Python 3.13+ and SQLite FTS5 are required for secure local persistence.
Text/HTML/feed readers do not require a store, optional network software or Linux
storage primitives. Missing requirements fail explicitly; no weakened fallback.

## Validation and safety

Validate types, identifiers, byte/record/structure limits, encoding, URL components,
scope and file ownership at public boundaries. Regular-file input never follows
symlinks or opens special files. Local private storage uses pinned directory
descriptors, no-follow opens, private modes and cooperating-caller kernel locks.
No tool interprets source text as instructions or executes stored content.
Explicit standalone file output may use an owned, non-group-writable parent;
collection roots and persistent quota/journal state remain private. Outputs are
private files, not permission changes to an existing parent. Replacement owns
atomic publication only; callers own coordination and compare-and-swap semantics.
No implicit lock file is added to an artifact directory. No-replace publication
uses one pinned-descriptor rename, never a transient hard-link alias.

Network access is HTTPS port 443 only, with exact reviewed DNS hosts. Reject URL
credentials, secret-like query keys, fragments and control characters. Resolve with
a finite lifetime, reject any non-public result and connect to a validated pinned
address while validating TLS against the original hostname. Recheck every redirect.
Ignore proxy environment configuration. Never forward cookies or credentials.

Bound compressed and expanded data, requests, redirects and total I/O deadline.
Upstream Retry-After and policy spacing return explicit deferral; no unconditional
sleep, automatic retry loop or model-credit accounting. Valid upstream delays are
never shortened. An unrepresentable delay blocks requests until operator review;
quota-window rollover cannot clear that block. Persist reservations before
network I/O; interrupted unknown usage is conservatively charged. Policy identity
and recorded requests cannot be silently changed to bypass limits.

Atomic metadata writes reference already durable immutable objects. A crash can
leave an unreferenced immutable object, never a committed reference to unwritten
content. Effect identities bind exact validated requests; mismatches fail. Recorded
status never starts work. Explicit HTTP resume reconciles completed results and
retries uncertain GETs with that uncertainty disclosed, within remaining limits.

## Output and operations

Semantic inference uses the pinned all-MiniLM-L6-v2 revision, CPU float32 ONNX,
384 dimensions, attention-mask mean pooling and L2 normalization. Its immutable
profile includes the backend, assets and complete-offset chunking contract.
The runtime executes sequentially with one calling thread, no worker thread pool.
Optional dependencies load only on explicit model loading. Operator-supplied
assets are pinned by length and SHA-256, read through no-follow descriptors and
passed as verified bytes, never an executable path. No inference network, global
model cache, credentials or automatic installation/download.
Queries exceeding 256 tokens fail; document chunks cover every character with
32-token overlap, checking the actual token ceiling without silent truncation.

Generic derivatives retain only references, source digest/length, profile, indexed
time and bounded vector/span records, not a second source archive. Consumers own
canonical text, authorization, summaries and source corrections. They invalidate
derivatives in the same transaction as a correction and publish with an expected
previous digest after encoding outside transactions. Search accepts an explicit database-resident authorized table/view and reports
missing/stale coverage without any corpus-count or scanned-chunk cutoff, never other
collections or silent lexical fallback. Text imports invalidate old derivatives
without deleting citable originals. Semantic clear deletes only derivatives.
Integrity and verified backups include vector profiles, finite unit vectors,
complete spans and canonical source bindings; no inference is required.
Bulk readiness and lexical matching return database-resident reference/digest
relations, not bounded candidate lists or source bodies. Canonical authorization,
freshness and application filters intersect those relations before counts and
pagination. Temporary relation names cannot overwrite another definition.
Preparing the semantic extension on a caller connection does not create schema,
change row factories or commit the caller's transaction.

Return completed/partial/failed outcomes, warnings, exact versions and bounded
references. Publication, supplied observation and recording times remain distinct;
unknown source dates stay unknown. Output excludes incidental machine paths and
credentials. Export destinations are explicit and cannot overwrite existing files.

Backup is consistent under the selected store lock. Restore verifies the complete
backup before creating a new destination; it never overwrites production. Reject
invalid database identity, structure or content. The optional archive has one
current schema. Its lexical derivatives and native vector index use the same
caller-owned implementations, not other archive engines. There are no historical
schema definitions, schema-version dispatch, conversion APIs or migration commands.
Explicit initialization creates the current schema; restore verifies and copies
that same schema. Consumers own retained originals and may explicitly rebuild
derivatives from those originals. Neither adopting consumer must use this archive.

Cleanup requires a preview describing exact eligible inactive staging files and
their identities, then verifies the plan before deletion. Unknown files, symlinks,
changed files, active work, credentials and retained objects are never cleanup
targets. Integrity checks are explicit operations, not repeated whole-archive work
on ordinary agent reads.

## Search capacity and resource budgets

SQLite owns vector comparison through the packaged public-domain vec1 0.8 extension,
compiled with worker threads disabled. The current configuration is an exact flat
index, not approximate nearest-neighbor pruning. Vectors are stored once inside
the native index; application references/spans remain normalized metadata. An
integer chunk-key filter is pushed into native selection before top-k. Each
indexed reference contributes its best chunk; returned records remain bounded.
No Python distance loop, candidate/chunk scan ceiling or hidden fallback exists.
Whole-index audits are separate from ordinary search and status.

The database has no Toolsmith byte ceiling. Backup/restore have an explicit
20 GiB aggregate budget and no object-count ceiling; databases are streamed, not
loaded wholesale into memory. Individual retained artifacts remain at most
128 MiB. HTML/PDF/image table meaning and geometry are interpreted by the
consumer LLM; no deterministic HTML table extraction API remains. CSV is format
parsing only. See limits.md for remaining bounds and their reasons.

## Verification

Verify strict types, formatting/lint, isolated tests, negative security controls,
installed CLI/library parity, optional-dependency absence and wheel/sdist contents.
Run these checks locally; GitHub Actions CI/CD workflows are not part of Toolsmith.
Architecture checks reject process spawning, servers, threads, skills and domain
coupling. Tests use controlled clocks and fake transport boundaries; no local test
server or indefinite sleep. Actual approved network acceptance is separate from
fixtures. Build/test tooling runs in an aggregate-memory/swap/task-bounded group.
No runtime or production deployment is authorized by package installation.
