# 0004 — Runtime source of truth is the `bd` CLI JSON

- **Status:** accepted
- **Date:** 2026-06-01
- **Relates to:** README "Behavior highlights" / "Backup", memory
  `stack-overview`, upstream `COMMUNITY_TOOLS.md`. Backfills audit item **M2**.

> At runtime bdboard reads bead state **only** through the `bd` CLI's JSON
> output (`bd list --all --no-pager --limit 0 --json`, `bd show … --json`). It
> never reads `.beads/issues.jsonl` and never writes to `.beads/`.

## Context

There are two superficially available ways to learn bead state:

1. The `bd` CLI's JSON output — backed by the live Dolt DB.
2. The `.beads/issues.jsonl` passive export file sitting right there on disk.

Reading the JSONL file directly looks tempting (no subprocess, just read a
file), but upstream `COMMUNITY_TOOLS.md` declares that path **deprecated** and
warns it may be missing fields. The JSONL is a passive export, not the wire
protocol or the source of truth (it can be stale or absent depending on
`export.auto`).

## Decision

- **Reads** go exclusively through the `bd` CLI in JSON mode
  (`bd list --all --no-pager --limit 0 --json`, `bd show … --json`, etc.),
  wrapped by `BdClient` in `src/bdboard/bd.py`.
- All `bd` subprocess calls are serialized through one `asyncio.Semaphore(1)`
  (`_subprocess_gate`) because bd's embedded Dolt server is single-writer and
  lock-prone under concurrency.
- **bdboard never writes to `.beads/`** and **never reads `issues.jsonl`.** The
  canonical runtime source of truth is the Dolt DB *as read through the `bd`
  CLI*.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Read via `bd … --json` CLI** | Always-fresh, dolt-native; complete field set; the supported, future-proof interface; lets bd own locking/migrations | Subprocess cost per call (mitigated by caching + the serialization gate) | **CHOSEN** |
| B. Read `.beads/issues.jsonl` directly | No subprocess; trivial file read | Upstream-deprecated; may be stale/absent; may be missing fields; couples us to an export format that can drift | Rejected |
| C. Talk to the embedded Dolt SQL server directly | Rich queries | Bypasses bd's contracts; brittle to schema changes; reimplements bd | Rejected |

## Consequences

- bdboard is correct-by-construction against whatever bd considers current; no
  staleness from a passive export.
- A read path always has subprocess overhead — accepted, and softened by
  in-process caches + the single subprocess gate. Cache invalidation after any
  mutation keeps reads fresh (see ADR 0005, ADR 0006).
- We depend on the `bd` binary being on PATH (configurable via `--bd`); that's
  acceptable for a tool whose entire purpose is to visualize a `bd` workspace.
- Revisit only if upstream blesses a stable file/IPC contract faster than the
  CLI.
