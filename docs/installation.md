# Installation

Toolsmith 0.1.0 has public MIT-licensed source and wheel/sdist artifacts. Metadata
declares the SPDX expression `MIT`; both artifacts include LICENSE. There is no
PyPI/npm release yet and no automatic publishing workflow. Build from the public
repository or install a built wheel:

```sh
git clone https://github.com/control-flow-project/toolsmith.git
cd toolsmith
uv build --no-sources
```

Python 3.13+ is required. Persistence/safe file reads require Linux, no-follow
descriptor primitives and SQLite built with FTS5. Pure byte readers have no
store/network requirement. Unsupported platforms fail without a weakened path.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install dist/ctlflow_toolsmith-0.1.0-py3-none-any.whl
.venv/bin/toolsmith --json capabilities
```

For selected network acquisition:

```sh
.venv/bin/python -m pip install 'dist/ctlflow_toolsmith-0.1.0-py3-none-any.whl[http]'
```

The `http` extra installs the pinned bounded DNS resolver `dnspython==2.8.0`.
There are no base runtime dependencies. Nothing downloads browsers, OCR models,
embeddings, skills or agent software. No global services or credentials are created.
Supply an explicit private store and separate shared source-limit directory only
for operations that need them. Parent directories must already exist.

The selected state is 0700 directories/0600 files owned by the invoking user.
Do not share one OS account with untrusted callers and then rely on collection
labels as an isolation boundary. Different actual trust domains need host-owned
access controls and separately authorized roots.

## Maintainer builds

`uv.lock` pins development/build dependencies under a seven-day release-age
cutoff. `uv sync --frozen --all-extras` followed by the bounded verification command builds
both wheel and sdist. The wheel includes only library/CLI code, schema, typing
marker and license/metadata; repository tests/scripts/docs remain in the sdist.
Neither artifact includes private stores, `.analysis`, secrets or development
environments. Installed-artifact acceptance verifies both formats from clean
environments, including absence of the optional dependency in a base installation.

The separately selected `[semantic]` extra provides pinned inference/tokenizer
dependencies. See [model preparation](semantic.md): supplying model assets is an
operator action, not an installation effect. Base installs have no model software,
and non-semantic capabilities work without it.
