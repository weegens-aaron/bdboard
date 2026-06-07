# Historical rationale moved from inline comments

This note preserves historical context removed from code during `bdboard-68q`.

## Subprocess serialization + in-flight dedup provenance

`BdClient` keeps a process-wide semaphore and per-bead in-flight request dedup.
That behavior was influenced by prior operational learnings in earlier dashboard
implementations and by the same class of concurrency issues documented in the
broader beads ecosystem (`bd` + embedded dolt lock contention under concurrent
CLI calls).

We keep that context here so inline code comments can stay focused on
current-state behavior and maintenance intent.

## README migration framing

Comparative migration copy (old dashboard vs current dashboard) was removed from
the primary README to keep it product-current. If migration guidance is needed,
create a dedicated migration document instead of embedding historical comparison
inside core quickstart docs.
