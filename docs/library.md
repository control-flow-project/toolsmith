# Library interfaces

The [primitive recipes](primitives.md) cover `readers.read_xml`, `read_json_lines`,
`inspect_html`, `read_pdf`, `render_pdf_page`, `acquisition.batch.download_batch`,
`download_batch_async`, URL resolution, ZIP/gzip and batch indexed lookup.
All are optional; none owns source selection or application orchestration.
`acquisition.streams.DeadlineReader` is a raw socket I/O adapter for callers
that own their own authenticated protocol. It applies one absolute deadline to
buffered reads and owns no DNS, HTTP policy, credentials or connection setup.
Public acquisition continues to use the single aiohttp transport; the stream
adapter is not an alternate public downloader or response parser.
`sqlite.connect_database(path, create=False, write=False, timeout_seconds=0)`
opens a caller-owned connection using the canonical private-file validator.
Linux O_PATH metadata inspection preserves existing SQLite process locks;
ordinary filesystem reads/hashes of an active database must use SQLite's backup
API or wait until all connections are closed. The caller closes the connection
and owns schema, transaction and connection settings. `sqlite.open_database`
composes it with the standard index-connection settings.

See [caller-owned application integration](consumer-adoption.md) for SQLite
scopes, atomic approval/quota configuration and filesystem ownership.

The [capability map](capability-mapping.md) records the complete adoption boundary.
Generic file/tree/ZIP, parsing, literal/indexed search, semantic, journal and public
HTTP/quota APIs require no Toolsmith source store. The optional archive composes
those same functions. Use public index ports, not their private table names.

Application corrections keep the application's transaction: change canonical text
and `unwrap` both invalidations **inside** that transaction, so an expected failure
raises and rolls back the source write. Encode outside it; recheck canonical text
inside publication's write transaction and pass the exact previous digest. Caller
schema versions and row factories remain unchanged.

`lexical.find_text` preserves punctuation and caller-owned regions.
`lexical.search` performs explicit indexed FTS matching over authorized database scopes.
These are distinct query semantics, never fallback paths. Semantic `inspect_index`
is cheap bulk metadata; full vector/source validation is a separate explicit audit.

Generic journal payloads are bounded arbitrary JSON; event schemas, authority and
retention stay with the caller. One ASCII-escaped canonical hash format preserves
the reviewed generic record framing. No record is automatically discarded, and an
incomplete tail fails for explicit operator review rather than silently deleting it.

Distribution: `ctlflow-toolsmith`; import: `toolsmith`; command: `toolsmith`.
Public modules/functions are named exports. There is no dynamic plugin registry,
HTTP client for a Toolsmith service, skill installation or fleet integration.

| Module | Public operations |
| --- | --- |
| `toolsmith.result` | `Success`, `Failure`, `Result` |
| `toolsmith.files` | `read_bytes`, `write_new_bytes`, `replace_bytes`, `hash_file`, `copy_file`, `file_stamp`, `FileDigest`, `FileStamp`; explicit private directories, descriptors and locks |
| `toolsmith.paths` | `relative_components`, `relative_parent`, `relative_file` for canonical private descendants |
| `toolsmith.filesystem` | `inventory`, `sync_directory_tree`, `publish_directory`, `FileEntry` |
| `toolsmith.archives` | `list_archive`, `read_archive_member`, `pack_files`, `unpack_files`, `ArchiveEntry`, `MemberSource`, `MemberDigest`, `ArchiveReport` |
| `toolsmith.compression` | `expand_gzip` with an explicit expanded-byte ceiling |
| `toolsmith.readers` | `Document`, `TextPart`, `read_text`, `normalize_text`, `read_json`, `read_json_lines`, `read_html`, `inspect_html`, `HtmlInspection`, `HtmlLink`, `HtmlMetadata`, `HtmlStructuredData`, `read_feed`, `Feed`, `FeedEntry`, `read_xml`, `XmlDocument`, `XmlElement`, `XmlLimits`, `read_xml_records`, `read_pdf`, `PdfText`, `PdfPageText`, `render_pdf_page`, `PdfImage`, `decode_table`, `iter_table_rows`, `project_table`, `read_xls`, `XlsSheet`, `XlsCell` |
| `toolsmith.readers.content` | `validate_content`; PDF signature only, not extraction |
| `toolsmith.lexical` | `Source`, `Scope`, `initialize_index`, `inspect_index`, `indexed_scope`, `matching_scope`, `index_source`, `invalidate_source`, `search`, `search_batch`, `check_index`, `compile_query`, `Region`, `find_text` |
| `toolsmith.semantic` | `load_model`, `inspect_model`, `Source`, `Scope`, `prepare_connection`, `prepare_embedding`, `encode_query`, `initialize_index`, `inspect_index`, `inspect_coverage`, `indexed_scope`, `pending_references`, `publish_embedding`, `invalidate_embedding`, `relocate_embedding`, `clear_index`, `search_embeddings`, `search_batch`, `search_embeddings_batch`, `check_index`, `indexed_digest` |
| `toolsmith.search_batch` | `SearchQuery`, `EmbeddingQuery`, `QueryResult`, `SearchBatch`, `read_queries` |
| `toolsmith.acquisition.urls` | `resolve_url`, `resolve_urls`, `ResolvedUrl`; resolution does not authorize requests |
| `toolsmith.acquisition.batch` | `DownloadRequest`, `DownloadedFile`, `DownloadOutcome`, `DownloadBatch`, `download_batch`, `download_batch_async` |
| `toolsmith.acquisition.buckets` | `Bucket`, `BucketResult`, `run_buckets_async`; finite caller-selected acquisition with per-bucket spacing |
| `toolsmith.acquisition.transport` | `NativeResolver`, `NativeTransport`, `request_pinned`, `request_pinned_async`; bounded DNS and pinned HTTPS transport |
| `toolsmith.acquisition.client` | `HttpPolicy`, `FetchResponse`, `fetch_http`, `fetch_http_async` without an archive |
| `toolsmith.acquisition.config` | `read_http_policy`, `read_budget_policy` |
| `toolsmith.acquisition.budgets` | `BudgetPolicy`, `Reservation`, `BudgetStatus`, `inspect_budget`, `reserve_budget`, `reserve_budget_async`, `settle_budget`; asynchronous admission waits only for local spacing/slots within its deadline, never upstream cooldowns or exhausted quota |
| `toolsmith.acquisition.budget_import` | `BudgetSnapshot`, `GroupUsage`, `Usage`, `import_budget` for reviewed quiesced counters |
| `toolsmith.acquisition.configuration` | `Configuration`, `configure_budget`, `inspect_configuration`, `check_budget` for atomic caller configuration and charged limits |
| `toolsmith.journal` | `Record`, `read_journal`, `append_record` |

The following modules compose the **optional text archive**, not a generic storage
backend for consumer applications. Its parsing and indexing still use the same
libraries listed above.

`inspect_html` returns `links` as a tuple of `HtmlLink` values: literal `target`,
readable `label`, `relations`, optional `media_type` and `label_truncated`.
Relative targets, fragments and non-HTTP schemes remain untrusted metadata;
the caller must resolve and validate them against its source policy before
requesting anything. Navigation links are preserved even though navigation prose
is omitted from `text`. Hidden, advertising and template regions stay excluded.
No browser, network access or automatic following occurs. For example:

```python
from toolsmith.readers import inspect_html
from toolsmith.result import unwrap

inspection = unwrap(inspect_html(b'<main><a href="/article">Report</a></main>'))
link = inspection.links[0]
assert link.target == "/article" and link.label == "Report"
```

`read_feed` returns an explicit `next_url` for feed-level Atom `rel="next"`
links, including Atom links embedded in RSS channels. Relative links honor
inherited `xml:base`; article links use the same resolution. Conflicting next
pages fail instead of selecting one. The reader does not request another page.
Callers must authorize and account for each page and detect repeated URLs.
No next link does not prove the publisher exposes every article in that feed.

| Module | Archive operations |
| --- | --- |
| `toolsmith.storage.models` | `TextReference`, `FileReference`; archive document validation |
| `toolsmith.storage.database` | `initialize_store`, `inspect_store`, `StoreInfo` |
| `toolsmith.storage.text` | `put_text`, `inspect_text`, `list_text` |
| `toolsmith.storage.artifacts` | `put_file`, `inspect_file`, `read_file`, `export_file` |
| `toolsmith.storage.operations` | `operation_status`, `OperationStatus` |
| `toolsmith.retrieval` | `search_text`, `read_citation`, `SearchHit`, `Citation` |
| `toolsmith.acquisition.policy` | `read_policy`, `SourcePolicy` |
| `toolsmith.acquisition.limits` | `inspect_limits`, `LimitStatus` |
| `toolsmith.acquisition.http` | `acquire_http`, `resume_http`, `Acquisition` |
| `toolsmith.operations.backup` | `backup_store`, `restore_store`, `BackupReport` |
| `toolsmith.operations.integrity` | `check_integrity`, `rebuild_index`, `IntegrityReport` |
| `toolsmith.operations.cleanup` | `preview_cleanup`, `apply_cleanup`, `CleanupPlan` |

Operations validate boundaries and return typed `Result[T]`. `unwrap` and internal
`ToolsmithError` are composition helpers used by the CLI/implementation, not an
exception-based alternative public API. Do not bypass invariants with internal
`Store`/connection helpers or direct SQL/file writes.

```python
from pathlib import Path
from toolsmith.result import Failure
from toolsmith.storage.database import initialize_store
from toolsmith.readers.models import Document, TextPart
from toolsmith.storage.text import put_text

root = Path.cwd() / "local-store"
initialized = initialize_store(root, "sample")
if isinstance(initialized, Failure):
    raise RuntimeError(initialized.message)
document = Document("Report", (TextPart("Physical page 1", "Retained source words", 1),))
result = put_text(root, "sample", "report", document, "import-report-1")
if isinstance(result, Failure):
    print(result.code, result.message)
else:
    version = result.value.version
```

Stored physical pages and warnings describe supplied extraction, not certification
that the original was complete. Citation offsets count Unicode characters, not
UTF-8 bytes. Old versions remain exact; searches intentionally cover current
versions only. Request identities are collection-wide across text, files and HTTP.

The optional HTTP boundary accepts `Clock`, `Resolver` and `Transport` protocols
for deterministic integration/tests. The shipping composition uses bounded native
DNS/TLS/HTTPS. These are injected call boundaries, not alternative product paths
or runtime plugins. DNS approval and byte/deadline checks remain in acquisition;
custom callers remain responsible for their own transport's actual network behavior.

Raw `HttpPolicy` and archive `SourcePolicy` accept one to 32 exact public DNS
hosts. Typed and JSON policies normalize case, sort the hosts and reject duplicate
names after normalization; neither silently removes aliases. The raw HTTP CLI
rejects an existing or relative destination before fetching and publishes the
completed response atomically without replacing another file.

Importing the HTTP module does not import its optional DNS dependency. Missing
dependency fails on selected network acquisition, not on text/storage import.

## Caller-owned lexical index

```python
import hashlib
import sqlite3
from toolsmith import lexical
from toolsmith.result import unwrap

with sqlite3.connect(":memory:") as connection:
    connection.execute("PRAGMA foreign_keys = ON")
    unwrap(lexical.initialize_index(connection))
    source = lexical.Source("opaque-reference", "Exact source words", "Source")
    unwrap(lexical.index_source(connection, source, expected_digest=None))
    connection.execute("CREATE TABLE permitted_text (reference TEXT PRIMARY KEY, text_digest TEXT NOT NULL)")
    connection.execute("INSERT INTO permitted_text VALUES (?, ?)", (source.reference, hashlib.sha256(source.text.encode()).hexdigest()))
    matches = unwrap(lexical.search(connection, '"source words"', lexical.Scope("permitted_text")))
```

Initialization owns only derivative relations, not the application's canonical
tables or schema version. Both index initializers reject existing or partial
schemas rather than silently adopting or repairing them. The selected database table/view is caller-owned authorization;
digests exclude stale derivatives before ranking and limits. BM25 uses DB-wide
statistics, so separate room/tenant databases remain necessary for statistical
isolation. Cheap bulk status does not perform a full integrity audit.

Low-level descriptor/lock and SQLite transaction context managers are composition
primitives: they raise `ToolsmithError` on expected failures within an enclosing
public `Result` boundary. They do not supply a second implementation or runtime.

`toolsmith.semantic` exports the optional encoder and generic SQLite API;
`toolsmith.semantic.store` composes those functions with exact retained citations.
Importing either loads no optional native package or model. See
[semantic contracts](semantic.md) and [fleet integration](fleet-recipes.md).

`toolsmith.readers.read_xls(content, sheet=0, start=0, limit=1000)` returns `Result[XlsSheet]`. Rows contain `XlsCell(kind, value, number_format)`. Number/date values are exact decimal expansions of stored binary64 values, not formatted display strings. Text values remain literal Unicode; Boolean and error cells remain Boolean and integer error codes. Empty and formatted blank cells are distinguished with null values. `date_mode`, sheet names, merged ranges, total dimensions and explicit continuation accompany each page. Callers own any documented rounding, currency interpretation or calendar conversion. Cached formula results are read without formula extraction or recalculation; xlrd does not identify whether a cell came from a formula. The optional `xls` dependency is loaded only on an XLS call.

`read_xml_records` selects one exact element name or a nonempty tuple of distinct exact names in one parsing pass. Selected elements must not nest; all selected populations share full-document validation, namespace scope and structural budgets.

HTML `inspect_html` and `read_html` accept keyword-only `maximum_bytes`: default
4 MiB, explicit ceiling 8 MiB. They use the same parser and retain independent
structure, access/password and extracted-text limits. `XmlLimits.maximum_bytes`
defaults to 32 MiB and can explicitly reach 144 MiB; node/depth/field limits remain
separate. `read_text` and safe explicit `read_bytes` share that 144 MiB input
ceiling; their default budgets and file-write/storage limits are unchanged.
