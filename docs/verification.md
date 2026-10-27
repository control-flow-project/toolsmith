# Verification

## XML namespace scope — 27 October 2026

Lexical QName values require the containing element's namespace declarations.
The single XML reader now preserves complete in-scope prefix bindings, local
rebinding, default namespace removal and the implicit `xml` prefix. Namespace
metadata follows the existing field and attribute bounds, including a bound on
in-scope binding count. Feed reading uses the same bounded parser.

The complete gate passes 504 tests in 42 isolated files with no failures or
skips, Ruff formatting/lint, strict Mypy over 122 files and wheel/sdist builds.
Verification uses a 4-GiB, zero-swap, 256-task scope on 24 available cores. Clean
wheel/sdist installed base, CLI/library and optional HTTP/semantic installation
checks pass. Scoped XML bindings are checked in both source and installed
primitives. No network source completeness, registry publication or fleet
activation is certified.

## Complete package review — 25 October 2026

The review covered every first-party source, test, script, example and guide,
plus the complete modified vec1 implementation. Two boundary defects were
reproduced: duplicate DNS hosts were accepted or silently removed differently
between typed/JSON HTTP policies, and raw HTTP CLI requests fetched before
rejecting an existing or relative destination. One shared host validator now
normalizes before rejecting duplicates; destination validation precedes HTTP
and final publication remains atomic and no-replace. Scheduler wording uses
caller-defined buckets. Current guides now match feed limits, transport exports,
optional PDF support and output-directory behavior.

The added controls initially produced nine failures and seven passes. After the
corrections, all 497 tests in 42 isolated files pass without warnings or skips;
Ruff format/lint, strict Mypy over 122 files and wheel/sdist builds pass. Tests
run under the existing 8-GiB, zero-swap, 256-task limits. Clean wheel and sdist
installations pass base/optional-dependency checks, library/CLI calls, native PDF
text/rendering and actual pinned MiniLM/API-30 acceptance with no added threads.
The small example corpus has warm query medians of 8.342 ms and 8.219 ms in these
two installations; these are observations, not production latency guarantees.
No live news completeness, registry release or fleet activation is certified.

## PR review corrections — 25 October 2026

Controlled regressions reproduced two automatic-wait defects: a new download
waited out an existing publisher cooldown or exhausted quota instead of returning
a deferral. Budget admission now waits only for local spacing/slot contention;
separate batches retain permitted spacing. Typed query batches enforce the same
32-MiB aggregate bound as file input before index/model work.

Live consumer qualification exposed database corruption. The file preflight
opened and closed an ordinary descriptor while another connection held SQLite
locks. That close releases all POSIX record locks for that file in the process,
allowing a competing writer. Metadata inspection now uses Linux O_PATH at the
shared connection owner. External-process tests verify that secondary generic,
index and archive connections retain the original writer lock; symlink, hardlink,
permission and nonregular-file rejection remain covered. The consumer adds the
same regression for companion-database validation. This follows SQLite's
[documented close/locking hazard](https://www.sqlite.org/howtocorrupt.html).

The corrected source passes 481 tests across 42 isolated files, with zero failed
tests or warnings, Ruff formatting/lint, strict Mypy over 122 files, and wheel/sdist
builds. Fresh independent wheel and sdist installations pass CLI/library,
XML/JSONL/HTML/URL/ZIP/PDF primitives, archive contents, optional HTTP and optional
semantic installation checks. These runs use the verified 8-GiB, zero-swap,
256-task scope. Actual MiniLM assets were not supplied to this package rerun;
the earlier dated real-model evidence remains separate. Consumer recovery and
full live collection are not certified by these library checks. The installed
third-party dependency audit reports no known vulnerabilities; it skips the
editable first-party distribution. Dependency records did not change in these
review corrections.

## Selected acquisition buckets — 25 October 2026

The pre-review source gate passed 469 tests in 41 isolated files, strict typing,
lint/format and wheel/sdist builds. The bucket scheduler is shared by approved
HTTP downloads and caller-owned asynchronous acquisition operations. Its default
is one concurrent coroutine per publisher bucket, not an eight-request ceiling.

A controlled-clock test submits 100 selections in five buckets. All five
publishers enter each round concurrently; each bucket remains sequential and its
20 starts occur at 0, 10, ..., 190 simulated seconds. This is scheduling evidence,
not a live network throughput benchmark. Invalid throttles and duplicate publisher
buckets fail before operations. Unexpected producer failure cancels and joins
other workers. Installed wheel/sdist acceptance checks the bucket API and the
current CLI version. Shared HTTP authorization, persistent budgets, cooldowns,
timeouts and interrupted-download accounting retain their existing tests.

## Generic primitives — 2026-10-24, 0.5.0

The integrated local gate passes 461 tests in 40 isolated files, Ruff formatting
and lint, strict Mypy and wheel/sdist builds. It runs with an aggregate 8-GiB
memory limit, zero swap and at most 256 tasks. Tests cover complete 2,500-entry
feeds, 250 selected downloads, cross-group concurrency, same-group serialization,
crash/deadline accounting, strict HTTP framing, typed XML/JSONL/HTML metadata,
native PDF text/rendering, output-file safety and one coverage read per batch
of 250 indexed queries. These are not live discovery or summary-quality claims.
Form-wrapped public pages retain their text and links without leaking control
values. Password/access checks remain covered. Long reading attributes use the
whole 4 MiB HTML bound; oversized complete input still fails. Fresh independent
wheel/sdist acceptance includes the form case, actual MiniLM and native PDF checks.

The optional primitives and actual MiniLM installation checks pass in independent
wheel and sdist environments, with no added native worker threads. Direct HTTPS
smoke requests fetch the ET OPML directory (30,863 bytes), Mint markets feed
(40,972 bytes) and Business Standard markets feed (55,650 bytes). Those requests
verify the transport only, not complete news coverage or Luna decisions.

The locked runtime dependency audit reports no known vulnerabilities. On
2026-10-24 the maintainer approved certifi 2026.10.19 and filelock 4.2.1 as exact
security-fix exceptions to the seven-day release-age cutoff. Lock resolution and
installed-package verification retain that cutoff for every other dependency.
Pillow uses the eligible fixed 13.0.0 release. No audit failure is waived.

This file documents reproducible gates. Release evidence is recorded after the
actual run; fixture results are not certification of every publisher/network.

## Linked HTML and feed pagination — 2026-10-24

Version 0.4.3 exposes typed anchor/feed links through the existing HTML inspector.
Literal targets remain untrusted; no link is requested automatically. Navigation
links are distinct from cleaned prose. Long labels expose a truncation flag.
Unused data attributes no longer fail the reader solely because of value length;
relevant attributes, input bytes, nodes, nesting, duplicate-attribute and access
checks remain enforced. Feed results also expose the declared Atom next-page
link in RSS/Atom. Inherited XML bases apply to next and article links;
conflicting or unsafe next targets fail, and no page is requested automatically.
Protocol ownership follows RFC 5005 feed pagination, not publisher selectors.

The complete gate passes 381 tests in 32 isolated files, Ruff lint/format and
strict Mypy over 103 source/test/script files. Wheel and sdist build and install
into independent clean environments; installed CLI/library, linked HTML,
feed pagination, license/archive contents, optional HTTP and
optional semantic installation checks pass. No skipped case or failed test is
reported in this run. Verification uses an aggregate 8-GiB, zero-swap, 256-task
scope. The dependency lock changes only the first-party version record.
These are offline/package checks, not live publisher or model-quality evidence.
No registry publication, service or fleet activation occurs.

## Current-schema cleanup — 2026-10-22

The 0.4.2 source removes archive/vector schema converters, their CLI/library
exports and historical fixtures. The archive has one current structure, checked
directly at store access and restore; it has no schema-version dispatch. Current
source versions and citation histories remain domain data.

The full local gate passes 354 tests in 30 isolated files, with no failures or
skips. Formatting, Ruff, strict Mypy over 101 source files, wheel/sdist builds and
installed CLI/library acceptance pass. Base, optional HTTP and optional semantic
installations pass. The runner uses all 24 available cores inside an 8 GiB,
no-swap, 256-task aggregate scope. No registry publication or consumer deployment
is part of these checks.

An initial run rejected the capacity fixture because it retained an unrelated
table. The fixture now drops its temporary allocation table before exercising
backup. It still verifies a database above 128 MiB and streaming reads no larger
than 64 KiB. The current-schema validation and capacity assertions remain intact.
Later dated sections describe their original revisions, not current APIs.

## Full gate

```sh
uv sync --frozen --all-extras
systemd-run --user --scope --quiet \
  --property=MemoryMax=8G --property=MemorySwapMax=0 --property=TasksMax=256 \
  --working-directory="$PWD" "$PWD/.venv/bin/python" "$PWD/scripts/verify.py"
```

This is a transient verification scope, not an installed global/product service.
The runner verifies actual cgroup v2 aggregate memory/swap/task limits and rejects
an unbounded group. It runs configured format/lint and strict types, then isolated
test files concurrently using available CPU affinity, with bounded waits and
reverse-order process disposal. No test server, unconditional sleep or fixture-only
native extraction claim exists. Each test owns/removes its temporary directory.

Tests cover reader limits/DTD/hidden content, exact version/citation/current search,
request identity/scope, filesystem/symlink/pipe/permissions, transaction rollback,
DNS/URL/redirect/cooldown/resume/gzip/deadline/TLS controls, backup/restore, corruption,
cleanup identity checks, CLI parity and banned architecture/dependencies. Public
network acceptance is separately explicit and uses the production DNS/TLS path.

The gate builds wheel and sdist. Package acceptance additionally installs both
formats in clean virtual environments, verifies no base HTTP dependency, installed
CLI/library calls, schema/typing/license files and no private/temporary content.
Dependency audit must be green; no release-age policy bypass or weakened gate.

## Scope of evidence

Semantic release acceptance requires the explicitly prepared pinned model and
official API-30 header. The script verifies native table slots, actual MiniLM,
complete token chunking, original/summary/agreement examples, generic SQLite and
backup/restore, zero added worker threads and unchanged process environment.
Run it in the same bounded scope; it neither fetches assets nor modifies fleets:

```sh
curl --fail --location --max-time 60 https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/include/onnxruntime/core/session/onnxruntime_c_api.h --output "$PWD/onnxruntime_c_api.h"
systemd-run --user --scope --quiet \
  --property=MemoryMax=8G --property=MemorySwapMax=0 --property=TasksMax=256 \
  --working-directory="$PWD" "$PWD/.venv/bin/python" "$PWD/scripts/accept_semantic.py" \
  --model-directory "$MODEL_DIRECTORY" --api-header "$PWD/onnxruntime_c_api.h"
```

`--retained-news FILE` additionally exercises previously captured real originals;
it does not collect news or call Luna. Fixture/sample success is not proof of
domain analysis, current live acquisition, summary-model execution or deployment.
Set `TOOLSMITH_MODEL_DIRECTORY` and `TOOLSMITH_API_HEADER` when running package
acceptance to exercise installed wheel and sdist with the actual encoder as well.

Controlled transport fixtures establish routing, contracts and negative controls.
Real HTTPS acceptance establishes tested public-source DNS/TLS/body behavior, not
all possible publisher restrictions or future availability. Python/Linux/SQLite
versions actually used, test counts, package acceptance and dependency-audit results
must be listed accurately in the release report. No product deployment is implied.

## Installed artifacts and actual HTTPS

After the full gate builds the artifacts, run both acceptance commands in bounded
scopes. HTTPS acceptance sends one bounded request to the permitted public example
source; it is explicit network work, not a background test server.

```sh
for script in accept_package.py accept_https.py; do
  systemd-run --user --scope --quiet \
    --property=MemoryMax=8G --property=MemorySwapMax=0 --property=TasksMax=256 \
    --working-directory="$PWD" "$PWD/.venv/bin/python" "$PWD/scripts/$script"
done
SITE_PACKAGES=$("$PWD/.venv/bin/python" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
systemd-run --user --scope --quiet \
  --property=MemoryMax=8G --property=MemorySwapMax=0 --property=TasksMax=256 \
  --working-directory="$PWD" "$PWD/.venv/bin/pip-audit" --path "$SITE_PACKAGES" --skip-editable
```

## Consumer adoption — 0.4.0, 2026-10-17

Local source verification passes 359 tests on each of Python 3.13.15 and 3.14.4.
Both runs use 31 isolated files with 24 workers in the required 8 GiB/no-swap/
256-task groups. Ruff lint/format and strict Mypy pass for 104 files. Caller-owned
relations, paths, configured quotas, concurrent locking, import clocks and
replacement publication are covered alongside the existing archive/search tests.

Clean wheel and sdist acceptance pass for base, HTTP and semantic installations.
The installed native API-30 encoder completes caller-owned SQLite, CLI, original/
summary/agreement examples, backup/restore and long-source checks with no added
worker threads or inference network calls. The measured installed warm medians
are about 10 milliseconds on the small acceptance corpus; these measurements
are not million-document performance or domain-answer-quality certification.
The explicitly approved native example.com HTTPS request passes with 400 wire
bytes. The installed Python dependency audit finds no known vulnerabilities;
it excludes the editable first-party package and does not certify native C.
All sixty third-party lock records remain unchanged.

Consumer source, exact-revision locks and clean installed integration are separate
gates; a Toolsmith test run does not certify a fleet deployment. GAAP applies its
own 32 MiB PDF input limit, below the unchanged generic 128 MiB ZIP-member ceiling.
Bad Bets adoption is deferred and is not part of the current consumer sign-off.
No registry release, production data migration, controller activation or deployment
has occurred.

## Indexed corpus and limit audit — 0.3.0, 2026-10-17

Integrated verification runs on Linux x86_64, an AMD Ryzen 9 5900X, with 24
available logical CPUs. The current source passes in both environments:

| Python | SQLite | Tests | Result |
| --- | --- | ---: | --- |
| 3.13.15 | 3.53.1 | 335 | All passed |
| 3.14.4 | 3.46.1 | 335 | All passed |

- Ruff format/check and strict Mypy pass for 99 source/test/build files. Twenty-eight
  isolated test files run with 24 workers in verified 8 GiB/no-swap/256-task scopes.
  Tests retain their assertions and own/dispose temporary fixtures.
- Actual SQLite vector tests compare 400 independent random vectors against a
  double-precision cosine oracle. Integer membership covers each packed metadata
  representation, nulls, duplicate/empty sets, int64 edges, multiple predicates,
  current permissions before top-k, and incomplete-vector rejection.
- Native writes are visible before commit and preserve nested/outer rollback.
  The loader preserves C-API and SQL extension settings on success/failure and
  rejects a different preloaded build. Compiler scratch is per-build and disposed;
  successful binary publication is atomic and failed builds preserve prior bytes.
- Capacity regressions cover more than 100,000 aggregate vector chunks and lexical
  references, 100,001 journal records, 300 quota groups/1,200 tasks, counters above
  10,000 requests/64 GiB, more than 10,000 archive objects/source records/regions,
  large paging offsets, and native-int64 explicit stream budgets. Input/output
  byte bounds and actual configured quotas remain enforced.
- A database larger than 128 MiB and a retained artifact larger than the old
  16 MiB limit round-trip through streamed backup/restore. Manifest producer and
  reader share one bounded metadata contract. Verified v1/v2-to-v3 copies preserve
  originals and citations; raw-vector conversion does not call an encoder.
- Wheel and sdist install in clean environments on both Python versions. Base
  installs have no third-party runtime packages. Installed library/CLI, both
  optional extras, actual MiniLM, schema/typing/license/native-binary checks and
  source-distribution compiler inputs pass. No model weights, private data, test
  databases, compiled source-distribution artifacts or CI workflow are packaged.
- Actual API-30 MiniLM, complete source coverage, current generic SQLite scope
  queries, caller-owned CLI, example texts and backup/restore pass. Installed
  small-example query medians are approximately 7–10 ms; syscall-traced runs are
  slower. Traces contain no network or clone/clone3 calls, and thread count stays
  unchanged. This run uses example texts, not retained live-publisher originals.
- Real approved DNS/TLS/HTTPS passes separately on both Python versions: one
  example.com request and 400 wire bytes each. Python dependency audit reports no
  known vulnerabilities, skipping the unpublished editable first-party package.
  All sixty external `uv.lock` records are unchanged; its release-age policy stays
  intact. This audit does not certify the vendored native C source defect-free.

The synthetic capacity command creates one million 384-dimensional vectors and
selects the strongest match at the last entry, beyond every former corpus cutoff:

```sh
systemd-run --user --scope --quiet \
  --property=MemoryMax=8G --property=MemorySwapMax=0 --property=TasksMax=256 \
  --working-directory="$PWD" "$PWD/.venv/bin/python" "$PWD/scripts/accept_corpus.py"
```

| Python | Build (s) | First full query (s) | Repeat full query (s) | Last-100 scope (s) | Peak process RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3.13.15 | 5.325 | 2.056 | 2.018 | 0.299 | 148.0 |
| 3.14.4 | 5.816 | 2.191 | 2.133 | 0.299 | 151.2 |

Each database is 2,024,955,904 bytes. Queries validate only the query vector and
twenty returned vectors in Python; native SQLite performs the comparisons over
the complete selected corpus. Peak RSS includes construction and queries, not
only the query. The first query is not an OS-cold-cache measurement: construction
has just written the database. These are observed runs, not latency guarantees.
The engine is exact flat vec1 0.8, single-threaded, `toolsmith-native-1`; it is not
ANN. Synthetic vectors establish capacity, not million-document embedding quality.

The complete removed/retained restriction inventory is in [limits](limits.md).
No consumer, fleet, production store, registry publication or deployment changes
are part of this verification.

## Verified 0.1.0 implementation — 2026-10-11

The complete integrated sequence passes on Linux x86_64 with these two actual
environments. Both SQLite builds provide FTS5.

| Python | SQLite | Tests | Result |
| --- | --- | ---: | --- |
| 3.13.15 | 3.53.1 | 106 | All passed |
| 3.14.4 | 3.46.1 | 106 | All passed |

- Ruff format/check and strict Mypy pass for all 45 source/test/script files.
- Ten isolated test files run concurrently on 24 available cores (ten workers),
  with the verified 8 GiB/no-swap/256-task aggregate bounds. Every file has its own
  temporary fixture root; owned fixtures and processes are disposed before return.
- Wheel and sdist build successfully. Both install into clean environments, use
  the installed code rather than checkout imports, and pass CLI/library calls,
  schema/typing/license checks, source scope, exact citations and backup/restore.
- Base installations have zero runtime dependencies and no DNS package. Selecting
  the HTTP extra installs the pinned `dnspython` dependency successfully.
- Actual native DNS/TLS/HTTPS acquisition passes separately in both environments:
  one request, 400 response-body bytes, meaningful retained text and no retained
  raw HTML, with temporary state disposed. This is not publisher-wide certification.
- Dependency audits report no known vulnerabilities for installed third-party
  runtime, build and development dependencies. The unpublished editable Toolsmith
  package is explicitly skipped by the advisory lookup, not treated as an audited
  public-registry package.
- Final review verifies the single library/CLI path, one chunking implementation
  for writes/rebuilds, one cleanup validator, no product process/thread/server,
  no domain/fleet dependency, and no embedding/native-extraction placeholder.

Verification uses the local commands in this guide, not GitHub Actions CI/CD.
No registry publication or consumer/production deployment is part of these results.

## Integrated semantic addition — 2026-10-13

- All 178 tests pass on Python 3.13.15/SQLite 3.53.1 and Python 3.14.4/SQLite
  3.46.1, Linux x86_64. Ruff format/lint and strict Mypy pass for 60 files.
- Fifteen isolated test files run on 24 available cores, inside verified 8 GiB,
  zero-swap, 256-task scopes. Owned fixture roots are disposed by the runner.
- Wheel and sdist build; clean installed base, HTTP and semantic-extra acceptance
  passes. Installed wheel and sdist both execute actual MiniLM library/CLI calls,
  the news/agreement recipes, exact citations, generic SQLite and backup/restore.
  Base imports start nothing and require zero third-party runtime packages.
- Actual CPU MiniLM passes token-ceiling rejection, complete long-source coverage,
  page/clause ranking, isolated correction/invalidation and four previously retained
  ECB/BoE/BBC originals. No new publisher request, Luna turn or production mutation
  is performed by semantic acceptance. The sample summary declares no Luna provenance.
- The exact upstream API-30 header and all used native slots are checked. Actual
  syscall tracing records no network socket/connect or clone/clone3 during semantic
  acceptance. Thread count remains one and the caller environment is restored.
- Small-corpus warm query medians vary with host load/tracing (approximately
  6–28 ms in these runs); this is not a large-corpus performance guarantee.
- Correctness tests cover corrupt vectors/spans/profiles/references, atomic outer
  rollback, busy commits, stale workers, search-time source changes, read-only
  assets, zero metadata-only re-encoding and Unicode-whitespace pages.
- Installed third-party dependency audit reports no known vulnerabilities; the
  unpublished editable first-party package is skipped by advisory lookup. All 45
  pre-existing external lock records remain unchanged, with no age-policy exception.
- Native approved HTTPS acceptance still passes separately: one example.com request,
  400 wire bytes, temporary state disposed. No publisher-wide certification.
- Local installed native acceptance uses explicitly prepared exact assets and
  actual MiniLM, not just mocked encoders. No hosted automation is required.

WCBUBWHB/API conclusions are in [architecture review](architecture-review.md).
No fleet/consumer code, production store or runtime is deployed by this work.

## Generic capability coverage — 0.2.0, 2026-10-14

The [capability mapping](capability-mapping.md) covers fifty required generic
capabilities and consumer-owned exclusions. The complete integrated gates pass
on Linux x86_64 in both supported test environments:

| Python | SQLite | Tests | Result |
| --- | --- | ---: | --- |
| 3.13.15 | 3.53.1 | 269 | All passed |
| 3.14.4 | 3.46.1 | 269 | All passed |

- Ruff format/check and strict Mypy pass for all 90 source/test/script files.
  Twenty-four test files run isolated on 24 available CPU cores under verified
  8 GiB/no-swap/256-task aggregate limits; the runner disposes owned fixtures.
- Generic acceptance covers an actual 512 MiB original copied in blocks no larger
  than 64 KiB, exact byte limits, mutation/snapshot races, symlinks/FIFOs/hard links,
  no-overwrite publication and exact-file ZIP extraction failures. A 64 MiB+1 GZIP
  bomb is rejected, not silently returned as a prefix.
- Parsing tests cover JSON uniqueness/finite values, static HTML access gates and
  article identity, feed original/offset/UTC dates, duplicate counts and validation
  of omitted entries, compressed CSV counts/limits and ambiguous HTML tables.
- Caller-owned index tests cover phrase/term/amendment/blank/full-page cases,
  authorized current candidates before result limits, title/posting corruption,
  stale workers, cheap metadata with no vector reads, arbitrary row factories,
  source/derivative rollback and symmetric rejection of existing/partial schemas.
- Quota/journal tests cover group/task conservation, unknown charges, unchanged
  policy bindings, reboot and clock rollback, cooldowns across window rollover,
  quiesced counter transfer, tampered/incomplete records and partial-write rollback.
- Explicit archive-v1 to v2 migration tests preserve the original database bytes
  and exact text/file versions; corrupt shapes/objects, scope or collisions fail.
  Removed archive chunk writers and old parsing-type imports are rejected by
  architecture checks. There is no older runtime reader or index fallback.
- Wheel and sdist build and pass clean installed CLI/library/base/extras acceptance.
  Both installed formats execute actual MiniLM and caller-owned search commands,
  exact citations and backup/restore. Base dependencies remain zero; no private
  data, analysis, development fixtures, model weights or CI workflow is packaged.
- Actual API-30 MiniLM acceptance passes in both Python environments, checking the
  exact upstream header/slots, complete long-source coverage, oversized queries,
  caller-owned SQLite/CLI and no added worker threads/environment changes.
  Native syscall tracing records zero socket/connect or clone/clone3 calls.
- Actual approved DNS/TLS/HTTPS passes in both environments: one example.com
  request/400 response-body bytes each, with invocation state disposed. This is
  not authenticated-broker, browser or publisher-wide certification.
- Dependency audit reports no known vulnerabilities for installed third-party
  packages. Only the first-party editable package is skipped. All 60 external
  lock records remain unchanged; only Toolsmith's own version becomes 0.2.0.

This run uses synthetic/consumer-shaped examples, not newly collected publisher
originals or Luna execution. Small-corpus warm query observations (approximately
6–16 ms here) do not establish unlimited-corpus performance. No consumer migration,
registry publication or production deployment is performed. The complete directory
reorganization remains a [proposal](proposed-layout.md), not import aliases.

## Public MIT licensing update — 2026-10-13

The owner authorized Toolsmith as a public MIT-licensed project. This changes
licensing, distribution metadata, documentation and acceptance checks only;
private storage protections and all library/runtime behavior stay unchanged.

- All three affected architecture tests pass on Python 3.14.4. Ruff format/lint
  and strict Mypy pass for all 60 source/test/script files. The frozen lock check
  passes with no dependency record changes.
- Both rebuilt wheel and sdist include the exact repository LICENSE, declare
  `License-Expression: MIT` and `License-File: LICENSE`, and have no private-upload
  classifier. Clean installed CLI/library acceptance passes for both formats.
- Base installs still have zero runtime dependencies; both optional extras install
  successfully. Archives exclude stores, credentials, analysis, test fixtures and
  model weights. Registry publication and consumer deployment are not performed.
- The earlier complete 178-test and real-model gates apply to the unchanged runtime
  implementation. They were not rerun for this licensing/documentation-only edit.

## HTML inspection boundary — 0.4.1, 2026-10-17

Inspection no longer treats an unresolved body dialog as proof of a visible
access gate. Document-title access screens still fail before browser-owned code
runs. Static text reading retains all dialog/password/challenge refusals.
Browser-owning consumers pass computed-visible markup to that same reader.
The regression covers hidden-template inspection and unchanged static denial.

The complete bounded verification and installed wheel/sdist/base/HTTP/semantic
acceptance pass. No publisher request or generative model call is required for
this change. Actual browser acceptance remains consumer-owned.
