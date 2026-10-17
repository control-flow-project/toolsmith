# SQLite vector extension

SQLite's public-domain `vec1` 0.8 is the sole native vector engine. It is compiled
when building the package, never downloaded or compiled by product code. Its
original public-domain notices remain in the source and headers.
Toolsmith's local modifications follow the repository's MIT license; original
material remains public domain.

Source: https://sqlite.org/src/raw/ext/vec1/vec1.c?ci=tip, retrieved 2026-10-17.
Reviewed upstream SHA-256:
`a38c62274093bec34631831371ad433703d6dde7fa9ecd6088da4ed33d4a61f9`.
SQLite 3.53.1 headers come from the official amalgamation archive:
https://www.sqlite.org/2026/sqlite-amalgamation-3530100.zip.

Trailing horizontal whitespace and redundant final blank lines are normalized
in vendored inputs. This does not change the compiled binary; the upstream hash
above identifies the original download before local changes.

One local source correction guards the worker-queue member access in
`vec1KMeansInitOne` with `VEC1_THREADS`: upstream's advertised zero-thread build
otherwise references an incomplete type and cannot compile. The zero-thread
branch uses exactly one job.

A second correction prepares integer `IN` membership once as a sorted int64 set
and performs binary membership lookup while scanning metadata. Upstream rebuilds
the list per packed block and performs a linear membership scan per vector,
making a million permitted IDs quadratic. This changes no membership semantics:
tests cover empty/duplicate sets, nulls, negative and 64-bit IDs, numeric metadata,
multiple predicates, rollback and exact results against an independent oracle.
The vector distance and ranking algorithms are unchanged.

Nearest-neighbor reads also flush pending packed vectors into the current SQLite
transaction before searching. Without this correction, direct native queries can
miss their own uncommitted inserts. The flush never commits the transaction;
outer and nested rollback behavior is verified separately.

The native information string includes `toolsmith-native-1`, identifying this
owned contract. The loader rejects a different preloaded vec1 build even when
its upstream version is also 0.8. This avoids silently using a build without
these corrections; it is a capability marker, not a same-process security seal.

`VEC1_THREADS=0` removes worker-thread support. On x86-64, the upstream CPU
instruction dispatch selects AVX2 or scalar instructions within this engine;
ARM builds use the native instruction implementation. This is not a second
retrieval backend or a Python/remote fallback. No inference assets are bundled.
