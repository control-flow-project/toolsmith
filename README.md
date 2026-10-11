# Toolsmith

Private, optional generic libraries and CLI tools maintained by Control Flow.
Use none, one or several capabilities. Toolsmith is not part of fleet setup,
message delivery, sessions or history.

**Libraries and short-lived CLI commands only. No servers, daemons, background
workers, threads or helper processes.** Installing or importing it starts nothing.
The CLI calls the same validated library functions that applications import.

## Available tools

- UTF-8 text, meaningful static HTML and RSS/Atom readers.
- Versioned local text and private files in an explicitly selected collection.
- Lexical search and exact-version, physical-page/character-span citations.
- Optional approved HTTPS acquisition with bounded DNS/TLS, redirects, compressed
  responses, shared local quotas and explicit interrupted-operation recovery.
- Verified backup/restore, explicit integrity/index checks and preview-bound
  cleanup of inactive staging files.

Browser automation, PDF/OCR helpers, embeddings and vector/hybrid retrieval are
not implemented. No substitute or placeholder is provided. Skills, source-specific
connectors, domain analysis, financial calculations and fleet runtime remain with
their existing owners.

## Install and use

Python 3.13+ is required. Linux and SQLite FTS5 are required only for persistence
and safe filesystem operations. The base distribution has **no runtime dependencies**.
The distribution is `ctlflow-toolsmith`; the command and import are `toolsmith`.
Distribution is private, not published to public PyPI or npm.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install /absolute/path/to/ctlflow_toolsmith-0.1.0-py3-none-any.whl
.venv/bin/toolsmith --json capabilities
.venv/bin/toolsmith --root "$PWD/local-store" --collection sample store init
```

For network acquisition, install the same private wheel with its `http` extra.
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

## Development

`uv sync --frozen --extra http` installs the locked development environment. Run
`scripts/verify.py` in a cgroup v2 scope bounded to 8 GiB aggregate memory, zero
swap and 256 tasks; see the verification guide. It runs format/lint, strict types,
isolated test files on available cores and wheel/sdist builds. No test server or
sleep-based timing is used. Tests clean their temporary state.

Copyright 2026 Jeswin P Kumar. Proprietary/restricted commercial software under
[LICENSE](LICENSE); this is not open source. Third-party rights remain intact.
