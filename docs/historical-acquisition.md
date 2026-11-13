# Historical acquisition

`toolsmith.acquisition.history` is an optional library for caller-owned backfills.
It does not collect a particular domain, discover routes, create analytical
schemas, interpret source documents, authenticate a provider or run autonomously.
Applications retain their existing transport, native parsers and independent
analytical builders.

```text
Native source adapter: identity, calendar, route, limits, discovery
                             |
                  Shared coverage and planner
                             |
             Same decision for inspection/execution
                             |
               Existing explicit transport owner
                             |
        Shared input ledger / attempt history / coverage
                             |
             Independent caller-selected builders
```

`NativeRequest` binds source, semantic item, exact native identity, opaque JSON
request, optional extent, freshness and discovery state. Payload format and
coverage granularity are independent. A fixed file or document need not pretend
to have a historical range. Different URLs/editions are not automatically equal.

`DateRange` is inclusive local calendar coverage. `TimeRange` is half-open
absolute-time coverage `[start,end)` with timezone-aware endpoints. They cannot
substitute for one another. `subtract`/`subtract_time` return disjoint gaps;
`pack`/`pack_time` pack bounded native requests newest first, bridging interior
holes where that saves calls. A native start anchor preserves providers whose
proven file boundaries depend on the start date. `calendar_months` supports
whole indivisible publisher months or clipped query months.

`Gap` records typed unresolved/provisional units and reasons. These remain
retryable observations, never a permanent exclusion list. `WindowPlan` keeps actual
missing spans separate from the wider native request used to pack them efficiently.

`Acquisition` records source originals, actual observation time, closed and
provisional coverage, native evidence, measurements and discovery completeness.
Only source adapters can establish what their responses prove. Downloaded bytes
without enumeration proof do not establish complete company/report history.
`Ledger` persists those typed inputs, unresolved attempts and coverage through
one current private record contract. Original objects and their immutable source
manifests remain owned by the application. Native evidence extensions do not
create an alternate cursor. Ordinary reads never migrate another format.

`decide` owns reuse, refresh, discovery and due decisions. New assignments retry
unresolved attempts; analytical failures do not become acquisition attempts.
An explicit refresh reuses an already refreshed identical input in the same
assignment. Missing measurements remain unknown. Inspection uses these same
`Decision` values and bounded pages; it reports exact native requests, coverage,
reasons and known request counts. Dynamic downstream counts remain unknown until
required discovery completes. Completed enumeration has zero unknown work.

`run_frontiers_async` coordinates finite work backwards in caller-selected
calendar blocks. Each publisher lane uses the existing acquisition bucket
scheduler. All selected streams finish an attempted block before the shared
frontier advances. A 15-day native range can therefore run beside 15 daily files.
Wide native files run once; they are not split to fit coordination blocks.
Discovery parents precede payloads and can withdraw superseded membership.
Explicit unavailable/failed outcomes do not stall independent sources forever.
A bounded interruption returns exact pending work. `known_work`, `handled_work`
and `pending_work` count the current active queue; `handled_work_total` retains
lifetime handled work even when later discovery withdraws it. No task, process, thread,
model or service is created outside the calling finite coroutine.

`Accounting` supplies per-stream reuse, outcome, byte and request counts with
preparation/discovery/payload separation. Wall duration is distinct from summed
operation durations. It flags streams with at least 20% failed operations;
applications retain domain-specific policy and reporting responsibilities.

The current record reader is also available through the same library/CLI path:

```sh
toolsmith --json history record /absolute/private/history-record.json
```

Use the global `--output` for complete large results. The command starts no HTTP,
SQL, directory initialization or source discovery. Record payloads are bounded to
32 MiB, atomically published and digest-bound. Immutable replacement conflicts
fail. Records bind their explicit category and relative owner identity.
Application-owned one-time conversion belongs in application maintenance code;
there is no generic legacy converter, runtime format dispatch or alternate reader.
