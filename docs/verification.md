# Verification

This file documents reproducible gates. Release evidence is recorded after the
actual run; fixture results are not certification of every publisher/network.

## Full gate

```sh
uv sync --frozen --extra http
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

The pinned GitHub workflow runs the corresponding local gates; it has not been
claimed as a completed remote run. No registry publication or consumer/production
deployment is part of these verification results.
