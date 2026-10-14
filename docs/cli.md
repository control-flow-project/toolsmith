# CLI

## Archive-independent commands

`search lexical/semantic` uses an explicit caller-owned `--database`. `init` adds
derivatives, not a canonical source database or application schema version.
`index/query/check` take `--sources FILE`, a JSON array of
`{reference,text,language?}`. `status` takes `--references FILE`, an array of source
references only, with no model, source-body or vector reads. `delete REFERENCE`
removes one exact derivative. Semantic index/query require `--model-directory`;
init/status/check/delete do not activate a model.

`read json`, `read table --column NAME [--filter COLUMN=VALUE]`, `read html-tables`
and `read html --selection article [--title INTENDED]` use generic parsers.
Table output includes complete scan/match counts and explicit truncation.
`filesystem hash/copy FILE --maximum-bytes N` streams selected regular files.

`http request URL --policy FILE --budget-policy FILE --network-state DIR --task ID
--destination FILE` returns a raw approved response file and receipt without an
archive. The stable task shares group/task quotas; the caller owns job-level
receipt storage/recovery. `http fetch/resume` is optional text-archive composition
over the same HTTPS producer, not another implementation.

`maintenance migrate DESTINATION` with explicit `--root/--collection` verifies
and forward-copies an archive-v1 store to v2; the original remains unchanged.
Regular backup/restore commands are specific to the optional text archive.

`toolsmith --help` and each subcommand's `--help` define the current syntax.
Global `--root`, `--collection` and `--json` precede the command family.
Paths are explicit and absolute; use `$PWD` when working in a suitable directory.
No command starts a server, helper process, listener or fleet.

```text
toolsmith capabilities
toolsmith store init | inspect
toolsmith read text FILE --title TITLE
toolsmith read html FILE [--title TITLE]
toolsmith read feed FILE --source-url URL [--limit N]
toolsmith read json FILE
toolsmith read table FILE --column COLUMN [--filter COLUMN=VALUE] [--format csv|zip-csv|gzip-csv]
toolsmith read html-tables FILE
toolsmith filesystem hash FILE --maximum-bytes N
toolsmith filesystem copy FILE DESTINATION --maximum-bytes N
toolsmith search lexical|semantic init --database FILE
toolsmith search lexical|semantic index --database FILE --sources FILE [--limit N]
toolsmith search lexical|semantic query QUERY --database FILE --sources FILE [--limit N]
toolsmith search lexical|semantic status --database FILE --references FILE
toolsmith search lexical|semantic check --database FILE --sources FILE
toolsmith search lexical|semantic delete REFERENCE --database FILE
toolsmith text put DOCUMENT_JSON --item ITEM --request-id ID
toolsmith text inspect VERSION
toolsmith text list [--item ITEM] [--limit N] [--offset N]
toolsmith text search QUERY [--limit N] [--offset N]
toolsmith semantic model-check --model-directory DIR
toolsmith semantic index --model-directory DIR [--limit N]
toolsmith semantic status | clear
toolsmith semantic search QUERY --model-directory DIR [--limit N] [--item ITEM]
toolsmith text cite VERSION [--part N] [--start N] [--length N]
toolsmith file put FILE --name NAME --media-type TYPE --request-id ID [--source-url URL]
toolsmith file inspect | read VERSION
toolsmith file export VERSION DESTINATION
toolsmith http inspect-policy --policy FILE
toolsmith http request URL --policy FILE --budget-policy FILE --network-state DIR --task ID --destination FILE
toolsmith http limits --policy FILE --network-state DIR
toolsmith http fetch URL --policy FILE --network-state DIR --request-id ID [--item ITEM] [--name NAME]
toolsmith http resume --policy FILE --network-state DIR --request-id ID
toolsmith operation ID
toolsmith maintenance integrity | rebuild-index
toolsmith maintenance backup | restore DESTINATION [--maximum-bytes N]
toolsmith maintenance migrate DESTINATION [--maximum-bytes N]
toolsmith maintenance cleanup-preview [--minimum-age SECONDS]
toolsmith maintenance cleanup-apply PLAN_JSON
```

`read`, `filesystem`, caller-owned `search`, raw `http request`, `capabilities`,
model checking, policy inspection and network-limit inspection require no archive.
Archive commands require exact `--root` and `--collection`; for restore, `--root`
selects the backup, not the destination. Standalone semantic index/query additionally
require `--model-directory`, omitted from the compact syntax list above.

Results use `{ "ok": true, "result": ... }` or `{ "ok": false, "error": ... }`.
`--json` emits compact JSON; ordinary output is the same data formatted readably.
Binary file reads return bounded base64 plus byte count. File export writes the
selected bytes without overwriting a destination and returns a path-free receipt.

## Local text example

```sh
toolsmith --root "$PWD/local-store" --collection sample store init
toolsmith --json read text "$PWD/source.txt" --title "Source" | jq '.result' > document.json
toolsmith --json --root "$PWD/local-store" --collection sample text put "$PWD/document.json" --item source --request-id import-source-1
toolsmith --root "$PWD/local-store" --collection sample text search "useful words"
```

`jq` is an optional operator convenience, not a dependency or spawned product
helper. Applications can pass the returned `Document` directly to `put_text`.
Document JSON requires `title` and `parts`; each part requires `label` and `text`.
Optional document fields: `method`, `source_url`, `published_at`, `observed_at`.
Optional part fields: `physical_page`, `warnings`. Unknown fields are rejected.

## Approved acquisition example

Review the source's access/retention rights before creating a policy. A policy
is local operator permission, not proof of redistribution rights.

```json
{"format":1,"group":"example-source","hosts":["example.com"],"retention":"text_only"}
```

```sh
toolsmith --json --root "$PWD/local-store" --collection sample http fetch https://example.com/ --policy "$PWD/source-policy.json" --network-state "$PWD/shared-source-limits" --request-id example-home-1 --item example-home
toolsmith --root "$PWD/local-store" --collection sample operation example-home-1
toolsmith --root "$PWD/local-store" --collection sample http resume --policy "$PWD/source-policy.json" --network-state "$PWD/shared-source-limits" --request-id example-home-1
```

A failed or interrupted fetch is not silently retried by repeating `fetch`.
`resume` reads the saved request, keeps its allowance and reports possible repeat
GETs. Passing a different policy or network-state directory fails. Keep that
directory with the store's operational state; backups of collection data do not
reset or replace shared upstream quotas.

## Maintenance example

```sh
toolsmith --root "$PWD/local-store" --collection sample maintenance integrity
toolsmith --root "$PWD/local-store" --collection sample maintenance backup "$PWD/new-backup"
toolsmith --root "$PWD/new-backup" --collection sample maintenance restore "$PWD/new-restored-store"
toolsmith --json --root "$PWD/local-store" --collection sample maintenance cleanup-preview | jq '.result' > cleanup-plan.json
toolsmith --root "$PWD/local-store" --collection sample maintenance cleanup-apply "$PWD/cleanup-plan.json"
```

Review the cleanup plan before apply. Changed candidates invalidate it before
deletion. Backups and restores require new destinations; these commands cannot
reset production or overwrite existing stores.

See [semantic retrieval](semantic.md) and the [fleet recipes](fleet-recipes.md)
for model preparation, bounded indexing, coverage, exact citations, corrections
and generic caller-owned SQLite integration.
