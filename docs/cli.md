# CLI

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
toolsmith http limits --policy FILE --network-state DIR
toolsmith http fetch URL --policy FILE --network-state DIR --request-id ID [--item ITEM] [--name NAME]
toolsmith http resume --policy FILE --network-state DIR --request-id ID
toolsmith operation ID
toolsmith maintenance integrity | rebuild-index
toolsmith maintenance backup | restore DESTINATION [--maximum-bytes N]
toolsmith maintenance cleanup-preview [--minimum-age SECONDS]
toolsmith maintenance cleanup-apply PLAN_JSON
```

`read`, `capabilities`, model checking, policy inspection and network-limit inspection do not
require a collection store. All other commands require exact `--root` and
`--collection`. For restore, `--root` selects the backup, not the destination.

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
