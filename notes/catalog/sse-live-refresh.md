# SSE live-refresh pipeline

Cross-cutting **infrastructure**, not a page. This is the plumbing that makes
bdboard feel "live": when bead data changes on disk — from this browser, another
tab, a terminal `bd` command, or another agent entirely — every live region
re-fetches itself within ~one watcher cycle, with no page reload. It is the
mechanism behind the `hx-trigger="load, refresh from:body"` you'll see all over
the templates. See also [store-cache.md](./store-cache.md) (the in-memory
snapshot this pipeline refreshes), and the consumers it drives:
[board-counts.md](./board-counts.md), [board-lanes.md](./board-lanes.md),
[board-closed-lane.md](./board-closed-lane.md), the History page
([history-chart.md](./history-chart.md), [history-stats.md](./history-stats.md),
[history-list.md](./history-list.md)), and the Memory page
([memory-list.md](./memory-list.md)).

## What it shows

The pipeline has **no UI of its own** — it renders nothing. Its job is to push a
single signal ("bead data changed, go re-fetch") to the browser so the *other*
features stay fresh on their own. The only user-visible trace of it is the small
**live-status pill** in the masthead, driven by the same `EventSource`
connection:

```html
<span class="live-dot" id="live-dot" aria-hidden="true"></span>
<span id="live-status">connecting…</span>
```

Its three states map directly to the SSE connection lifecycle
(`base.html` ~446–448):

- **`connecting…`** — initial markup, before the `EventSource` opens.
- **`live · push`** (`live-on`) — connection is open; live updates are flowing.
- **`reconnecting…`** (`live-off`) — connection dropped; the browser's built-in
  `EventSource` auto-reconnect (exponential backoff) is healing it.

The dot is `aria-hidden` (decorative); the status text carries the meaning for
assistive tech.

## Where the data comes from

The pipeline is a one-way observer chain. bdboard never writes the source of
truth — it watches it and reacts:

```
bd writes dolt
  → files mutate inside .beads/embeddeddolt/<db>/.dolt/noms/
    → watchfiles.awatch fires a batch of FS events
      → _settle_then_refresh() debounce + cooldown
        → Store.refresh() runs `bd list --json` (active + closed)
          → if the bead list actually changed → bus.broadcast("beads_changed")
            → every open /api/events SSE stream yields the event
              → browser EventSource dispatches a synthetic 'refresh' on <body>
                → every hx-trigger="refresh from:body" region re-fetches its partial
```

Component by component:

- **The watcher** — `_watch_beads()` in `src/bdboard/app.py` (~191), started as
  a background task by the FastAPI `lifespan` context manager (~165). It calls
  `bd.watch_targets()` (`src/bdboard/bd.py` ~100) to get a **small, fixed set of
  directories** and watches them **non-recursively** via
  `watchfiles.awatch(*targets, recursive=False)`. Targets are each dolt db's
  `.dolt/noms/` dir plus `.beads/` itself as a catch-all. (See the fd-exhaustion
  note under Edge cases for *why* it's non-recursive.)
- **The debounce/cooldown gate** — `_settle_then_refresh()` (~239) and its
  helper `_settle_task()`. This is the heart of the "settle-then-refresh"
  behavior; details below.
- **The refresh** — `store.refresh()` in `src/bdboard/store.py` (~183). Runs
  `bd list --json` for active + closed sets, diffs them against the
  cached snapshot, and **returns `True` only if the bead list actually
  changed**. That return value is the broadcast dedup gate — a dolt-internal
  write (or a memory-only `bd remember`) that doesn't change the issue list
  produces `False` and **no broadcast**.
- **The bus** — `EventBus` in `src/bdboard/events.py`, a tiny in-process
  pub/sub. `bus.broadcast("beads_changed")` pushes the same event onto one
  bounded queue per open SSE connection (fan-out). Each subscriber drains its
  own queue at its own pace.
- **The SSE endpoint** — `GET /api/events` → `sse_events` in `app.py` (~281).
  Returns a `StreamingResponse` of `media_type="text/event-stream"`. On connect
  it immediately yields a `beads_changed` **bootstrap** event (so a fresh tab
  renders without waiting for a file change), then loops: emit any bus event as
  `event: beads_changed\ndata: <ts>\n\n`, or a `: heartbeat\n\n` comment every
  15s of idle to keep proxies from killing the long-lived connection.
- **The browser** — `base.html` (~446) opens a single `EventSource('/api/events')`
  per page load. On `beads_changed` it dispatches a synthetic
  `new CustomEvent('refresh')` on `document.body`. That is the "broadcast" half
  of the `refresh from:body` wiring.

The **source of truth** is never a file bdboard parses directly. `.beads/issues.jsonl`
is a deprecated passive export and is **not** read here; `bd list --json` is the
only data source in-process.

## What changes its state

Two independent paths can fire a `beads_changed` broadcast:

1. **File-watcher path (the default).** Any `bd` write — from this app's own
   mutating routes, another terminal, or another agent — churns files under
   `.beads/`. `watchfiles` fires, the debounce settles, `store.refresh()` runs,
   and if the bead list changed, the bus broadcasts. This is how cross-process
   and cross-tab freshness works for free.

2. **Optimistic broadcasts from mutating routes.** After a successful mutation,
   several routes call `await bus.broadcast("beads_changed")` **directly**,
   *before* the watcher would have caught up. This bypasses the 250ms debounce so
   the **acting user** (and every other tab) sees the change immediately rather
   than waiting for the FS event to settle. Known emitters:
   - Memory create / delete (`api_create_memory` / `api_delete_memory`,
     `app.py` ~658) — also necessary because a memory-only write may not change
     the *bead* list, so the watcher's diff would return `False` and never
     broadcast on its own.
   - Field edits (`update_field` route) — see [bead-inline-edit.md](./bead-inline-edit.md).
   - Formula pour (`pour_formula` route) — see
     `partials/formula_pour_result.html`.

   The watcher will *also* fire shortly after for these, but the broadcast dedup
   in `store.refresh()` means the redundant watcher pass is cheap (no second
   broadcast when nothing further changed).

On the **client** side, the consumers that re-fetch on each `refresh` are every
region wired with `hx-trigger="load, refresh from:body"`:

- Board: `#counts` and `#lanes` in `dashboard.html` (~16, ~56).
- Memory: the list region in `memory.html` (~68).
- History: re-fetched on `refresh from:body` (`app.py` ~389).

The `load` half paints each region lazily on first render; the `refresh from:body`
half keeps it live thereafter — one trigger string, two jobs, fully DRY.

## Edge cases & notes

- **Settle-then-refresh: debounce + cooldown.** A single `bd update` typically
  writes 3–5 files (manifest, journal.idx, lock, …) in a burst. Two guards in
  `_settle_task()` (`app.py` ~255) collapse that into one refresh:
  - **Debounce (`WATCHER_DEBOUNCE_S = 0.25`)** — each FS batch cancels any
    in-flight settle task and starts a fresh 250ms timer. A continuous stream of
    events keeps pushing the actual refresh out until the writes *stop*; only
    then does the timer fire. 250ms is longer than the burst, shorter than human
    perception.
  - **Cooldown (`WATCHER_COOLDOWN_S = 1.0`)** — after a refresh completes,
    further refreshes are swallowed for 1s. This stops a sustained write storm
    (dolt commit + auto-export fan-out + git-add hook) from chain-firing at full
    FS speed. The next event *after* cooldown expires starts a fresh
    debounce+refresh, so genuine subsequent changes are not lost — just
    coalesced.
- **Broadcast dedup.** `store.refresh()` returns `True` only when the active or
  closed bead list actually changed vs the cached snapshot. Dolt-internal writes
  and memory-only `bd remember` don't change the bead list → `False` → no
  watcher broadcast. (Memory mutations therefore rely on their route's
  *optimistic* broadcast, which is why those routes call `bus.broadcast`
  explicitly — covered by `tests/test_memory_mutations.py`
  `test_create_memory_broadcasts_sse_on_success` /
  `test_delete_memory_broadcasts_sse_on_success`.)
- **Non-recursive watch (fd-exhaustion guard).** `watch_targets()` watches a
  tiny fixed set of dirs **non-recursively**, not the whole `.beads/` tree. The
  recursive whole-tree watch opened one kqueue fd *per directory* on macOS;
  dolt's churning `noms/` object store has hundreds of dirs and exhausted
  `RLIMIT_NOFILE` (often 256). Once fds ran out,
  `asyncio.create_subprocess_exec` could no longer open pipes, so `bd list --json`
  and `bd show` both crashed with `OSError [Errno 24] Too many open files`.
  Every meaningful bd write still touches `manifest`/`journal.idx` inside a
  `noms/` dir, so non-recursive watching keeps sub-second latency without the
  blowup.
- **Client reconnection.** `EventSource` has **built-in auto-reconnect** with
  exponential backoff. A server restart or transient drop heals within a few
  seconds; the status pill shows `reconnecting…` (`live-off`) meanwhile and
  flips back to `live · push` on the next `open`. On reconnect the server's
  bootstrap event re-syncs the client immediately rather than waiting for the
  next file change.
- **Bootstrap on connect.** `sse_events` yields a `beads_changed` event the
  instant a client subscribes, so a freshly-loaded (or reconnected) tab renders
  current data without waiting for the first FS change.
- **Heartbeat keeps the pipe alive.** With no events for 15s the stream emits a
  `: heartbeat\n\n` SSE comment. Comments don't fire any client event handler —
  they just keep proxies/load balancers (typical 30–60s idle timeout) from
  killing the long-lived connection. `Cache-Control: no-cache` and
  `X-Accel-Buffering: no` headers also keep intermediaries from buffering the
  stream.
- **Lossy-by-design backpressure.** Each subscriber has a bounded queue
  (`_QUEUE_SIZE = 16`, `events.py`). On overflow the bus drops the **oldest**
  event to make room for the newest. A slow client must never block the
  broadcaster — and since every event triggers the *same* full re-fetch, a
  dropped event costs at most a freshness blip, never correctness.
- **Watcher resilience.** `_watch_beads()` runs in an infinite loop: if `.beads/`
  doesn't exist yet it waits 2s and retries; if the watcher crashes it logs and
  restarts in 2s. `store.refresh()` on a `bd list` failure keeps the previous
  snapshot (serve stale rather than flash empty) and returns `False`.
- **Refresh serialization.** `store.refresh()` holds `_refresh_lock`, so a burst
  of watcher events (or a watcher refresh racing a lazy `snapshot()`) can't
  produce overlapping bd queries or torn cache writes.
- **`hx-trigger="load, refresh from:body"` is the contract.** The `from:body`
  modifier is essential: the `refresh` event is dispatched on `<body>`, and HTMX
  regions listen for it *bubbling up from* the body element. Every live region
  uses the identical trigger string — adding a new live region is just a matter
  of using the same string, no JS changes.

## Source files

- `src/bdboard/app.py` —
  - `lifespan` (~165): starts/stops the watcher background task.
  - `_watch_beads` (~191): `watchfiles.awatch` loop over non-recursive targets.
  - `_settle_then_refresh` / `_settle_task` (~239–272): debounce + cooldown +
    dedup-gated `store.refresh()` → `bus.broadcast`.
  - `sse_events` (~281): the `GET /api/events` SSE stream (bootstrap + heartbeat).
  - `WATCHER_DEBOUNCE_S` / `WATCHER_COOLDOWN_S` (~160): the timing constants.
  - mutating routes' optimistic `bus.broadcast("beads_changed")` (e.g. memory
    create/delete ~658).
- `src/bdboard/events.py` — `EventBus` (`broadcast`, `subscribe`,
  `subscriber_count`); per-subscriber bounded-queue fan-out with drop-oldest
  backpressure.
- `src/bdboard/store.py` — `refresh` (~183): re-fetch + diff + change-detect that
  drives the broadcast dedup; `snapshot` (~105) lazy-loads via the same refresh.
- `src/bdboard/bd.py` — `watch_targets` (~100): the non-recursive watch-dir set
  and the fd-exhaustion rationale; `beads_dir` (~94).
- `src/bdboard/templates/base.html` — the `EventSource('/api/events')` setup,
  the `beads_changed` → `document.body.dispatchEvent(new CustomEvent('refresh'))`
  bridge, and the live-status pill (~159–160, ~432–453).
- `src/bdboard/templates/dashboard.html` — `#counts` / `#lanes` hosts wired with
  `hx-trigger="load, refresh from:body"` (~16, ~56).
- `src/bdboard/templates/memory.html` — memory list region wired with the same
  trigger (~68).
- `src/bdboard/templates/partials/formula_pour_result.html` — notes the pour
  route's optimistic SSE broadcast.
- `tests/test_memory_mutations.py` — asserts optimistic `beads_changed`
  broadcast on memory create/delete.
- `tests/test_field_edit.py`, `tests/test_field_edit_concurrency.py`,
  `tests/test_field_edit_status_gate.py`, `tests/test_formula_pour.py` — stub
  `bus.broadcast` to assert optimistic broadcasts from those mutating routes.
