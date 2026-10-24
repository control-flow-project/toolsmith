# Toolsmith

- [Caller-owned application integration](docs/consumer-adoption.md)

The [capability mapping](docs/capability-mapping.md) records which generic parts
GAAP, Bad Bets and other consumers can replace, the required tests and the domain
responsibilities that stay with them. Adoption is optional; an adopting project
uses one generic implementation, not a selectable local/Toolsmith backend.
The [full proposed layout](docs/proposed-layout.md) separates filesystem, parsing,
HTTP, search, journals and the optional text archive; it is a proposal, not aliases.

## Use your own application database

No Toolsmith archive is needed for parsing, public HTTPS or caller-owned indexes.
Create a private working directory explicitly; then use the included generic
source examples and an application-owned `permitted_text` table/view with the installed package:

```sh
toolsmith --json search lexical init --database /absolute/private/application.sqlite3
toolsmith --json search lexical index --database /absolute/private/application.sqlite3 --sources /absolute/caller-owned-sources.json
toolsmith --json search lexical query '"Restricted Payments"' --database /absolute/private/application.sqlite3 --scope permitted_text
toolsmith --json search lexical status --database /absolute/private/application.sqlite3 --scope permitted_text
```

The library uses the same functions. Consumers keep canonical text, page/article
metadata, permissions and corrected-source eligibility. Generic references are
not access grants, and search snippets are not substitutes for the originals.
Semantic indexing/query additionally requires the optional semantic extra and
explicitly prepared pinned model assets; status does not load a model or bodies.

Raw HTTPS uses `http request URL --policy FILE --budget-policy FILE --network-state
DIR --task ID --destination FILE`, with the included policy examples. It returns
a bounded receipt and an explicit file, not another source database. Application
approval, permitted formats, job identity and publication remain with the caller.

MIT-licensed, optional generic libraries and CLI tools maintained by Control Flow.
Use none, one or several capabilities. Toolsmith is not part of fleet setup,
message delivery, sessions or history.

**Libraries and short-lived CLI commands only. No servers, daemons, background
workers, threads or helper processes.** Installing or importing it starts nothing.
The CLI calls the same validated library functions that applications import.

## Available tools

- Streaming regular-file hash/copy, private tree inventory/publication and exact-file ZIPs.
- UTF-8/strict JSON/JSONL, XML, static HTML with links/metadata, CSV and RSS/Atom readers.
- Optional in-process PDF text extraction and PNG page rendering; no OCR or table interpretation.
- URL resolution, ZIP inspection/exact-member reads and bounded gzip decompression.
- Literal passages and lexical indexes over caller-owned sources and authorized database scopes.
- Optional offline English MiniLM embeddings and semantic search, with complete
  token-aware chunks, exact source spans and caller-owned SQLite integration.
- Optional approved HTTPS responses with bounded DNS/TLS, redirects, compressed
  responses and persistent shared group/task budgets.
- Concurrent file-download batches, serial within each caller-defined quota group.
- Batch lexical/semantic queries with one authorized coverage snapshot per batch.
- Generic bounded JSON journals; applications own event meaning and retention.
- A separately optional text/file archive: exact versions/citations, acquisition
  receipts/recovery, verified backup/restore, integrity and staging cleanup.

Browser automation, process-based PDF/OCR helpers and hybrid retrieval are
not implemented. No substitute or placeholder is provided. Skills, source-specific
connectors, domain analysis, financial calculations and fleet runtime remain with
their existing owners.

## Install and use

Python 3.13+ is required. Linux and SQLite 3.44+ with FTS5 are required only for persistence
and safe filesystem operations. The base distribution has **no runtime dependencies**.
The distribution is `ctlflow-toolsmith`; the command and import are `toolsmith`.
Source and built artifacts are MIT-licensed. There is no PyPI or npm release yet;
build from the public repository or install a built platform-specific wheel.
Source builds require a C compiler. The native extension is compiled at build
time, never by importing or invoking the package.

```sh
git clone https://github.com/control-flow-project/toolsmith.git
cd toolsmith
uv build --no-sources
python3 -m venv .venv
.venv/bin/python -m pip install dist/ctlflow_toolsmith-0.5.0-py3-none-*.whl
.venv/bin/toolsmith --json capabilities
.venv/bin/toolsmith --root "$PWD/local-store" --collection sample store init
```

For network acquisition, install the same wheel with its `http` extra.
No global configuration, data directory, credentials, model download or runtime
activation is selected by installation.

```python
from toolsmith.readers import read_text
from toolsmith.result import Failure

result = read_text(b"Useful source text", "Example")
if isinstance(result, Failure):
    print(result.code, result.message)
else:
    document = result.value
```

## Documentation

- [Specification](docs/specification.md)
- [Architecture](docs/architecture.md)
- [Tool contracts](docs/tools.md)
- [Capacity and limit audit](docs/limits.md)
- [CLI](docs/cli.md)
- [Library interfaces](docs/library.md)
- [Installation](docs/installation.md)
- [Security](docs/security.md)
- [Maintenance and recovery](docs/operations.md)
- [Verification](docs/verification.md)
- [WCBUBWHB architecture review](docs/architecture-review.md)
- [Semantic retrieval and model preparation](docs/semantic.md)
- [Fleet recipes: Bad Bets news and GAAP agreements](docs/fleet-recipes.md)

## Fleet examples

Both fleets can use the same package, without changing fleet controllers,
agent runtime, history or message delivery. Domain rules stay in the fleet.
These checked-in examples are **synthetic demonstrations**, not research evidence.

```sh
toolsmith --root "$PWD/example-store" --collection demo store init
toolsmith --root "$PWD/example-store" --collection demo text put "$PWD/examples/news-body.json" --item news-body --request-id news-1
toolsmith --root "$PWD/example-store" --collection demo text put "$PWD/examples/news-summary.json" --item news-summary --request-id summary-1
toolsmith --root "$PWD/example-store" --collection demo text put "$PWD/examples/agreement.json" --item agreement --request-id agreement-1
toolsmith --root "$PWD/example-store" --collection demo semantic index --model-directory "$MODEL_DIRECTORY"
toolsmith --root "$PWD/example-store" --collection demo semantic search "borrower transfers assets outside the guarantor group" --model-directory "$MODEL_DIRECTORY" --item agreement
```

Install the wheel's `semantic` extra and explicitly prepare the two pinned
model files as described in [the semantic guide](docs/semantic.md). No implicit
download, network inference, silent truncation or lexical fallback. Bad Bets can
also embed the generic SQLite functions directly in its own database; it need
not create a Toolsmith store or copy its article archive. Read the fleet recipes
for atomic correction/invalidation and database-resident authorization scopes.

Search has no corpus-count or scanned-chunk cutoff. SQLite owns exact cosine
ranking through the packaged single-threaded vec1 engine; no Python per-vector
comparison or remote service is used. A flat index still performs a native scan,
not approximate pruning. See [search and capacity contracts](docs/semantic.md)
and the [limit audit](docs/limits.md).

## Development

`uv sync --frozen --all-extras` installs the locked development environment. Run
`scripts/verify.py` in a cgroup v2 scope bounded to 8 GiB aggregate memory, zero
swap and 256 tasks; see the verification guide. It runs format/lint, strict types,
isolated test files on available cores and wheel/sdist builds. No test server or
sleep-based timing is used. Tests clean their temporary state. Verification runs
locally; this repository has no GitHub Actions CI/CD workflows.

## License

Copyright 2026 Jeswin P Kumar. Licensed under the [MIT License](LICENSE).
Maintainer: jeswinpk@agilehead.com. Third-party dependencies and model assets retain
their own licenses; model weights are not distributed with Toolsmith. This license
does not apply to consumer projects or their private data.
