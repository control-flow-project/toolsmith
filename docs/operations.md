# Maintenance and recovery

Maintenance is explicit library/CLI work. Nothing runs on a timer or behind an
accepted-job response. Do not reset production, erase history or replace upstream
limit state to bypass quotas. Collection data and shared network state have
separate lifetimes; preserve both when moving an operational installation.

## Status and explicit HTTP resume

An operation record identifies work already attempted, not an unattended future
job. `operation_status` reads its kind, times, status, GET attempt count, result
and failure. Text/file writes and completion records commit in one transaction;
their completed request replay returns the same reference.

HTTP saves its input before I/O. Each GET records a source reservation and operation
count before sending. Success commits the retained result and completion together.
An interruption can leave `running`, or a known failure records `failed`. Status
does not send a GET. Repeating `fetch` on unresolved work fails; `resume_http`
loads the saved request and original allowance, rejecting policy/network-root
changes. A completed record is reused without network I/O.

If a request was sent but its result was not durably recorded, no honest mechanism
can promise it was never received by the publisher. Explicit resume reports that
the GET may repeat. It does not change its URL, reset its allowance or invent a
successful result. Unknown byte reservations stay charged until the quota window
ends. Total request allowance can be exhausted; that fails rather than silently
creating a new job. Publisher denials, unavailable dependencies and unsupported
response types remain explicit failures.

`Acquisition.wire_bytes` measures the final received response body, not aggregate
headers, previous failed attempts or redirect bodies. The persistent allowance
conservatively accounts each request, including redirects/unknown outcomes.

Valid upstream `Retry-After` delays are preserved even when longer than a quota
window or seven days. If a supplied delay cannot be represented, limit inspection
returns `next_request_at: null` and requests remain deferred without a suggested
retry time. Another in-flight response or quota-window rollover cannot clear that
block. Preserve the state and review the upstream response with the operator; do
not reset quotas or blindly retry an unknown cooldown.

## Backup and restore

Backup holds a shared collection lock, validates the store, snapshots SQLite and
copies referenced objects to a **new** private directory. The manifest records
format/schema/collection/database/object identities. Staging and unreferenced
objects are not backup content. A consistent backup is not a source-rights grant.

Restore validates the entire backup, object set and captured database before
creating a **new** destination. It retains collection, immutable versions and
recorded operations. It copies/fsyncs objects before publishing the database from
staging, so interrupted object copies cannot expose a usable store with missing
originals. It never overwrites a production directory. A destination
already existing is a conflict even if empty. Move/activate a verified restored
store through the caller's existing operational procedures, not a hidden fallback.

I/O failure can leave a partially written new backup/restore destination. Do not
use it or overwrite/reuse it as if verified. Preserve the original, inspect the
failure and select a new destination. No automatic destructive deletion occurs.
Successful backup completion writes its manifest last; restore checks all content.

Collection backup does **not** replace/reset the shared source-limit directory.
Retain that private directory unchanged, including policy bindings and outstanding
conservative reservations, when restoring operations that might be resumed.

## Integrity and lexical rebuild

`check_integrity` checks SQLite/foreign keys, exact text/provenance/file-version
identities, complete deterministic chunk coverage, index content/postings and
referenced object bytes.
Index checking uses a bounded in-memory snapshot, not an extra persistent store.
These full checks are explicit maintenance, not repeated whole-store work on each
agent read. Normal artifact reads verify the selected object's size/identity.

`rebuild_index` transactionally regenerates chunks and the one FTS index from
canonical retained text parts using the same chunking implementation as ordinary
writes, and verifies it after commit; SQLite FTS pending postings must be committed
before snapshot verification. This can repair the index, not damaged source text,
lost originals or forged provenance. An integrity failure never substitutes a
different version. Preserve backups and diagnose damaged canonical data separately.

## Staging cleanup

Preview selects only private, single-link, old `.stage-<uuid>.tmp` regular files
under the selected `tmp/`. It records the collection, actual root identity and
exact file identities/times/sizes. Unknown files, symlinks, recent or active files
are excluded. At most 1,000 files are selected; too many fails with no deletion.

Review and explicitly apply that exact plan. Under the exclusive store lock, all
candidates are rechecked before the first deletion. Changed/moved/root-mismatched
candidates invalidate the plan. Cooperating writers cannot stage concurrently.
Arbitrary same-user processes ignoring locks are not isolated. Mid-deletion I/O
failure can leave a subset deleted; regenerate the preview, never claim rollback
of filesystem deletion. Retained originals/objects are never cleanup targets.

## Schema

Only schema one exists. Unknown schemas fail without an alternate reader, importer
or automatic migration. No production predecessor is known, so no migration is
invented. Future forward migration requires the actual old schema, verified backup,
one replacement model and coordinated consumers. No production resets are allowed.
