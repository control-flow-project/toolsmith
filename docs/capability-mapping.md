# Consumer capability mapping

Reviewed 2026-10-13/14. Toolsmith implementation target: **0.3.0**. Consumer
snapshots: GAAP agents `52c2cc7`; Bad Bets agents `08e4461`. Neither consumer is
modified, installed or deployed by this work. Inspection covers their local tool
interfaces and owning modules, not a certification of every provider or analysis.

## Adoption contract

Toolsmith is optional for a fleet. Once a project adopts it, replace the applicable
generic implementation completely, remove its imports/dependencies/old commands,
and keep one implementation. Do not retain a backend selector, alias, fallback or
old/new path. A domain CLI may compose library functions; it must not spawn the
Toolsmith CLI. A project can install only the base package or selected extras.

Neither GAAP nor Bad Bets needs Toolsmith's optional text archive. Both already
own their canonical source records and databases. Generic indexes use their
caller-owned SQLite connection and opaque source references. Generic HTTP returns
bytes and receipts without creating a source archive. There is no mandatory
dependency from Crossfire/fleet setup, message delivery, history or lifecycle.

## Required generic capabilities and evidence

Every row names a real use, its current public library owner and executable tests.
Tests without a live provider establish contracts, not publisher certification.

| ID | Requirement and consumer use | Public owner | Verification |
| --- | --- | --- | --- |
| F01 | Stable, bounded, no-follow regular-file reads; both consumers | `files.read_bytes` | `test_files.py`, `test_generic_files.py` |
| F02 | Stream large originals without loading the entire file; GAAP PDF / both backups | `files.hash_file`, `files.copy_file` | `test_large_file_copy_is_streamed_exact_and_private`; read-size/mutation/collision controls |
| F03 | Match the inventory snapshot before copying; Bad Bets backup mechanics | `files.file_stamp`, `copy_file(expected_stamp=...)` | `test_inventory_snapshot_does_not_copy_changed_sources` |
| F04 | Private descriptor-pinned directories, file permissions, hard-link/symlink/special-file denial | `files.private_directory`, `private_file`, `directory_lock` | `test_files.py`, `test_tree_rejects_symlinks_special_files_and_unbounded_directory_count` |
| F05 | Explicit atomic mutable state writes, not artifact overwrite | `filesystem.replace_bytes` | `test_private_tree_and_atomic_publication_are_generic` |
| F06 | Bounded metadata-only directory inventory; application chooses included areas | `filesystem.inventory` | Private tree, special files and directory-count tests; no content hashing |
| F07 | Explicit tree durability and atomic no-replace publication | `filesystem.sync_directory_tree`, `publish_directory` | Publication/collision tests; Linux `renameat2`, no weakened fallback |
| A01 | Exact selected-file ZIP creation, not a document-specific bundle schema | `archives.pack_files` | `test_archives.py`: Unicode/blank pages, paths, collisions, streaming |
| A02 | Exact expected file set, digests, member types and byte-bounded ZIP extraction | `archives.unpack_files` | Corrupt/encrypted/symlink/unexpected/digest/prefix/expansion controls; no partial publication |
| P01 | Strict UTF-8, JSON uniqueness, finite numbers and bounded structures | `readers.read_text`, `read_json`; `validation` | `test_readers.py`, `test_validation.py`, `test_generic_readers.py` |
| P02 | Static visible HTML, omitted scripts/hidden/noise content, table warnings | `readers.read_html(selection="text")` | Static extraction/noise/hidden/table tests |
| P03 | Intended article identity, substantial prose and ambiguity rejection; Bad Bets | `readers.read_html(selection="article")` | `test_article_title_selection_ambiguity_and_table_warning` |
| P04 | Do not parse login, challenge, subscription/password dialogs as article data | Shared `readers.html_dom` access checks | `test_html_rejects_active_access_gates_without_bypass` |
| P05 | RSS/Atom unambiguous fields/links, bounded XML, no DTD/entities or excessive escapes | `readers.read_feed` | Feed negative/ambiguous/conflict/structure/escape tests |
| P06 | Preserve original publication/update values, source offsets and UTC separately | `FeedEntry` | `test_feed_retains_publication_and_update_offsets_and_unknown_dates` |
| P07 | Discovery counts, identical lead deduplication and explicit truncation | `Feed` | `test_feed_duplicate_counts_truncation_and_omitted_entry_validation`; no article fetching or inferred dates |
| P08 | CSV, single-member ZIP-CSV and single-member GZIP-CSV; Bad Bets reports | `readers.decode_table` | Archive path/encryption/format/extra-member/expansion tests |
| P09 | Bounded row iterator, headers, widths, exact filters/projection and complete scan counts | `iter_table_rows`, `project_table` | Bad rows/headers/row limits and `scanned/matched/truncated` assertions |
| P10 | HTML/PDF/image table interpretation stays with the consumer LLM | No deterministic HTML table extraction API or CLI remains | Ordinary source text and original artifacts remain available; removed table form is rejected |
| P11 | Wrong-format HTML, access screens, finite JSON and PDF signature-only checks | `readers.content.validate_content` | Response-format tests; PDF parsing is explicitly not claimed |
| L01 | Punctuation-preserving literal occurrences and exact offsets; Bad Bets document search | `lexical.find_text` | `test_literal_search_preserves_punctuation_regions_counts_and_offsets` |
| L02 | Caller-selected regions so context does not cross a page/region boundary | `lexical.Region` | Same test; physical-page interpretation remains caller-owned |
| L03 | Caller-owned SQLite lexical derivatives, complete Unicode chunks, blank pages | `lexical.initialize_index`, `index_source` | `test_caller_indexes.py`: pages/amendments/blank/full-source tests |
| L04 | Distinguish literal terms, quoted phrases and explicit FTS5 syntax | `lexical.compile_query`, `search` | Phrase vs separated words; the archive calls the same engine |
| L05 | Authorized current candidate refs/digests before ranking, limits and offsets | `lexical.Scope`, `search` | Higher-ranked unauthorized source is excluded before `LIMIT 1`; missing/stale counts |
| L06 | Expected-previous-digest publication, invalidation and explicit integrity checks | `index_source`, `invalidate_source`, `check_index` | Stale worker, corruption and outer-transaction rollback tests |
| S01 | Pinned offline English MiniLM, one CPU calling thread, no worker/download/GPU fallback | `semantic.load_model`, `inspect_model` | `test_semantic_model.py`, `test_semantic_native.py`, native acceptance |
| S02 | Complete 256-token chunks with overlap and exact canonical spans | `semantic.prepare_embedding`, `encode_query` | Chunk tests, actual-model long-source coverage and oversized-query rejection |
| S03 | Generic exact cosine retrieval over caller-authorized current representations | `semantic.search_embeddings` | Filtered headline/body/summary-shaped tests, missing/stale/corrupt controls |
| S04 | Cheap bulk readiness without loading source bodies or vectors | `semantic.inspect_index` | Query trace in `test_bulk_semantic_metadata_does_not_read_vectors_or_canonical_text` |
| S05 | Metadata/reference changes reuse existing vectors without inference | `semantic.relocate_embedding` | Public relocation tests and existing archive metadata-only reuse tests |
| S06 | Invalidate corrections, compare expected digest, clear only derivatives | `invalidate_embedding`, `publish_embedding`, `clear_index` | Outer rollback, stale worker, application data survives clear |
| S07 | Full vector/profile/span/source audit is a distinct explicit operation | `semantic.check_index`, `indexed_digest` | Corrupt vectors/profiles/spans/source tests; readiness deliberately is not an audit |
| D01 | Do not commit/rollback unrelated writes or change schema version/row factory; reject existing/partial derivative schemas | Shared SQLite savepoints and cursor ownership | Atomic source/derivative rollback, arbitrary row-factory, initialization symmetry and busy-commit tests |
| H01 | Archive-independent bounded approved HTTPS; both public-source workflows | `acquisition.client.fetch_http` | `test_independent_http_uses_canonical_routing_without_archive`; native HTTPS acceptance |
| H02 | Public DNS, pinned address, original-host TLS, redirect rechecks, no proxy/cookie/credential forwarding | Same transport/URL owner | `test_http.py`, `test_transport.py`, `test_policy_limits.py`; native approved source |
| H03 | One deadline, compressed/expanded/total byte limits and no automatic retry loop | `HttpPolicy`, transport | Slow-read/gzip/framing/deadline/redirect/request-cap tests |
| H04 | Durable admission hook lets the consumer keep its existing job/receipt owner | `fetch_http(before_request=...)` | Failure increments admission before I/O; existing archive recovery/replay tests |
| Q01 | Shared group and task request/byte reservations for HTTP and external browser operations | `acquisition.budgets` | Cross-source task conservation and exhaustion tests |
| Q02 | Reserve before I/O; uncertain usage stays charged; settle only known received bytes | `reserve_budget`, `settle_budget` | Crash/unknown-charge/reservation-mismatch/counter-corruption tests |
| Q03 | Source spacing and server cooldowns, including unknown/unrepresentable ends | Same budget owner | Long Retry-After/unknown cooldown/window rollover tests |
| Q04 | Reboot/clock rollback do not reset allowances or shorten the original period | Same budget owner, controlled clocks | Reboot/elapsed-period/rollback tests |
| Q05 | Adoption carries existing reviewed counters/cooldowns without clearing quotas | `budget_import.import_budget` | Quiesced import, conservation, current-period and empty-destination tests |
| J01 | Generic bounded hash-linked JSON journal; caller owns event validation/retention | `journal.read_journal`, `append_record` | Domain-neutral Unicode event, tamper/tail and partial-write rollback tests |
| T01 | Optional text/file archive, exact immutable versions, citations, permissions and operation IDs | `storage`, `retrieval`; higher-level composition | Existing store/CLI/maintenance/recovery tests; no duplicated lexical engine |
| T02 | Verified backup/restore/integrity/rebuild/preview-bound staging cleanup | `operations` | Existing maintenance/corruption/restore/change/symlink tests |
| T03 | Explicit archive-v1/v2 to v3 copy migration, original unchanged, exact versions preserved | `storage.migration.migrate_store` | `test_archive_migration.py`; bad schema/object/scope/collision tests |
| C01 | Same library in installed CLI, with caller-owned `--database/--sources`, metadata-only `--references` and no archive | `cli.indexes`, `search lexical/semantic` | `test_standalone_cli.py` and installed wheel/sdist acceptance |
| C02 | Standalone raw HTTPS receipt/file, readers and streaming filesystem commands | CLI composition only | Generic CLI tests and installed acceptance; source paths not echoed in receipts |
| X01 | Optional zero-dependency base, selected extras, no services/threads/helper processes/domain code/CI | Package boundaries and metadata | Architecture tests, clean installs, native thread checks and artifact audit |

## What remains consumer-owned

These are exclusions by ownership or the approved architecture, not missing generic
implementations to copy into Toolsmith.

| Consumer modules / responsibility | Keep there | Use Toolsmith for |
| --- | --- | --- |
| GAAP `agreement_tools/manifest.py` | Agreement manifest, originals, page numbers, OCR/native method/warnings, tool versions | Validators, stable file IO/digests |
| GAAP `extraction.py`, `native.py` | Poppler/Tesseract process lifecycle, OCR routing, extraction assurance | File staging/copy only; no fake native parser |
| GAAP `artifacts.py` | Approved exact agreement handoff set, bundle manifest and room/recipient access | Generic exact-file ZIP APIs |
| GAAP `retrieval.py` | Exact room binding, case/source/amendment/page relations, full page reads and displayed provenance | Generic lexical engine in the same case DB |
| GAAP website, fleet/role/skill definitions | Deployment, TLS/Element, agent quality, model options, identity/routing/security | None required; optional domain CLI composition |
| Bad Bets `articles.py`, `feed_discovery.py`, `response_content.py`, `tables.py`, `documents.py` | Preserved-original checks, news insertion policy, derived source meaning, physical-page mapping | Generic DOM/feed/format/tabular/literal search APIs; remove their generic copies |
| Bad Bets `data_acquire*`, `request_gate.py`, `browser*`, `data_browser*` | Reviewed sources/purpose/assignment/jobs, browser lifecycle, app receipts and selection | Generic approved public HTTP and one shared group/task quota engine |
| Bad Bets `text_retrieval/*` | Nothing after semantic adoption | Replace completely with public semantic APIs and generic CLI; remove Torch/backend copies |
| Bad Bets `data_news*`, `news_schema.py`, `news_migration.py` | One current article/URL, canonical headline/body/latest valid Luna summary, jobs/claims/tags/dates/entities, correction eligibility and query pagination | Public index state/publish/invalidate/query/audit ports; no private-table SQL |
| Bad Bets `data_files.py`, basic portions of `inputs.py`, `store.py`, `journal.py` | Included backup areas, evidence/event schemas and source-approval semantics | Generic descriptors/validators/inventory/IO/publication/journal; domain composition only |
| Bad Bets `data_backup.py`, `data_operations.py`, data schemas/migrations | Consistent multi-store backup manifest, research/news DB checks and restore activation | File/tree primitives and generic index audit; Toolsmith archive backup is not their backup |
| Bad Bets `kite*`, broker credentials/login/transport/rate rules | Authenticated provider-specific requests and private credential custody | No replacement by credential-free public HTTPS; this capability is explicitly outside its contract |
| Bad Bets market/reference/ownership/daily/option/portfolio/strategy/report modules | Provider parsing, financial definitions/calculations, evidence policy, charts/reports and publication | Generic tabular/JSON/file primitives only; financial logic is not copied |
| Both browser/native-process supervisors and Crossfire runtime integration | Required subprocess ownership, fleet lifecycle, approvals, identity, delivery, telemetry and Matrix permissions | Nothing mandatory; never move core runtime into Toolsmith |

## Capacity, safety and evidence limits

- Streaming requires an explicit signed-64-bit byte budget. Buffered
  reads support up to 128 MiB. ZIP member/total limits are 128 MiB/1 GiB, 10,000
  members and 4 MiB central directory. No prefix is silently returned on overflow.
- Generic CSV compressed/expanded input is 32/64 MiB; default 1,000,000 rows with larger explicit budgets,
  256 columns and explicitly bounded projections. Data remains strings.
- Generic lexical sources support 8 MiB and database-resident authorized scopes without a corpus-count cutoff; physical
  pages and full canonical text remain caller-owned. Search hits are exact spans.
  BM25 uses database-wide statistics: a candidate list is not corpus-statistical
  isolation. GAAP must retain its exact-room database boundary.
- Semantic sources remain 4 MiB and queries 256 tokens. A native SQLite exact
  vector index searches the complete authorized relation, including million-entry
  corpora, without candidate/chunk scan ceilings. Output remains at most 100
  references. Consumer article grouping remains consumer-owned. The synthetic
  capacity check is not million-document semantic-quality or multilingual certification.
- Readiness is metadata-only. Full integrity audits intentionally cost more.
  Hashing is a tool-side intake/transfer/audit operation, not repetitive model-led
  bookkeeping. Directory inventory does not hash contents; CLI source changes
  use descriptor metadata rather than reparsing the whole corpus per publication.
- Generic journals have one ASCII-escaped canonical hash format, arbitrary JSON
  payloads, 64 KiB events and a 32 MiB journal bound. They are not automatically
  pruned; event meaning and retention belong to the caller. A hash chain detects
  damage, not malicious same-user rewriting or producer authority.
- Borrowed SQLite connections retain their application schema version, transaction
  and row factory. The library owns only its declared derivative relations. Call
  `unwrap` **inside** the outer application transaction so an expected failure
  raises and rolls back the source correction; do not return a failure and commit.
- Public HTTPS is not an authenticated broker client or browser. Models/assets
  are explicitly prepared by operators. No compatibility Torch path is retained.
- Source/classification/permission filters precede ranking. Metadata is not OS
  isolation from arbitrary processes under the same account. Caller authorization
  and publication decisions cannot be replaced by Toolsmith reference labels.

## Migration actions

GAAP: keep its current document CLI and application schema; replace generic file,
ZIP and lexical implementations, update tests/skills/install documentation, forward
migrate its case indexes with a verified backup, preserve full page/method/warning
lookups, and remove old generic helpers. Do not require the Toolsmith text archive.

Bad Bets team: preserve canonical research/news/evidence stores, source approval,
Luna-summary eligibility and filtered representation selection. Replace local
`text_retrieval` and its generic CLI/dependencies; do not reinterpret Torch vectors
as the new ONNX profile. With verified backup and quiesced writers, remove old
derivative tables and rebuild from retained canonical text through public APIs.
Replace public acquisition/parsing/file/journal mechanics, carry existing reviewed
quota counters/cooldowns using `import_budget`, and remove superseded copies.
Keep broker/browser/native-process and domain application behavior where owned.

Acceptance must run each consumer's actual CLI and production-shaped stores in
isolated fixtures before activation. This Toolsmith review is not their completed
migration or deployment. See the [proposed full layout](proposed-layout.md) for the
next physical module organization; no old-path import aliases are proposed.
