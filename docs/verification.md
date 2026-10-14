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
