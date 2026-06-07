# 0005 — Live-refresh architecture (watcher → Store.refresh → SSE)

- **Status:** accepted
- **Date:** 2026-06-01
- **Relates to:** bdboard-3sf (watcher fd-safety), bdboard-ywep
  (revision-signature self-feedback guard, commit `f2179e3`), bdboard-xbc7
  (watcher debounce/cooldown timing, commit `2429217`), README "JSONL
  freshness", memories `refresh-architecture` / `cli-behavior` /
  `board-livesync-chain`, `tests/test_watch_targets.py`,
  `BdClient.watch_targets()` / `BdClient.revision_signature()` in
  `src/bdboard/bd.py`, `Store.refresh()` in `src/bdboard/store.py`,
  `RefreshScheduler` in `src/bdboard/watcher.py`. Backfills audit item **M3**,
  folds in **N1**, and amends in the revision-signature skip (audit defect
  **D2**, bdboard-mol-lon).

> A `watchfiles` watcher observes each Dolt database's `noms/` directory (plus
> `.beads/` itself) **non-recursively**; any bd write triggers a
> debounced/cooled `Store.refresh`, which first compares each Dolt manifest's
> **root hash** and **skips the `bd list` subprocess entirely when it is
> unchanged** (the self-feedback-loop guard); only when the bead list actually
> changed does SSE broadcast a single `beads_changed` event.

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

There is a second, subtler trap. A `bd list` is **read-only** at the bead level,
but running it still makes Dolt rewrite the `manifest` inside the watched
`noms/` directory (new inode + bumped mtime). So the naive "any watcher event →
re-run `bd list`" rule from the original three-stage design feeds **our own
read** straight back into the watcher: refresh → read → watcher fires → event →
refresh, forever. Worse, on a large `noms/` store `bd list` is *slower* than the
self-trigger latency, so each in-flight refresh gets cancelled before it
finishes and the board **never updates until relaunch** (the live-sync wedge
fixed in bdboard-ywep). The structural-change equality check at stage 3 does
**not** save us here — the loop starves before any refresh completes, so the
equality check is never reached.

## Decision

The live-refresh pipeline is three stages, with a load-bearing precondition
guarding stage 2:

1. **Watcher.** Watch a tiny fixed set of targets **non-recursively**: each
   Dolt database's `noms/` directory plus `.beads/` itself
   (`BdClient.watch_targets()`). This deliberately rejects recursive watching of
   the whole `.beads/` tree to stay well under the fd limit.
2. **`Store.refresh`** — *gated by the revision-signature skip.* On a debounced
   change (**~250ms debounce + ~1s cooldown**, `WATCHER_DEBOUNCE_S` /
   `WATCHER_COOLDOWN_S`, scheduled by `RefreshScheduler` in `watcher.py`),
   `Store.refresh()` first computes `BdClient.revision_signature()` — the set of
   `(manifest_path, manifest_bytes)` for every `.dolt/noms/manifest` under
   `.beads/embeddeddolt/`, i.e. Dolt's current **root hash** per database. If
   that signature is **non-empty, a populated cache already exists, and it is
   identical to the signature of the last successful refresh**, the committed
   Dolt state cannot have changed — this event is our own read echoing back (or
   unrelated FS churn) — so we **skip the `bd list` subprocess entirely** and
   report "no change". This is the guard that breaks the
   refresh→read→event→refresh self-feedback loop described in Context. Only when
   the signature differs (or is empty, see below) do we actually re-run `bd
   list` (ADR 0004) and rebuild the in-process snapshot, invalidating caches so
   subsequent detail reads return post-change state.
   - **Empty signature = always refresh.** A workspace with no Dolt manifest
     (legacy JSONL-only) yields an empty signature; that is treated as "no
     signal available," so we **never skip** and behavior there is unchanged.
   - The skip does **not** subsume the stage-3 equality check: the signature
     skip is a *cheap subprocess-avoidance* gate (root-hash bytes), while the
     equality check is the *broadcast-dedup* gate (bead-list contents). The
     manifest can flip root hash on a Dolt-internal or memory-only write that
     changes no issue state, so we still record the new signature but suppress
     the SSE event at stage 3.
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
| D. Always re-run `bd list` on any watcher event (the original three-stage rule, no signature gate) | Simplest stage-2 logic | The read-only `bd list` rewrites the watched `noms/` manifest, re-triggering the watcher → refresh self-feedback loop that starves real updates (live-sync wedge, bdboard-ywep). The stage-3 equality check can't save it — the loop starves first | Rejected (superseded by the revision-signature skip) |

## Consequences

- The UI updates within ~250ms of any bd write, fd-safely, on macOS and Linux.
- SSE traffic is minimized to actual structural changes (the equality guard).
- The refresh self-feedback loop is structurally impossible while the
  revision-signature skip is in place: a read-only `bd list` can jiggle the
  `noms/` files but cannot change the manifest root hash, so the next refresh
  takes the cheap skip path instead of spawning another `bd list`. **Do not
  remove the signature skip as "redundant with the stage-3 equality check"** —
  they guard different failure modes (subprocess avoidance vs broadcast dedup),
  and dropping the skip reintroduces the live-sync wedge (bdboard-ywep).
- The watcher must know which `noms/` dirs to watch; `watch_targets()` owns that
  and is regression-tested (`tests/test_watch_targets.py`) so the fd-safety
  property can't silently regress back to recursive watching.
- The debounce/cooldown timing (`~250ms` / `~1s`, `RefreshScheduler`) is part of
  the contract: it absorbs the burst of file writes from one logical `bd`
  command and prevents back-to-back refreshes under sustained activity. It must
  not be "simplified" away — see bdboard-xbc7 for the trailing/isolated-write
  drops that motivated the trailing-debounce design.
- Revisit if `watchfiles` gains a fd-cheap recursive backend on macOS, if bd
  exposes a change-notification hook directly, or if bd ever stops mutating the
  `noms/` manifest on read-only commands (which would make the signature skip
  unnecessary).
