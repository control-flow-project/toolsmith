# Toolsmith

MIT-licensed, optional generic libraries and CLI tools maintained by Control Flow.
Use none, one or several capabilities. Toolsmith is not part of fleet setup,
message delivery, sessions or history.

**Libraries and short-lived CLI commands only. No servers, daemons, background
workers, threads or helper processes.** Installing or importing it starts nothing.
The CLI calls the same validated library functions that applications import.

## Available tools

- UTF-8 text, meaningful static HTML and RSS/Atom readers.
- Versioned local text and private files in an explicitly selected collection.
- Lexical search and exact-version, physical-page/character-span citations.
- Optional offline English MiniLM embeddings and semantic search, with complete
  token-aware chunks, exact source spans and caller-owned SQLite integration.
- Optional approved HTTPS acquisition with bounded DNS/TLS, redirects, compressed
  responses, shared local quotas and explicit interrupted-operation recovery.
- Verified backup/restore, explicit integrity/index checks and preview-bound
  cleanup of inactive staging files.

Browser automation, PDF/OCR helpers and hybrid retrieval are
not implemented. No substitute or placeholder is provided. Skills, source-specific
connectors, domain analysis, financial calculations and fleet runtime remain with
their existing owners.

## Install and use

Python 3.13+ is required. Linux and SQLite FTS5 are required only for persistence
and safe filesystem operations. The base distribution has **no runtime dependencies**.
The distribution is `ctlflow-toolsmith`; the command and import are `toolsmith`.
Source and built artifacts are MIT-licensed. There is no PyPI or npm release yet;
build from the public repository or install a built wheel.

```sh
git clone https://github.com/control-flow-project/toolsmith.git
cd toolsmith
uv build --no-sources
python3 -m venv .venv
.venv/bin/python -m pip install dist/ctlflow_toolsmith-0.1.0-py3-none-any.whl
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
for atomic correction/invalidation and authorized candidate selection.

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
