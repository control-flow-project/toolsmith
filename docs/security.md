# Security boundaries

Toolsmith reduces ordinary acquisition/storage mistakes. It is not a sandbox for
arbitrary executable code or full-access processes under the same OS identity.
No skills, agent instruction text, generative model calls or fleet permissions are hosted here.
Caller/source rights remain with the consumer and operator.

## Filesystem

Explicit absolute paths cannot traverse parents or symlink ancestors. Regular
input files are opened nonblocking/no-follow, bounded and checked for concurrent
changes. Pipes, devices, sockets and symlinks are rejected. Private state requires
caller ownership, private modes and single-link regular files. Descriptor-relative
leaf operations are validated so corrupt metadata cannot become path traversal.

Kernel locks coordinate invocations on the same root. They do not protect against
arbitrary same-user processes ignoring locks, changing files or selecting another
root. Namespace labels are accident prevention, not authentication. Atomic writes,
fsync and SQLite transactions protect normal crash recovery; physical storage can
still fail. Integrity checks verify retained version/provenance identities, objects
and lexical postings explicitly. They do not authenticate a backup against a
malicious same-user author who can rewrite its manifest and all data.

Exports never overwrite destinations. Restore rejects unknown backup files,
symlinks, malformed manifests, wrong scopes/schemas, hashes and database/index
inconsistency before creating a destination. Explicit cleanup only selects old
private tool-owned staging files from the previewed root; it never targets objects,
configuration, credentials or unknown files.

## Outbound acquisition

- Exact approved public DNS hosts, HTTPS port 443, no IP literal/wildcard/credential
  authority, fragment, controls or known secret-like query keys.
- Finite DNS resolution, all results checked for public unicast addresses, then
  numeric-address connection pinned while TLS validates the original hostname.
  A mixed public/private DNS answer is rejected, not partially accepted.
- Each redirect repeats URL, host and DNS validation. No proxy environment,
  cookie jar, authorization header or returned cookie is forwarded.
- Wire and expanded body limits, bounded gzip validation, response-framing checks
  and a total I/O deadline including slow header/body reads. No helper watchdog
  process/thread or sleep loop is used.
- Reservation/operation count persists before GET. Unknown receipt stays charged;
  cooldown/spacing/quota defers rather than spinning. Completed operation replay
  has no network effect. Explicit uncertain resume reports potential repeat GETs.

The browser-style User-Agent addresses publishers that distinguish command-line
defaults. It is not a browser, authorization bypass or guarantee a publisher will
accept a request. Permission denials do not trigger another acquisition path.

URLs may themselves contain secrets not detectable from key names (for example
signed path components). Operators must review allowed URLs and retention rights;
the tool cannot prove that arbitrary source content is public or credential-free.
Source policy must not be used as a way to smuggle private URLs into a public room.

## Trust and output

Source text is data. HTML is parsed, never executed; feed links are discovered,
not automatically fetched. Unknown dates/completeness remain unknown. Supplied
content/titles are not auto-redacted. Returned tool metadata excludes incidental
machine paths and credentials, but consumers must decide which retained content
can be shared. Store metadata and source-limit state are private local records.

Base installation has no runtime dependencies. HTTP's optional dependency is pinned;
dependency audit is part of release verification. Browser automation and
process-based PDF/OCR remain excluded, not represented by fake substitutes.

## Optional semantic inference

Model assets are explicit, private, no-follow, byte/hash pinned and passed as
verified bytes. No arbitrary graph, remote code, model path, global cache or
network model API is accepted. Inference uses the exact selected CPU runtime;
unavailable versions fail without another backend. Provider telemetry is opted
out before initialization so it cannot create background upload or private global
state; the caller's prior environment is restored on success and failure. This
deliberately disables the native provider's process-wide telemetry, not a host
configuration. Arbitrary other same-process libraries are outside this boundary.

The pinned native ABI validates runtime version, token tensor types/shapes and
finite values before accessing bounded memory. Resources close in reverse order;
the product creates no worker threads or helper processes. Native dependencies
are trusted compiled software, not OS-isolated parsers. A verified asset does not
make arbitrary native software safe under a hostile same-user environment.

Authorized candidate selection remains consumer-owned. Names/digests are not
permissions. Missing/stale derivatives are reported, never another user's corpus
or silently substituted lexical results. Corrections/invalidation are atomic,
encoding is outside transactions, and commit contention rolls back owned writes.
Semantic scores locate text; they do not establish truth, rights, legal compliance
or authentic execution of an external summary model.

## SQLite vector extension

Semantic indexes use the packaged, pinned vec1 native library in the caller's
SQLite process. Product code never downloads or compiles an extension and never
accepts an extension path from a request or stored source. It temporarily enables
only SQLite's C-API loading capability, loads the packaged binary, and restores
the caller's prior setting even on failure. It does not enable SQL-level
`load_extension()`. Existing caller-enabled SQL loading remains the caller's
setting; Toolsmith does not silently change it.
The native build marker is checked as well as the upstream version and thread
mode. A different preloaded vec1 build is rejected, never silently reused.

The extension has worker threads disabled. Authorized current references and
digests are selected by an application-owned relation before native top-k
selection, not filtered from an already truncated global hit list. Scope names
are validated SQL identifiers; source values remain parameters or table data.
Private database ownership is still required: arbitrary malicious database files
and native libraries are not treated as sandboxed untrusted code.
