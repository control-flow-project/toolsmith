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

- Bounded UTF-8 text, meaningful HTML and RSS/Atom reading.
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
directory, shared by every cooperating caller using the same upstream quota. It
uses validated bounded files and kernel locks, not another database or process.
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
previous digest after encoding outside transactions. Search accepts an explicit
bounded authorized candidate set and reports missing/stale coverage, never other
collections or silent lexical fallback. Text imports invalidate old derivatives
without deleting citable originals. Semantic clear deletes only derivatives.
Integrity and verified backups include vector profiles, finite unit vectors,
complete spans and canonical source bindings; no inference is required.

Return completed/partial/failed outcomes, warnings, exact versions and bounded
references. Publication, supplied observation and recording times remain distinct;
unknown source dates stay unknown. Output excludes incidental machine paths and
credentials. Export destinations are explicit and cannot overwrite existing files.

Backup is consistent under the selected store lock. Restore verifies the complete
backup before creating a new destination; it never overwrites production. Reject
unsupported schemas. Version one has no deployed predecessor to migrate; future
forward migrations need actual schema evidence and verified backups.

Cleanup requires a preview describing exact eligible inactive staging files and
their identities, then verifies the plan before deletion. Unknown files, symlinks,
changed files, active work, credentials and retained objects are never cleanup
targets. Integrity checks are explicit operations, not repeated whole-archive work
on ordinary agent reads.

## Verification

Verify strict types, formatting/lint, isolated tests, negative security controls,
installed CLI/library parity, optional-dependency absence and wheel/sdist contents.
Run these checks locally; GitHub Actions CI/CD workflows are not part of Toolsmith.
Architecture checks reject process spawning, servers, threads, skills and domain
coupling. Tests use controlled clocks and fake transport boundaries; no local test
server or indefinite sleep. Actual approved network acceptance is separate from
fixtures. Build/test tooling runs in an aggregate-memory/swap/task-bounded group.
No runtime or production deployment is authorized by package installation.
