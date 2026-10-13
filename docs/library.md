# Library interfaces

Distribution: `ctlflow-toolsmith`; import: `toolsmith`; command: `toolsmith`.
Public modules/functions are named exports. There is no dynamic plugin registry,
HTTP client for a Toolsmith service, skill installation or fleet integration.

| Module | Public operations |
| --- | --- |
| `toolsmith.result` | `Success`, `Failure`, `Result` |
| `toolsmith.readers` | `read_text`, `read_html`, `read_feed`, `Feed`, `FeedEntry` |
| `toolsmith.files` | `read_bytes`, `write_new_bytes` |
| `toolsmith.storage.models` | `Document`, `TextPart`, `TextReference`, `FileReference` |
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
from toolsmith.storage.models import Document, TextPart
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

`toolsmith.semantic` exports the optional encoder and generic SQLite API;
`toolsmith.semantic.store` composes those functions with exact retained citations.
Importing either loads no optional native package or model. See
[semantic contracts](semantic.md) and [fleet integration](fleet-recipes.md).
