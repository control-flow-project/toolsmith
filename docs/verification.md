# Verification

This file documents reproducible gates. Release evidence is recorded after the
actual run; fixture results are not certification of every publisher/network.

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
