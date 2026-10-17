# Tool contracts

All capabilities are optional. Public operations return typed `Success(value)`
or `Failure(code,message,retry_after_seconds)`; failures never silently become
successful, truncated or substituted work. Filesystem effects use explicit absolute
paths, not a global store. Applications own rights, permissions and source meaning.

## Generic capabilities: no text archive required

| Capability | Inputs and results | Limits and cautions |
| --- | --- | --- |
| Regular-file IO | Explicit path/byte bound → bytes, digest or private streamed copy | Buffered maximum 128 MiB, streaming requires an explicit byte budget (native signed-64-bit range); no-follow regular files; stable metadata; copy never overwrites |
| File/tree metadata | Explicit path/tree → stamp or relative file entries | No content hashing; default 10,000 total entries/1 GiB, depth 64; private tree excludes symlinks/special files |
| Mutable state / publication | Explicit bytes/path or same-parent staging/destination | Private atomic replacement for state; no-replace directory publication; no weakened rename fallback |
| Exact-file ZIP | Explicit selected files / expected member digests → archive or extracted directory | 10,000 files, 128 MiB/member, 1 GiB total, 4 MiB central directory, path depth 64; no encryption/special/extra members or partial publication |
| Text / JSON | Explicit UTF-8 bytes → parsing types or bounded JSON | Text default 4 MiB, configurable 128 MiB; JSON default 32 MiB, configurable 128 MiB; duplicate keys/nonfinite numbers rejected |
| Static HTML | Bytes and explicit text/article selection → `Document` | 4 MiB, 50,000 nodes, depth 128; access screens rejected; article identity/prose checked; table/dynamic-content warnings |
| RSS/Atom | Bytes, source URL and explicit entry limit → `Feed` | 2 MiB, 12,000 nodes, depth 32, 1,000 entries; validate omitted entries; duplicates/conflicts/counts/truncation; original/offset/UTC dates distinct |
| Tabular input | CSV/one ZIP-CSV/one GZIP-CSV → UTF-8 rows/projection | Compressed 32 MiB, expanded 64 MiB; comma/pipe/tab dialect; 256 columns, default 1,000,000 scanned rows; explicit larger budgets supported; strings only; exact scan/match/truncation counts |
| Response validation | Selected format/media type → explicit warnings | Wrong-format/access pages rejected; PDF signature only, not a PDF parser or OCR |
| Literal passages | Source/query/optional nonoverlapping regions → exact matches and counts | Source 128 MiB, 1,000 returned matches; no arbitrary region-count cutoff; punctuation and page-bounded context preserved |
| Caller-owned lexical index | SQLite + opaque refs/current digests → status, mutations or ranked hits | Source 8 MiB, database-resident authorized scope without a corpus-count ceiling, 1,000 result limit; terms/phrases/explicit FTS5; filtering before limits; BM25 DB-wide statistics |
| Caller-owned semantic index | Explicit model/SQLite/refs/current digests → vectors or exact ranked spans | Pinned offline English MiniLM; complete 256-token chunks; 4 MiB sources; native SQLite exact cosine queries with no candidate/chunk scan ceiling; metadata readiness is not a full audit |
| Raw public HTTPS | URL, approved policy, shared budget root, stable task → bytes and receipt | Per-response maximum 128 MiB (wire/expanded), 100 requests, 10 redirects, total I/O deadline at most 60 seconds; no credentials/proxies/cookies/automatic retry |
| Group/task budgets | Reviewed policies + explicit shared root → reserve/settle/status | Durable admission before I/O; unknown bytes stay charged; group/task conservation, spacing/cooldown/reboot controls; no global/distributed authority |
| Quota transfer | Reviewed quiesced snapshot → one new budget root | Preserve original period/counters/cooldowns; no source-specific decoder, state reset or concurrent old/new accounting |
| Generic JSON journal | Explicit private root/name and arbitrary JSON → verified records | 64 KiB event/32 MiB journal; one canonical hash framing; caller owns schema/retention; malformed existing tail is not silently removed |

Low-level descriptor/lock and transaction context managers are composition
primitives under these public `Result` boundaries, not an alternative backend.
See the [complete capability map](capability-mapping.md) for test-level evidence,
consumer exclusions and exact capacities.

## Separately optional text archive

| Capability | Inputs and results | Limits and cautions |
| --- | --- | --- |
| Text archive | Root, collection, item, document, request identity → exact version | 1,000 parts, 4 MiB combined text; physical pages/methods/warnings supplied by caller |
| File archive | Root, collection, bytes/name/media type, request identity → version | 128 MiB/file; no execution or publication |
| List/versions | Exact archive selection, limit/offset → retained/current references | At most 100 records; original versions remain citable |
| Current lexical search | Archive query/limit/offset → provenance-linked hits | Same generic lexical engine; at most 100 records |
| Citation | Exact version/part/start/length → provenance and text | Unicode character offsets; at most 16,384 returned characters; never another version |
| Retained HTTPS / resume | Approved retention policy + operation identity → retained result | Same raw HTTPS producer; archive admission/receipt owner; uncertain repeat GET disclosed |
| Backup / restore / migration | Verified source, collection and new destination | Default/max 20 GiB aggregate; no object-count cutoff; verify before publication; original retained; forward-only schema migration |
| Integrity / rebuild / cleanup | Explicit selected archive operation → report/preview-bound apply | Full audits are not normal reads; cleanup only inactive known staging, never originals/credentials |

Databases/indexes have no Toolsmith byte ceiling. The 128 MiB bound applies to
individual retained/exported artifacts, not database/index files. Backup/restore
stream databases under the aggregate 20 GiB budget. See [all limits and reasons](limits.md).
Neither GAAP nor Bad Bets is required to adopt this archive or its backup schema.
Generic ZIP and file/tree functions do not impose an agreement/document bundle.

## Policies

Raw HTTP uses `HttpPolicy` (network bounds only) and `BudgetPolicy` (shared
group/task admission). Included examples are `examples/http-policy.json` and
`examples/budget-policy.json`. Applications keep source approval, assignments,
job identities, content eligibility and optional browser/provider authorization.

The optional archive's `SourcePolicy` composes retention and those same generic
network/budget ports. Its format-one JSON requires `group`, reviewed `hosts`
and `retention` (`text_only` or `original`). Defaults remain a 1 MiB response,
5 requests, 3 redirects, 30-second deadline, 60-second window, 10 window requests,
8 MiB window bytes and zero minimum interval. This is an archive recipe, not a
second HTTP implementation or required consumer policy.

All cooperating transports selecting an upstream allowance share its state root,
group/task period and budget definition. Policy changes never silently reset
charges. Other roots or programs bypassing these tools are outside that guarantee.
No request cookie/credential is forwarded. A browser-style User-Agent does not
authorize access bypass or prove a source is public.

## Failures and CLI exit codes

`invalid_input` 2; `not_found` 3; `conflict` 4; `denied` 5; `limit` 6;
`unavailable` 7; `deferred` 8; `integrity` 9; `io` 10; `http` 11; `tls` 12.
Success exits zero. Known deferrals include an interval, not a promised successful
retry. Unknown cooldowns remain blocked for operator review; quota rollover cannot
shorten them. No retry/wait slot, daemon, automatic fallback or process helper.

Source content/titles remain untrusted caller data. Path-free tool receipts omit
incidental machine details, not arbitrary private strings supplied by callers.
Semantic similarity is navigation, not proof of facts/rights/analysis or summary
model execution. See [semantic contracts](semantic.md) for the exact native profile.
