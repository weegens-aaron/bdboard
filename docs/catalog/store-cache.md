# Store cache / data source of truth

Cross-cutting **infrastructure**, not a page. The `Store` is bdboard's
in-memory cache of bead snapshots: every board render, `/api/lanes`,
`/api/counts`, and the History page read from it instead of shelling out to
`bd` on each request. It sits one layer below the SSE pipeline — the watcher
calls `Store.refresh()`, and the snapshots the Store holds are what that
pipeline keeps fresh. See also [sse-live-refresh.md](./sse-live-refresh.md)
(the plumbing that triggers refreshes and broadcasts the result), and the
consumers that read the snapshot: [board-lanes.md](./board-lanes.md),
[board-closed-lane.md](./board-closed-lane.md),
[board-counts.md](./board-counts.md), and the History page
([history-chart.md](./history-chart.md), [history-stats.md](./history-stats.md),
[history-list.md](./history-list.md)). The runtime source-of-truth decision is
formalized in [ADR 0004](../decisions/0004-runtime-source-of-truth-bd-cli-json.md).

## What it shows

**Nothing directly** — the Store renders no UI. It is the in-process snapshot
that every page reads from. Its visible effect is indirect: the board lanes,
the masthead counts, the closed lane, and the History list all reflect whatever
the Store last cached. If the Store is fresh, the page is fresh; if the Store is
serving a stale snapshot (see Edge cases), the page shows that stale state until
the next refresh.

Two cooperating objects make up this layer:

- **`Store`** (`src/bdboard/store.py`) — caches the *bead list* in three
  separate snapshots (active / board-closed / history-closed) and exposes
  `snapshot_*()` read accessors plus a `refresh()` the watcher drives.
- **`BdClient`** (`src/bdboard/bd.py`) — the subprocess wrapper. Beyond running
  the list fetches the Store caches, it keeps its own **per-bead detail caches**
  (`bd show`, `bd history`) and workspace-global caches (`bd status`, memories),
  each governed by a TTL.

## Where the data comes from

The entire data path bottoms out at the `bd` CLI's JSON output — never the
`.beads/issues.jsonl` passive export ([ADR 0004](../decisions/0004-runtime-source-of-truth-bd-cli-json.md)).

```
bd CLI (bd list/show/history/status --json, backed by the dolt DB)
  → BdClient subprocess wrapper (src/bdboard/bd.py)
      ├─ list_active()         → Store active snapshot
      ├─ list_closed()         → Store board-closed snapshot (date-bounded)
      ├─ list_closed_history() → Store history-closed snapshot (window-bounded)
      └─ show_long()/history()/status_summary()/memories()
                               → BdClient per-key TTL caches
        → Store in-memory _Snapshot(beads, by_id) caches
          → HTTP routes read via snapshot_active()/snapshot_closed()/
            snapshot()/snapshot_history()/bead(id)
```

**The three Store snapshots** (`_Snapshot` = `beads` list + a pre-indexed
`by_id` dict for O(1) lookups):

- **Active** — open / in_progress / blocked / deferred issues. Fetched via
  `bd.list_active()` (no limit). Fast path for first paint; ~5KB typical.
- **Board-closed** — closed issues bounded by the board's **date window**
  (`BOARD_CLOSED_WINDOW_DAYS = 3`, from `derive/lanes.py`) via
  `bd --closed-after`. Fetched via `bd.list_closed()`. Powers both the
  Closed lane *and* the masthead CLOSED KPI so the two numbers always agree
  (bdboard-p8v).
- **History-closed** — the closed record for the long-window History page,
  sorted by `closed_at` desc, fetched via `bd.list_closed_history()`. It is
  never *count*-capped (`bd list --limit 0`); it was previously truncated to
  the 50 newest closures (`HISTORY_CLOSED_LIMIT`), which made anything older
  unreachable no matter how the page's filters were set (bdboard-a194). It IS
  *window*-bounded, though: the active range / custom-date lower bound is
  pushed down to the bd query via `--closed-after` so a narrow range fetches
  only its beads instead of slurping the whole closed table into memory on
  every snapshot (bdboard-gp06). The `all` range passes `closed_after=None`
  and stays a genuine full-table read by design. The cache is window-aware —
  a wider cached window already covers any narrower sub-window, so the Store
  only re-queries bd when a request reaches further back than what it holds.

**Read accessors** (all `async`, all lazy-loading on first call):

- `snapshot_active()` — active only. Hot path for `/api/lanes`.
- `snapshot_closed()` — board-closed only. Background load for `/api/lanes/closed`.
- `snapshot()` — active + board-closed. Powers header counts and the cached
  bead-lookup fallback.
- `snapshot_history()` — active + history-closed. History page only.
- `bead(id)` — **sync** single-bead lookup against the cached `by_id` index
  (active first, then board-closed). Sync because the only caller (the bead
  modal fallback path) is already inside a handler that awaited `snapshot()`
  upstream.

**BdClient per-key caches** (separate from the Store's list snapshots): each is
a `dict[str, CacheEntry]` keyed by bead id (or `""` for workspace-global
status). A `CacheEntry` is `fresh()` for **`SUCCESS_TTL_S = 10.0`** seconds on
success and **`ERROR_TTL_S = 30.0`** on failure — failures are cached (briefly)
to avoid hammering a flaky `bd`. The `_cached()` helper layers **in-flight
dedup** on top: if a request for the same `(subcommand, key)` is already running
its subprocess, the second caller awaits the first's `Future` instead of
spawning a duplicate process.

**Source of truth.** Reads go *exclusively* through the `bd` CLI in JSON mode,
all serialized through one `asyncio.Semaphore(1)` (`_subprocess_gate`) because
bd's embedded dolt server is single-writer and lock-prone under concurrency.
bdboard never reads `issues.jsonl` and never writes to `.beads/`
([ADR 0004](../decisions/0004-runtime-source-of-truth-bd-cli-json.md)).

## What changes its state

1. **Watcher refresh (`Store.refresh()`).** When `bd` writes the dolt store,
   `watchfiles` fires and — after the debounce/cooldown gate — calls
   `store.refresh()` (see [sse-live-refresh.md](./sse-live-refresh.md)). Refresh:
   - Re-fetches `list_active()` + `list_closed()` under `_refresh_lock`.
   - **Diffs structurally** (`prev == new`): `bd list --json` returns a
     deterministically-sorted list of dicts, so Python's `==` answers "did any
     field change" in one O(n) compare. Only the snapshots that actually changed
     are replaced.
   - Refreshes the history-closed snapshot **only if it was already
     lazy-loaded** — no point paying for a long-window fetch nobody asked for.
   - Returns `True` **iff** the bead list actually changed. That boolean is the
     SSE broadcast dedup gate (no change → no broadcast).

2. **Cache invalidation after mutations.** When `refresh()` detects a change it
   calls `self.bd.invalidate_caches()`, clearing the BdClient `show` / `history`
   / `memories` / `status` caches so the next detail/modal click hits fresh `bd`
   output instead of serving up-to-10s-old pre-mutation values. The mutating
   `BdClient` methods *also* invalidate their own caches inline (so the route's
   own follow-up read is fresh without waiting for the watcher to win the race):
   - `update_field()` — clears `_show_cache` then calls `invalidate_caches()`.
   - `remember()` / `forget()` — clear `_memories_cache`.
   - `rename_bead()` / `pour()` — call `invalidate_caches()`.

3. **Lazy first load.** Any `snapshot_*()` call when its backing snapshot is
   `None` triggers a load (`_load_active` / `_load_closed` / `_load_history`, or
   a full `refresh()` for `snapshot()`). All loads take `_refresh_lock` and
   re-check for `None` after acquiring it, so concurrent first-callers result in
   exactly one `bd list` call, not N.

## Edge cases & notes

- **Staleness window (read caches).** The BdClient per-bead caches serve data up
  to `SUCCESS_TTL_S` (10s) old. This is normally harmless, but the optimistic-
  lock precondition check in the field-edit route can't tolerate it: a stale
  cache could report an out-of-date `updated_at` and let a concurrent edit slip
  through undetected. That route therefore calls `show_long(..., fresh=True)`,
  which pops the entry from `_show_cache` first, forcing a live read. See
  [bead-inline-edit.md](./bead-inline-edit.md).
- **Cache drop on field edit.** `update_field()` clears `_show_cache` and calls
  `invalidate_caches()` *immediately* after the mutation, ahead of the watcher.
  The watcher will also fire and invalidate again, but it may lose the race
  against the route's own optimistic re-render — so the inline drop guarantees
  the acting user sees post-edit state without waiting for the debounce.
- **Serve-stale-on-failure.** If `bd list` raises inside `refresh()` (or a lazy
  load), the Store **keeps the previous snapshot** and returns `False` — better
  to serve slightly-stale data than to flash an empty dashboard on a transient
  bd hiccup. The failure is logged loudly so an operator can grep for it. On a
  *first*-ever load failure the snapshot stays `None` and accessors return `[]`
  (genuinely-empty board) until a later refresh succeeds.
- **No-op watcher fires.** A dolt-internal write or a memory-only `bd remember`
  churns files under `.beads/` but doesn't change the *bead* list. The
  structural diff returns `False`, no snapshot is swapped, and no SSE broadcast
  goes out. (Memory mutations rely on their route's *optimistic* broadcast for
  freshness — see [sse-live-refresh.md](./sse-live-refresh.md).)
- **Refresh serialization.** `refresh()` and every lazy load hold
  `_refresh_lock`, so a burst of watcher events — or a watcher refresh racing a
  lazy `snapshot()` — can't produce overlapping `bd` queries or torn cache
  writes.
- **History snapshot is decoupled on purpose.** The board's date-bounded closed
  set (`BOARD_CLOSED_WINDOW_DAYS`) and the History page's full uncapped closed
  set are different fetches and different caches. Widening the History range
  never touches the board's closed lane, and vice versa.
- **`by_id` skips malformed rows.** The index comprehension guards
  `isinstance(b.get("id"), str)`, so a row with a missing/non-string id is
  silently excluded from `bead(id)` lookups rather than crashing the index
  build.
- **Runtime source-of-truth = bd CLI JSON.** Per
  [ADR 0004](../decisions/0004-runtime-source-of-truth-bd-cli-json.md), the
  canonical runtime source of truth is the dolt DB *as read through the `bd`
  CLI*. The Store is a cache *of that*, not an alternative source. Reading
  `issues.jsonl` directly is rejected (upstream-deprecated, may be stale/absent,
  may be missing fields). The cost — subprocess overhead per fetch — is the
  accepted tradeoff, softened by these in-process caches + the single
  subprocess gate.

## Source files

- `src/bdboard/store.py` —
  - `_Snapshot` (~57): `beads` list + pre-indexed `by_id` dict.
  - `Store.__init__` (~70): the three snapshot fields + `_refresh_lock`.
  - `snapshot_active` / `snapshot_closed` / `snapshot` / `snapshot_history`
    (~80–135): lazy-loading read accessors.
  - `_load_active` / `_load_closed` / `_load_history` (~137–183): first-load
    paths with double-checked locking.
  - `refresh` (~185): re-fetch + structural diff + change-detect + cache
    invalidation; returns the broadcast-dedup boolean.
  - `bead` (~250): sync single-bead lookup via `by_id`.
- `src/bdboard/bd.py` —
  - `SUCCESS_TTL_S` / `ERROR_TTL_S` (~46–47) and `CacheEntry.fresh` (~56–64):
    the read-cache TTL policy.
  - `BdClient.__init__` (~67): the per-key caches, `_subprocess_gate`
    semaphore, and `_inflight` dedup map.
  - `list_active` / `list_closed` / `list_closed_history` (~190–235): the three
    Store-backing fetches and their window/limit constants.
  - `_cached` (~342): TTL-cache + in-flight dedup around `_run_json`.
  - `show_long` (~383): `fresh=True` cache-drop for the optimistic-lock read.
  - `history` / `status_summary` (~412–445): other per-key cached reads.
  - `invalidate_caches` (~448): clears show/history/memories/status caches.
  - `update_field` (~662) / `remember` / `forget` / `rename_bead` / `pour`:
    mutations that invalidate caches inline.
- `src/bdboard/derive/lanes.py` — `BOARD_CLOSED_WINDOW_DAYS = 3` (~40): the
  board's closed-window constant. (History fetches uncapped, no count constant.)
- `src/bdboard/app.py` — `_settle_task` (~253) / `store.refresh()` call (~268):
  the watcher path that drives refresh; mutating routes' inline
  `store.refresh()` (~942) for immediate post-mutation freshness.
- `docs/decisions/0004-runtime-source-of-truth-bd-cli-json.md` — the ADR fixing
  bd CLI JSON as the runtime source of truth.
