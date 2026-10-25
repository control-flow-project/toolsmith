# Generic acquisition and reading primitives

These functions perform format, network, file and indexed-query operations.
They do not choose topics, follow links autonomously, interpret relevance,
summarize content or decide whether two stories report the same facts. Those
decisions belong to the caller. No services, browser, helper processes or model
calls are installed or started.

## Files rather than console payloads

Use the global `--output` option for complete bulk results. The destination must
be an absolute path with an owned, non-group-writable parent and must not exist.
The console receives only the new file's path and byte count; the JSON result
is not truncated. Output paths are local operational references, not public URLs.

```sh
toolsmith --output /private/work/inspection.json read html-links /private/work/page.html
toolsmith --output /private/work/feed.json read feed /private/work/feed.xml --source-url https://example.com/feed
toolsmith --output /private/work/tree.json read xml /private/work/sitemap.xml
toolsmith --output /private/work/records.json read jsonl /private/work/records.jsonl
```

`read html-links` returns cleaned text, literal links and metadata together.
Executable scripts, styles and non-content markup are excluded from prose;
literal JSON/JSON-LD blocks are separate untrusted fields. Link labels can be
explicitly marked shortened. No site selector or deterministic table meaning is
inferred. Callers inspect ordinary text and metadata, then choose what to read.
Ordinary content inside form wrappers remains readable; interactive controls
and values do not become prose. Long reading attributes use the complete 4 MiB
HTML input bound rather than a separate small field cutoff. Access/password
signals, hidden-content exclusions and node/depth limits still apply.
The XML representation preserves expanded namespace names, attributes, text and
child order. RSS/Atom returns every distinct entry within its input bounds and
an explicit publisher-declared next link when present; it fetches nothing.

## URL and format operations

```sh
toolsmith --output /private/work/urls.json url resolve https://example.com/index --file /private/work/relative-urls.json
toolsmith --output /private/work/members.json archive list /private/work/input.zip
toolsmith archive read /private/work/input.zip folder/report.csv --destination /private/work/report.csv
toolsmith decompress gzip /private/work/input.xml.gz --destination /private/work/input.xml --maximum-bytes 33554432
```

URL input is a JSON array of relative or absolute targets. Each result keeps its
input index and validation outcome; resolution does not authorize HTTP access.
Archive inspection rejects unsafe names, encrypted members and special files.
Exact-member reading and gzip expansion retain compressed/expanded byte bounds.
No archive member is executed and there is no extract-everything operation.

## Concurrent downloads

The `http` extra is required. `acquisition.batch.download_batch` accepts typed
`DownloadRequest` values; `download_batch_async` uses the same implementation.
Each request has `id`, `url`, `destination`, `HttpPolicy` and `BudgetPolicy`.
The CLI accepts their JSON representations through named approved profiles:

```json
{
  "publisher": {
    "http": {"hosts": ["example.com"]},
    "budget": {
      "group": "publisher", "period_seconds": 86400,
      "group_requests": 10000, "group_bytes": 1073741824,
      "task_requests": 50000, "task_bytes": 4294967296,
      "minimum_interval_seconds": 10
    }
  }
}
```

The request file is an array of objects such as
`{"id":"document-1","url":"https://example.com/report","profile":"publisher","destination":"/private/work/document-1.html"}`.
Group/task limits are operator approvals, not suggested collection quotas.
All profiles in a batch share period/task limits; each group has one policy.
If network state has reviewed configuration, each profile must also supply its
current `configuration_digest`. A missing/stale approval fails before HTTP; the
downloader never assumes that a recently changed approval still permits work.

```sh
toolsmith --output /private/work/downloads.json http batch --profiles /private/work/profiles.json --requests /private/work/requests.json --network-state /private/network --task assignment --concurrency 8 --deadline-seconds 300
```

By default every publisher group runs concurrently; `--concurrency` is an explicit
optional network ceiling, not a default eight-group limit. Each group is serial and its persistent request slot,
spacing and upstream cooldown are shared by cooperating callers using the same
network-state directory. Each successful body is written directly to its private
destination, not included in the outcome. An existing destination causes no HTTP
request. Timeout/cancellation leaves explicit unfinished results and conservative
usage. A completed batch means only that supplied batch completed, not that a
publisher or discovery tree was exhausted. Submit remaining selections explicitly.

### Caller-owned acquisition operations

`acquisition.buckets.Bucket(id, items, minimum_interval_seconds)` and
`run_buckets_async(buckets, operation)` supply the same finite scheduling used by
the downloader. Submit the selected inputs once: one coroutine runs per bucket,
each bucket runs its items sequentially, and starts respect that bucket's supplied
spacing. Every bucket runs concurrently; no model call or per-item scheduling by
an agent is required. Results retain bucket and input order. Duplicate bucket
identities and invalid throttles fail before effects. Cancellation or unexpected
producer failure cancels and joins the other coroutines.

The caller supplies an asynchronous operation and owns its actual effects,
permissions, per-item time bounds and durable outcomes. For example, a
browser-owning application can submit its approved page acquisitions without
putting browser processes or application policy in Toolsmith. The library starts
no process or thread. Local batch spacing never replaces shared upstream
request quotas, cooldowns or authorization checks. The application must reject
model-supplied throttles that weaken its approved publisher policy.

## PDF pages

The `pdf` extra supplies in-process PDFium and Pillow. Inputs are at most 32 MiB.
`readers.read_pdf` returns text, total pages and `next_page`. Continue until that
value is absent. `render_pdf_page` returns a PNG with dimensions, without OCR.

```sh
toolsmith --output /private/work/pages.json read pdf /private/work/document.pdf --start 0 --limit 20
toolsmith render pdf /private/work/document.pdf --page 0 --dpi 144 --destination /private/work/page-0.png
```

Pages are zero-based. Native handles close after each call. Page pixel budgets
are checked before rendering. A native parser is not an OS sandbox; PDFium calls
stay on the calling thread and callers own process-level execution controls.

## Batch indexed lookups

`lexical.search_batch` and `semantic.search_batch` accept caller-owned SQLite
connections, an authorized `Scope` and `SearchQuery(id, text)` values. Semantic
lookups additionally require the explicitly loaded local encoder. Each batch
reads scope coverage once and returns per-input results. No corpus-count cutoff,
Python pairwise corpus comparison, generative call or automatic duplicate verdict
is introduced. Existing per-query output/model limits remain explicit.

The CLI query file is an array of `{"id":"candidate-1","text":"Supplied headline"}`.
Use `search lexical batch` or `search semantic batch` with `--database`, `--scope`
and `--queries`; semantic queries also require `--model-directory`. The table or
view named by the scope must contain authorized `reference` and `text_digest` columns.
Applications own authorization, candidate dates and interpretation of matches.
