# Proposed complete directory layout

This is the proposed physical organization **after** the generic capability work.
It is not another implementation, a placeholder package or a set of compatibility
aliases. The current branch adds/verifies the capabilities first. Approval of this
layout would move each implementation once, change all owned imports and commands,
remove the old paths, and repeat the integrated/installed gates.

`filesystem` is about files, not documents. `parsing` reads bytes/text without
retaining them. `http` makes explicit approved outbound requests; it is never an
HTTP service. `search` owns derivatives over caller-owned sources. `journal` owns
generic JSON record framing, not business events. `text_archive` is specifically
the optional retained-text/file application; neither adopter is forced to use it.

```text
toolsmith/
├── .gitignore
├── AGENTS.md
├── LICENSE
├── README.md
├── pyproject.toml
├── uv.lock
├── hatch_build.py
├── vendor/
│   └── sqlite/
│       ├── README.md
│       ├── vec1.c
│       ├── sqlite3.h
│       └── sqlite3ext.h
├── src/
│   └── toolsmith/
│       ├── __init__.py
│       ├── __main__.py
│       ├── py.typed
│       ├── result.py
│       ├── validation.py
│       ├── clock.py
│       ├── sqlite.py
│       ├── compression.py
│       ├── filesystem/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── paths.py
│       │   ├── descriptors.py
│       │   ├── io.py
│       │   ├── streaming.py
│       │   ├── atomic.py
│       │   ├── locks.py
│       │   ├── tree.py
│       │   └── archives.py
│       ├── parsing/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── text.py
│       │   ├── json.py
│       │   ├── html_dom.py
│       │   ├── html.py
│       │   ├── feeds.py
│       │   ├── tables.py
│       │   └── content.py
│       ├── http/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── policy.py
│       │   ├── urls.py
│       │   ├── transport.py
│       │   ├── client.py
│       │   ├── budgets.py
│       │   └── budget_import.py
│       ├── search/
│       │   ├── __init__.py
│       │   ├── scopes.py
│       │   ├── lexical/
│       │   │   ├── __init__.py
│       │   │   ├── chunks.py
│       │   │   ├── query.py
│       │   │   ├── passages.py
│       │   │   ├── index.py
│       │   │   └── schema.sql
│       │   └── semantic/
│       │       ├── __init__.py
│       │       ├── profile.py
│       │       ├── assets.py
│       │       ├── native.py
│       │       ├── model.py
│       │       ├── chunks.py
│       │       ├── index.py
│       │       ├── status.py
│       │       ├── vector.py
│       │       └── schema.sql
│       ├── journal/
│       │   ├── __init__.py
│       │   ├── records.py
│       │   └── io.py
│       ├── text_archive/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── database.py
│       │   ├── schema.sql
│       │   ├── text.py
│       │   ├── artifacts.py
│       │   ├── operations.py
│       │   ├── citations.py
│       │   ├── lexical.py
│       │   ├── semantic.py
│       │   ├── http_policy.py
│       │   ├── http.py
│       │   ├── backup.py
│       │   ├── integrity.py
│       │   ├── cleanup.py
│       └── cli/
│           ├── __init__.py
│           ├── parser.py
│           ├── commands.py
│           ├── filesystem.py
│           ├── parsing.py
│           ├── http.py
│           ├── indexes.py
│           └── text_archive.py
├── tests/
│   ├── conftest.py
│   ├── semantic_support.py
│   ├── test_architecture.py
│   ├── test_validation.py
│   ├── test_files.py
│   ├── test_generic_files.py
│   ├── test_archives.py
│   ├── test_capacity_boundaries.py
│   ├── test_corpus_capacity.py
│   ├── test_search_scopes.py
│   ├── test_vector_native.py
│   ├── test_packaging.py
│   ├── test_optional_primitives.py
│   ├── test_readers.py
│   ├── test_generic_readers.py
│   ├── test_policy_limits.py
│   ├── test_transport.py
│   ├── test_http.py
│   ├── test_generic_budgets.py
│   ├── test_caller_indexes.py
│   ├── test_semantic_chunks.py
│   ├── test_semantic_model.py
│   ├── test_semantic_native.py
│   ├── test_semantic_index.py
│   ├── test_semantic_store.py
│   ├── test_store.py
│   ├── test_maintenance.py
│   ├── test_cli.py
│   └── test_standalone_cli.py
├── scripts/
│   ├── verify.py
│   ├── accept_package.py
│   ├── accept_https.py
│   ├── accept_corpus.py
│   └── accept_semantic.py
├── docs/
│   ├── specification.md
│   ├── architecture.md
│   ├── architecture-review.md
│   ├── capability-mapping.md
│   ├── proposed-layout.md
│   ├── installation.md
│   ├── library.md
│   ├── tools.md
│   ├── limits.md
│   ├── cli.md
│   ├── filesystem.md
│   ├── parsing.md
│   ├── http.md
│   ├── search.md
│   ├── semantic.md
│   ├── journal.md
│   ├── text-archive.md
│   ├── operations.md
│   ├── fleet-recipes.md
│   ├── security.md
│   └── verification.md
└── examples/
    ├── caller-owned-sources.json
    ├── http-policy.json
    ├── budget-policy.json
    ├── agreement.json
    ├── news-body.json
    └── news-summary.json
```

No `services/`, servers, daemons, worker processes, skills, fleets, connectors,
financial domain schema or agent configurations are proposed. `scripts/` contains
development verification only; it is not a runtime dependency. There is no CI/CD
workflow or package-install activation.

The archive's lexical/semantic/HTTP files are **composition**, not other engines.
They call the same generic libraries and add archive-specific references/retention.
The current flat retained-HTTP policy translation belongs there, not in the
generic network package. No core module imports `text_archive`.

This tree lists all proposed tracked source, tests, scripts, examples and docs.
Ignored local analysis, virtual environments, downloaded verification assets,
databases and build/test caches are deliberately excluded. Library-only primitives
do not need placeholder CLI commands: the journal remains a library, and CLI files
are responsibility splits of real commands. Capability guides document actual
functions rather than promising future services or domain integrations.
