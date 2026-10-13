# WCBUBWHB architecture review — 2026-10-13

Scope: the initial optional library/CLI release, including semantic extraction.
Consumer fleets and production are unchanged. No deployment is claimed.

## Conclusions

- One library implementation owns each capability. CLI dispatch calls those same
  public functions. Generic semantic tables work in a caller-owned SQLite database;
  text-store integration is composition, not a second implementation/database.
- No server, daemon, process worker, thread worker, fleet-core dependency, skills,
  generative model API, domain taxonomy/news schema or financial rules are added.
- No compatibility alias, alternative model/backend, hidden download, fallback
  search or parallel old/new representation is retained. Initial unpublished
  schema construction changes directly; deployed consumer conversion remains
  owner-scoped, backup-first and forward-only.
- Public expected failures use the shared Result contract. Input types, byte/token
  bounds, exact references, profile identity, private filesystem ownership and
  authorized candidate/record/scan bounds are checked in their owners.
- Optional native packages load only when selected. Base installations remain
  dependency-free. Model bytes are exact pinned operator inputs; no model weights
  are packaged. Trusted native dependencies are not misrepresented as a sandbox.
- Encoding stays outside SQL transactions. Canonical source rechecks and expected
  prior digests protect publication. Source changes and derivative invalidation
  share a transaction; current queries cannot silently search old revisions.
- Original/page/source provenance remains exact and citable. Unchanged text reuses
  vectors after title/page corrections; blank Unicode-whitespace pages are retained
  but do not become unencodable index work. Coverage is separate from health.
- One transaction owner handles nested savepoints and owned transactions, including
  busy commits. Failed operations cannot leave an owned pending write to commit later.
- Integrity/backup verify finite unit vectors, complete spans and canonical bindings.
  Derived-only clear/rebuild never deletes originals, permissions or histories.
- Native C API version/slots are explicitly pinned and verified against the exact
  upstream header. Native resources close in reverse order. Startup telemetry is
  suppressed before creating an uploader/cache; process environment is restored.
  Actual acceptance verifies no added threads, sockets, connections or child creation.

## Verification and limitations

The complete evidence is in [verification](verification.md). Tests include mutable
source races, rollback/commit contention, corruption, source scope, Unicode/page
citations, optional dependency absence, installed CLI/library parity, both fleet
recipes, actual MiniLM and retained public-source originals.

Semantic similarity discovers candidate text; it does not prove legal/financial
claims, summary provenance, rights or collection completeness. English-only CPU
inference is deliberate. Exact bounded cosine search is not unbounded ANN or a
distributed retrieval service. Metadata is not OS isolation from same-user code.

Bad Bets keeps its current domain implementation until its owner explicitly
migrates to this library; there is no concurrent Toolsmith compatibility reader
for its old vector tables. No consumer code, production database or native history
is reset or upgraded by this work. Public distribution remains banned.
