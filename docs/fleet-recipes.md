# Using the same toolkit from any fleet

Everything remains optional. Use the private wheel's `[http]` and/or `[semantic]`
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
connection. Install its three tables as part of that owner's single schema.
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
At query time, choose authorized article/representation candidates first, supply
current digests to `search_embeddings`, and read exact hit spans from canonical
original text. Report missing/stale coverage. Do not broaden a private query to
another user's corpus or use a stale summary digest to claim body completeness.

Existing Torch-profile tables are **not** a compatible Toolsmith index. An owned
consumer change must use a verified backup and forward conversion to the one
canonical Toolsmith profile/tables, rebuilding derivatives from current originals.
No automatic import, dual reader/writer, silent backend adoption or production
changes are included here. Current optional platform extraction is complete;
switching that live consumer is a separately scoped owner change.

## GAAP: page-based agreements and exact citations

GAAP owns PDF/browser/OCR, extracted pages and legal analysis. Supply one `TextPart`
per meaningful extracted page/section, including known physical page and explicit
extraction warnings. Never invent a page number. Toolsmith reads/indexes that
text; it does not parse a PDF, approve a legal conclusion or promise OCR accuracy.

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

Alternatively, GAAP can use the exact same generic SQLite library in its own
canonical database, as Bad Bets can. Neither consumer is forced to use the
platform text store or duplicative state. This is composition over one vector
implementation, not two product modes or a special per-fleet integration.

## Broader toolkit recipes

- Saved HTML: `read html` keeps meaningful text; a browser, cookies and scripts
  are not emulated. Feed reading does not automatically fetch article bodies.
- Approved acquisition: `http fetch` takes reviewed host/retention policy and a
  shared explicit network-limit root. Its transport already uses a browser-style
  User-Agent; this is not permission to bypass quota/access restrictions.
- Read exact text: `text cite` preserves Unicode offsets, provenance and unknown
  timestamps. Lexical `text search` and semantic search are separate explicit
  tools. A missing encoder is not silently replaced with lexical results.
- Originals/files: `file put`, `read` and `export` retain exact private bytes;
  exports never overwrite. Rights and permitted sharing remain consumer-owned.
- Recovery: verified `maintenance backup/restore`, integrity and index operations
  need no model service. Use production backups and forward owner migrations,
  never reset a database or histories to make an optional toolkit work.

See the library/CLI guides for executable contracts. These examples use only
portable public package exports; no repository-source reach-through, special
fleet plugin or internal agent package is needed.
