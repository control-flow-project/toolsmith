# Caller-owned applications

Toolsmith is optional. Adopting consumers call its public library, remove their
superseded generic implementation and do not require its optional text archive.

| Consumer | Application ownership | Toolsmith ownership |
| --- | --- | --- |
| Agreement tools | PDF/OCR processes, manifests, physical pages, extraction warnings, room binding and legal interpretation | File IO, exact ZIP transfer, lexical derivatives |
| Research tools | Source approval, native browser/broker headers/processes, prices, canonical articles, summary eligibility and reporting | File IO, CSV/feed/static HTML formats, journals, DNS/TLS/body primitives, quotas, lexical/native vector derivatives |

Toolsmith does not approve a publisher, summarize news, interpret an HTML table
or operate a browser. Native browser adapters may use low-level TLS/body primitives
with their own reviewed headers; `fetch_http` remains cookie/credential-free.

## SQLite

`semantic.prepare_connection` loads vec1 without creating tables or changing
the schema version, row factory or transaction owner. Use it before preparing
caller schemas that include `semantic.SCHEMA_SQL`.

`Scope` selects a table/view exposing unique `reference` and `text_digest` columns.
The application owns source eligibility and access. Filters run in SQLite before
ranking; do not hydrate Python candidate dictionaries or impose corpus cutoffs.
See `examples/caller-owned-indexes.py` for an executable example.

`lexical.matching_scope` exposes all matching references/digests for application
counts and pagination, without a hidden hit limit. `lexical.indexed_scope` and
`semantic.indexed_scope` expose complete metadata matches. These projections are
not authorization decisions or full integrity audits. `semantic.inspect_coverage`
reports matching chunk/vector-payload bytes, not physical database allocation.

Invalidate derivatives and publish lexical text inside the canonical correction's
transaction. Encode semantic text outside write transactions, recheck its source
under the application guard and publish with the captured previous digest. Call
`unwrap` inside the transaction so failures roll back, rather than committing a
source-only correction. Full audits remain explicit.

## Approval and quotas

`configure_budget` atomically stores opaque caller configuration and quota
counters. The caller validates configuration and derives `BudgetPolicy` values;
Toolsmith neither understands nor grants application permissions.
`inspect_configuration` returns the value and canonical digest for reviewed
replacement. A stale/missing digest rejects the whole update.
Pass that digest as `expected_configuration_digest` to `reserve_budget`; the
configuration is checked again under the reservation's write lock. This prevents
a concurrent approval edit from authorizing a request with a stale host selection.
Readers and writers lock the same pinned directory descriptor. Lock contention
returns `deferred`; it does not mutate or misclassify an atomically replaced file.

Updates cannot erase usage, remove charged groups, shorten a charged period or
change limits with outstanding reservations. Lost state is not silently recreated.
`check_budget` validates without writing. `import_budget` accepts explicit reviewed
current counters, periods and cooldowns into an empty selected root. It does not
read consumer-specific state files or another schema. Unknown interrupted usage
stays charged. Preserve original stores and verified backups.

## Files and readers

Collection roots are private. Explicit output files are 0600; atomic replacement
also requires a caller-owned parent not writable by others. Relative files traverse
only canonical private descendants. Truncation follows type/ownership/mode/link
checks. No-replace publication uses `renameat2`; readers never observe temporary
hard-link aliases. `files.replace_bytes` creates no implicit lock file: callers own
write coordination and compare-and-swap semantics.

`inspect_html` returns visible text, title, content-root/password-control signals
and resource-bearing element counts, not actual browser request counts.
Inspection rejects document-title access screens before source scripts run, but
does not decide whether body dialogs are CSS-visible. Static `read_html` rejects
unresolved access dialogs. A browser-owning consumer supplies its computed-visible
DOM to `read_html`; a hidden template is not an active login gate. Inspection's
password-control signal describes raw markup, not a visibility assertion.
`read_feed` preserves original/resolved links, raw/source-aware/UTC dates, feed kind
and duplicate counts. Consumers own URL normalization and publisher acceptance.
Neither reader certifies source completeness.

## Application input limits

Applications enforce their own format-specific admission limits before calling
generic readers, copies or ZIP operations. The agreement and research consumers
limit source PDFs to 32 MiB (33,554,432 bytes); that PDF policy remains theirs,
not a format-specific rule in Toolsmith. The generic 128 MiB ZIP-member ceiling
remains unchanged and does not authorize larger PDFs. Derived text, aggregate
bundles and database backups retain their separate budgets.
