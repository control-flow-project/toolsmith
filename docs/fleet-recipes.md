# Using the same toolkit from any fleet

Everything remains optional. Use the MIT-licensed wheel's `[http]` and/or `[semantic]`
extras only for selected capabilities; zero extras is valid. No setup, delivery,
native history or lifecycle depends on this package. Importing it starts nothing.
Existing production Bad Bets/GAAP code has **not** been changed by this extraction.
These recipes are ready integration contracts, not a deployed migration claim.

## Bad Bets: current news in the owner database

Keep current article URLs, original bodies, Luna summaries, tags, dates and jobs
in Bad Bets. Toolsmith does not enforce a summary model, create article revisions,
perform financial analysis or call a model API. Give each representation a stable
reference, e.g. `article:<id>:headline`, `article:<id>:body`, `article:<id>:summary`.
Preserve the distinction between acquired original text and summary navigation.

The generic library in `toolsmith.semantic` operates directly on the owner's
connection. Initialize its derivative tables and native vector index as part of that owner's
single schema. The packaged extension is registered by `initialize_index`; no
separate process, index file or server exists.
Prepare `Source`/vectors outside transactions. At publication, in the same
transaction, compare the current article text digest with the prepared digest,
then call `publish_embedding` with the index's expected previous digest. Reject
stale workers. This is one canonical path, not a mirrored archive or service.

For a body correction, inside the existing article-update transaction:

```python
from toolsmith.result import unwrap
from toolsmith.semantic import invalidate_embedding

with connection:
    update_current_article_and_clear_obsolete_summary(connection, article_id, body)
    unwrap(invalidate_embedding(connection, f"article:{article_id}:body"))
    unwrap(invalidate_embedding(connection, f"article:{article_id}:summary"))
```

The first function is deliberately **consumer-owned**, not a Toolsmith API. It
also applies Bad Bets' existing summary/tag/claim rules. Only unchanged current
inputs may reuse vectors. Headlines and summaries can be separate sources with
the same primitive API; a summary must not be presented as original evidence.
At query time, expose permitted current references/digests in an application-owned
SQLite table/view and pass `Scope("permitted_text")` to `search_embeddings`, and read exact hit spans from canonical
original text. Report missing/stale coverage. Do not broaden a private query to
another user's corpus or use a stale summary digest to claim body completeness.

Existing Torch-profile tables are **not** a compatible Toolsmith index. An owned
consumer change must use a verified backup and forward conversion to the one
canonical Toolsmith profile/tables, rebuilding derivatives from current originals.
No automatic import, dual reader/writer, silent backend adoption or production
changes are included here. Current optional platform extraction is complete;
switching that live consumer is a separately scoped owner change.

## GAAP: page-based agreements and exact citations

GAAP keeps its room-specific case database, source/amendment identity, PDF/OCR
outputs, physical page relations, methods/warnings and full page reads. Replace its
generic file/ZIP/chunk/FTS mechanics, not those domain records or permissions.
Use public `lexical.Source` per canonical page with an opaque exact reference,
initialize derivatives in that same case DB, and supply authorized current page
digests before query ranking. Preserve the exact-room database boundary: candidate
filtering does not isolate BM25's database-wide statistics. Use `find_text` with
caller-selected page regions for literal context that must not cross pages.

```python
from toolsmith import lexical
from toolsmith.result import unwrap

unwrap(lexical.initialize_index(case_connection))
source = lexical.Source(page_reference, canonical_page_text, source_title)
unwrap(lexical.index_source(case_connection, source, expected_digest=previous_digest))
matches = unwrap(lexical.search(case_connection, '"Restricted Payments"', lexical.Scope("authorized_pages")))
```

The case connection, canonical text and authorized table/view are deliberately
consumer-owned. Enable foreign keys before writes. Apply corrections/invalidation
inside its transaction and unwrap failures there. Query hit offsets address the
original page text; short snippets do not replace full page reads. For document
handoffs, `pack_files/unpack_files` use the exact consumer-approved file set and
digests without imposing an agreement bundle manifest or recipient policy.

Semantic analysis can additionally use the same page references on this caller-owned
connection. Prepare vectors outside its transaction, recheck current text when
publishing, invalidate corrections atomically and use metadata-only `inspect_index`
for readiness. Indexing supplies no extraction assurance or legal conclusion.
Toolsmith's separately optional PDF reader extracts text/renders pages; GAAP
still owns physical-page mapping, extraction methods and any OCR process.

## Optional retained-text demonstration

For a consumer that deliberately chooses the separate text archive, supply one
`TextPart` per extracted page/section, including known physical page and explicit
extraction warnings. Never invent a page number. This is not GAAP's required storage
model or a replacement for its full-page CLI.

The checked-in `examples/agreement.json` demonstrates three physical pages. Import
through `text put` or `put_text`, run bounded semantic batches until pending=0,
then search with `--item` for the relevant agreement. Store functions return exact
version/part/character-span citations. Old originals remain citable after corrected
extraction, but current search never uses their invalidated vectors.

```sh
toolsmith --root "$PWD/gaap-example" --collection demo store init
toolsmith --root "$PWD/gaap-example" --collection demo text put "$PWD/examples/agreement.json" --item agreement --request-id extraction-1
toolsmith --root "$PWD/gaap-example" --collection demo semantic index --model-directory "$MODEL_DIRECTORY"
toolsmith --root "$PWD/gaap-example" --collection demo semantic search "assets outside the guarantor group" --model-directory "$MODEL_DIRECTORY" --item agreement
toolsmith --root "$PWD/gaap-example" --collection demo maintenance integrity
```

Neither consumer is forced to create this archive. It is composition over the same
indexes, not a per-fleet plugin, alternate backend or mirrored application store.

## Broader toolkit recipes

- Saved HTML: `read html` keeps meaningful text; a browser, cookies and scripts
  are not emulated. Feed reading does not automatically fetch article bodies.
- Approved public acquisition: `http request` takes reviewed network/budget policy,
  a shared network-state root and stable task, returning raw bytes/receipts. The
  optional archive's `http fetch` adds retention/operation identity through the
  same producer. The browser-style User-Agent never authorizes access bypass.
- Quotas: all cooperating public HTTP and externally owned browser transports
  reserve against the same group/task budget root. Preserve reviewed existing
  charges/cooldowns through quiesced `import_budget`; never reset them at adoption.
- Generic parsing: strict JSON, article-selected static HTML, feeds and compressed
  CSV validate bytes/fields/counts, not source rights or financial interpretation.
- File/tree/journal primitives: preserve exact file snapshots and explicit private
  staging. Consumers choose included backup areas and validate their event schemas;
  no Toolsmith document schema or automatic journal retention is imposed.
- Read exact text: `text cite` preserves Unicode offsets, provenance and unknown
  timestamps. Lexical `text search` and semantic search are separate explicit
  tools. A missing encoder is not silently replaced with lexical results.
- Originals/files: `file put`, `read` and `export` retain exact private bytes;
  exports never overwrite. Rights and permitted sharing remain consumer-owned.
- Recovery: verified `maintenance backup/restore`, integrity and index operations
  need no model service. Preserve originals and histories. The toolkit has one
  current schema and does not convert consumer databases or reset running state.

See the library/CLI guides for executable contracts. These examples use only
portable public package exports; no repository-source reach-through, special
fleet plugin or internal agent package is needed.
