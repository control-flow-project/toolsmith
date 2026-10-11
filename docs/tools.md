# Tool contracts

Every selected capability is optional. Public calls return `Success(value)` or
`Failure(code, message, retry_after_seconds)`; unknown/programmer errors are not
silently converted into successful or substituted work. All effectful paths
require explicit absolute `Path` values, with no symlink ancestry or traversal.

| Capability | Inputs and results | Limits and cautions |
| --- | --- | --- |
| Text reader | UTF-8 bytes, title → `Document` | 4 MiB; exact source text, no PDF/OCR interpretation |
| HTML reader | UTF-8 HTML bytes, optional title → `Document` | 4 MiB, 50,000 nodes, depth 128; scripts/hidden/navigation omitted; largest article/main; completeness unverified |
| Feed reader | UTF-8 RSS/Atom, source URL, entry limit → `Feed` | 4 MiB, 50,000 nodes, depth 32, at most 1,000 returned entries; DTD/entities rejected; no article fetching |
| Text store | Root, collection, item, document, request identity → `TextReference` | At most 1,000 parts, 4 MiB combined text; supplied physical pages/warnings retained |
| File store | Root, collection, bytes, leaf name, MIME type, request identity → `FileReference` | 16 MiB each; no execution or publication |
| List/versions | Root, collection, optional item, limit/offset → references | At most 100 records; item selects all retained versions, otherwise current items |
| Search | Root, collection, query, limit/offset → `SearchHit`s | One to 32 literal AND terms; 100 records; exact 1,200-character chunks with 160-character overlap; current versions only |
| Citation | Root, collection, exact version/part/start/length → `Citation` | Zero-based Unicode character offsets, half-open end; at most 16,384 characters; never another version |
| HTTPS | Root, collection, network state, approved policy/URL, retention selection, request identity → `Acquisition` | 16 MiB maximum wire and expanded body, 100 requests/operation, 10 redirects/invocation, 60-second total I/O deadline; lower policy limits normally apply |
| Status/resume | Selected operation identity → record / explicit HTTP resume | Status starts nothing; retries uncertain GETs only under the original policy/input/remaining allowance |
| Backup/restore | Selected store/backup, collection, new destination → `BackupReport` | Default 256 MiB, configurable to 2 GiB, at most 10,000 referenced objects; restore verifies before creating destination |
| Integrity/rebuild | Selected store/collection → `IntegrityReport` | Explicit full retained-text/provenance/object/index checks; no whole-store hashing on normal text reads |
| Cleanup | Preview → exact `CleanupPlan` → explicit apply | Default staging age one day; at most 1,000 files; binds store/file identities; never retained objects or unknown files |

The database limit is 128 MiB. It is not a guarantee of unlimited archive capacity.
Text/artifact titles and content are user/source supplied: machine-neutral output
means tools omit incidental local paths, not that they redact arbitrary supplied
content. Sources remain untrusted data, never executed instructions.

## Source policy

JSON format one requires `group`, one to 32 exact DNS `hosts`, and `retention`:
`text_only` or `original`. Supported optional settings/defaults:

| Setting | Default |
| --- | ---: |
| `maximum_response_bytes` | 1,048,576 |
| `maximum_requests` | 5 |
| `maximum_redirects` | 3 |
| `deadline_seconds` | 30 |
| `window_seconds` | 60 |
| `window_requests` | 10 |
| `window_bytes` | 8,388,608 |
| `minimum_interval_seconds` | 0 |

The window must permit at least one maximum-sized response. All cooperating
callers using an upstream allowance must use the same group, policy and network
state root. Changing request IDs cannot reset that shared allowance. Different
roots/bypass programs are outside this local guarantee. Policy changes against
existing limit state fail, rather than silently deleting or resetting state.

`text_only` never retains a raw original. Acquisition can extract HTML/plain text
into an item; original-only acquisition stores bytes without pretending to parse
unsupported content. Reader failure does not yield a claimed completed document.
Article discovery and supplied publication dates remain distinct from retrieval
and recording times. No source catalog or model accounting is imposed.

## Failures and CLI exit codes

`invalid_input` 2; `not_found` 3; `conflict` 4; `denied` 5; `limit` 6;
`unavailable` 7; `deferred` 8; `integrity` 9; `io` 10; `http` 11; `tls` 12.
Success exits zero. `deferred` includes a retry interval when known, not a promise
that a retry will succeed. Contention, policy/source cooldown and resource failure
are ordinary bounded outcomes. No automatic retry loop, wait slot or fallback exists.
