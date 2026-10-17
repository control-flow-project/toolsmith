# Library interfaces

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
| `toolsmith.files` | `read_bytes`, `write_new_bytes`, `hash_file`, `copy_file`, `file_stamp`, `FileDigest`, `FileStamp` |
| `toolsmith.filesystem` | `replace_bytes`, `inventory`, `sync_directory_tree`, `publish_directory`, `FileEntry` |
| `toolsmith.archives` | `pack_files`, `unpack_files`, `read_archive_member`, `MemberSource`, `MemberDigest`, `ArchiveReport` |
| `toolsmith.readers` | `Document`, `TextPart`, `read_text`, `read_json`, `read_html`, `read_feed`, `Feed`, `FeedEntry`, `decode_table`, `iter_table_rows`, `project_table` |
| `toolsmith.readers.content` | `validate_content`; PDF signature only, not extraction |
| `toolsmith.lexical` | `Source`, `Scope`, `initialize_index`, `inspect_index`, `index_source`, `invalidate_source`, `search`, `check_index`, `compile_query`, `Region`, `find_text` |
| `toolsmith.semantic` | `load_model`, `inspect_model`, `Source`, `Scope`, `prepare_embedding`, `encode_query`, `initialize_index`, `inspect_index`, `inspect_coverage`, `pending_references`, `publish_embedding`, `invalidate_embedding`, `relocate_embedding`, `clear_index`, `search_embeddings`, `check_index`, `indexed_digest`, `migrate_index` |
| `toolsmith.acquisition.client` | `HttpPolicy`, `FetchResponse`, `fetch_http` without an archive |
| `toolsmith.acquisition.config` | `read_http_policy`, `read_budget_policy` |
| `toolsmith.acquisition.budgets` | `BudgetPolicy`, `Reservation`, `BudgetStatus`, `inspect_budget`, `reserve_budget`, `settle_budget` |
| `toolsmith.acquisition.budget_import` | `BudgetSnapshot`, `GroupUsage`, `Usage`, `import_budget` for reviewed quiesced counters |
| `toolsmith.journal` | `Record`, `read_journal`, `append_record` |

The following modules compose the **optional text archive**, not a generic storage
backend for consumer applications. Its parsing and indexing still use the same
libraries listed above.

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
| `toolsmith.storage.migration` | `migrate_store`; verified forward copy, original unchanged |

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
