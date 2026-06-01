# 0005 — Live-refresh architecture (watcher → Store.refresh → SSE)

- **Status:** accepted
- **Date:** 2026-06-01
- **Relates to:** bdboard-3sf (watcher fd-safety), README "JSONL freshness",
  memories `refresh-architecture` / `cli-behavior`,
  `tests/test_watch_targets.py`, `BdClient.watch_targets()` in
  `src/bdboard/bd.py`. Backfills audit item **M3** and folds in **N1**.

> A `watchfiles` watcher observes each Dolt database's `noms/` directory (plus
> `.beads/` itself) **non-recursively**; any bd write triggers
> `Store.refresh` (re-run `bd list`), and SSE broadcasts a single
> `beads_changed` event **only when the bead list actually changed**.

## Context

bdboard wants the UI to update within a fraction of a second of any `bd` write,
without polling and without the user hitting refresh. Bead state lives in Dolt
(read via the CLI — ADR 0004), so we need to notice when the on-disk Dolt store
changes and turn that into a push to connected browsers.

The obvious approach — `awatch(".beads", recursive=True)` — is a trap on
macOS: Dolt's churning `noms/` object store contains many directories, and the
kqueue backend opens **one file descriptor per watched directory**, exhausting
`RLIMIT_NOFILE` and crashing every subsequent `bd` subprocess call (discovered
and fixed in bdboard-3sf, **N1**).

## Decision

The live-refresh pipeline is three stages:

1. **Watcher.** Watch a tiny fixed set of targets **non-recursively**: each
   Dolt database's `noms/` directory plus `.beads/` itself
   (`BdClient.watch_targets()`). This deliberately rejects recursive watching of
   the whole `.beads/` tree to stay well under the fd limit.
2. **`Store.refresh`.** On a debounced change (~250ms debounce + ~1s cooldown),
   re-run `bd list` (ADR 0004) and rebuild the in-process snapshot. Caches are
   invalidated so subsequent detail reads return post-change state.
3. **SSE broadcast.** Push a single `beads_changed` event to connected clients
   **only when the bead list structurally changed** (equality check vs the
   previous cache), so a no-op Dolt churn doesn't spam the UI.

bdboard issues **no** `bd export` calls and never writes to `.beads/`.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Non-recursive watch of `noms/` + `.beads/` → refresh → SSE** | fd-safe on macOS kqueue; ~250ms latency; pushes only real changes | Must enumerate the right `noms/` dirs per DB | **CHOSEN** |
| B. `awatch(".beads", recursive=True)` | One line; catches every change | Opens an fd per dir → exhausts `RLIMIT_NOFILE` → crashes bd subprocesses on macOS | Rejected (the bug bdboard-3sf fixed) |
| C. Periodic polling of `bd list` | Dead simple; no fs-watch quirks | Wasteful; laggy or hammering depending on interval; still needs change detection | Rejected |

## Consequences

- The UI updates within ~250ms of any bd write, fd-safely, on macOS and Linux.
- SSE traffic is minimized to actual structural changes (the equality guard).
- The watcher must know which `noms/` dirs to watch; `watch_targets()` owns that
  and is regression-tested (`tests/test_watch_targets.py`) so the fd-safety
  property can't silently regress back to recursive watching.
- Revisit if `watchfiles` gains a fd-cheap recursive backend on macOS, or if bd
  exposes a change-notification hook directly.
