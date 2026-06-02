# Closed lane

Part of the **Board** page — the fifth swim lane in the lanes grid, holding
recently-closed beads. It lazy-loads separately from the open lanes for fast
first paint. See also [board-lanes.md](./board-lanes.md) (the open lanes + epic
strip it renders alongside, and the host that fetches it),
[board-time-filter.md](./board-time-filter.md) (the 12h/1d/3d strip that narrows
which closed cards are visible), [board-counts.md](./board-counts.md) (the
masthead CLOSED KPI that counts the same date-bounded set),
[history-list.md](./history-list.md) (where older closed work lives once it falls
out of the board window), [sse-live-refresh.md](./sse-live-refresh.md) (the
pipeline that re-fetches the lane), and [store-cache.md](./store-cache.md) (the
cached closed snapshot it derives from).

## What it shows

A single swim lane titled **Closed** containing cards for beads that have
recently been closed/resolved/done — the board's "recent wins" column.

- **Lane title + count badge** — the heading shows `Closed` and a count badge
  (`data-closed-count="total"`) reflecting how many closed cards are currently
  *visible*. The badge is updated client-side by the time filter, so it tracks
  the user's selected window rather than the raw fetched total.
- **Cards** — each closed bead renders as a `.bead-card` showing its id, a
  priority pill (`P0`–`Pn`), the title, and a meta row (assignee, issue type,
  dependency count). Every card carries a `data-closed-at="<timestamp>"`
  attribute, which is what the time filter keys off of (closed cards are the
  only timestamped cards on the board).
- **Click target** — clicking a card fires an HTMX `GET /api/bead/<id>` into the
  `#bead-modal` target to open the detail view, identical to open-lane cards.
- **Ordering** — most-recently-closed first (sorted by `closed_at` descending),
  so the freshest wins sit at the top of the lane.

The lane is **read-only**: it reflects closed state and never mutates beads.

## Where the data comes from

- **Route:** `GET /api/lanes/closed` → `api_lanes_closed` in
  `src/bdboard/app.py` (~443). It renders `partials/closed_lane.html` with a
  single context value, `closed`. This route is deliberately split out from
  `GET /api/lanes` (~414): the closed lane is the heaviest part of the board
  (~495KB on large workspaces), so loading it *after* the active lanes paint
  cuts time-to-first-paint from a ~500KB fetch to ~5KB — a ~100x improvement
  (bdboard-0yy).
- **Source of truth:** `await store.snapshot_closed()` in `src/bdboard/store.py`
  (~94) — closed issues from the in-memory Store cache, lazily loaded on first
  call and refreshed by the file watcher. Same cache the rest of the board uses,
  no separate source of truth.
- **Date-bounded fetch:** the closed cache is populated by `BdClient.list_closed`
  in `src/bdboard/bd.py` (~175), which calls
  `bd list --status closed --closed-after <cutoff> -- --limit 0`. The
  cutoff is `now - BOARD_CLOSED_WINDOW_DAYS` (3 days). Crucially the board's
  closed set is bounded by a **date window**, not a static count cap — this keeps
  the lane count and the masthead CLOSED KPI consistent because both reflect the
  same date-bounded set (bdboard-p8v).
- **Ordering note:** the closed list arrives from bd already sorted by
  `closed_at` descending (`--sort closed`). The route hands it straight to the
  template without re-bucketing. (The pure derivation `derive.lanes()` in
  `src/bdboard/derive/lanes.py` *also* produces a `closed` bucket sorted
  `closed_at` desc, but the dedicated `/api/lanes/closed` route uses the closed
  snapshot directly rather than running the full lane split.)
- **Template:** `partials/closed_lane.html` — the swapped-in lane content: the
  `Closed` title, the count badge, and the card list (with an `(empty)` fallback
  row). The lane *chrome/skeleton* lives in `partials/lanes.html` (the
  `.lane-closed` host), which this partial replaces.

## What changes its state

The lane host is the `.lane-closed` div in `partials/lanes.html` (~73):

```html
<div class="lane lane-closed"
     data-lane="closed"
     hx-get="/api/lanes/closed"
     hx-trigger="load, refresh from:body"
     hx-swap="innerHTML">
  {# skeleton shimmer while loading #}
</div>
```

Three things change what it shows:

1. **`load`** — fires once when the lanes region partial swaps in. The host ships
   with a shimmer skeleton (3 placeholder cards, `aria-hidden="true"`) so the
   slot looks alive immediately; HTMX then fetches `/api/lanes/closed` and swaps
   the real content in (`hx-swap="innerHTML"`). This is what keeps the heavy
   closed payload off the first-paint critical path.
2. **`refresh from:body`** — the SSE live-update hook. When the file watcher
   detects a `.beads/` change, the server broadcasts a `beads_changed` SSE event
   (`GET /api/events`, `sse_events` in `app.py` ~281); the `EventSource` in
   `base.html` dispatches a synthetic `refresh` DOM event on `<body>`, and this
   lane (like the other refresh-wired regions) re-fetches itself. So closing a
   bead anywhere — another agent, a terminal, the modal — re-renders the lane
   within ~one watcher cycle, no page reload.
3. **Time filter (client-side)** — the masthead 12h/1d/3d strip calls
   `applyBoardFilter(filter)` in `base.html` (~340). It walks
   `.bead-card[data-closed-at]` cards in the closed lane, hides any whose
   `closed_at` age exceeds the selected window, and rewrites the count badge to
   the visible total. This is pure DOM show/hide — it does **not** re-fetch; the
   server already bounded the set to the 3-day window, and the filter narrows it
   further in-browser. The selection persists in `sessionStorage` under
   `bdboard-time-filter` (default `1d`) and is re-applied after each SSE refresh.

## Edge cases & notes

- **3-day historical limit.** The board only ever fetches beads closed within
  `BOARD_CLOSED_WINDOW_DAYS = 3` (`derive/lanes.py` ~40, applied at fetch time in
  `bd.list_closed`). Anything closed earlier never reaches the board — it lives
  on the History page, which uses a separate uncapped path
  (`list_closed_history`, `bd list --limit 0`) so its wider
  7d/30d/90d/All ranges don't silently miss older closed work (bdboard-a194). The
  3-day fetch window is also the max the board time filter offers (12h/1d/3d),
  by design — filtering can narrow within the fetch window but never widen
  beyond it.
- **Date-bounded, not count-bounded.** Unlike the History page, the board's
  closed set has no static count cap (`--limit 0`); it's purely the 3-day
  window. This is what keeps the Closed lane count and the masthead CLOSED KPI
  in agreement — they count the same date-bounded set.
- **Ordering = closed_at desc.** Most-recently-closed first. The order comes from
  bd's `--sort closed`; cards missing a `closed_at` fall back to `updated_at` in
  the pure-derivation path (`derive.lanes`), but the dedicated closed route
  trusts bd's sort directly.
- **Empty state.** If no beads were closed in the window, the card list renders a
  single `(empty)` muted row (the `{% else %}` branch of the `{% for %}` loop)
  rather than collapsing the lane — layout stays stable. The badge reads
  `0`.
- **Count badge tracks the filter, not the fetch.** `data-closed-count="total"`
  initially renders `{{ closed|length }}` server-side, but `applyBoardFilter`
  overwrites it with the *visible* count whenever a narrower window (e.g. 12h or
  1d) is active. So the badge can legitimately read less than the number of cards
  in the DOM — the extra cards are `display:none`, not removed.
- **Missing `data-closed-at`.** The template only emits `data-closed-at` when
  `b.closed_at` is present. A closed card without that attribute is treated as
  always-visible by the filter (it short-circuits to shown) and still counts —
  defensive handling for malformed/legacy beads.
- **Skeleton vs. content accessibility.** While loading, the skeleton card list
  is `aria-hidden="true"` so assistive tech waits for real content; the swapped
  partial replaces it entirely with the live list.
- **Conservative blocked detection caveat (inherited).** The first-paint active
  fetch can't see closed beads, so a bead depending on a now-closed bead may show
  as blocked in the open lanes until the next refresh. This is an open-lane
  artifact, not a closed-lane one, but it's why the closed lane and full snapshot
  exist as separate paths — see [board-lanes.md](./board-lanes.md).

## Source files

- `src/bdboard/app.py` — `api_lanes_closed` route (~443); `api_lanes` (~414) for
  the split it complements; `sse_events` SSE stream (~281) that drives the
  `refresh` trigger.
- `src/bdboard/store.py` — `snapshot_closed` (~94), the cached closed snapshot
  (source of truth); `_load_closed` (~151) lazy loader.
- `src/bdboard/bd.py` — `list_closed` (~175): the date-bounded
  `--closed-after <cutoff> --sort closed --limit 0` fetch.
- `src/bdboard/derive/lanes.py` — `BOARD_CLOSED_WINDOW_DAYS = 3` (~40),
  `CLOSED_STATUSES`, and the `closed` bucket in `lanes()` sorted `closed_at`
  desc (~330).
- `src/bdboard/templates/partials/closed_lane.html` — the swapped-in lane
  content: title, `data-closed-count` badge, timestamped cards, `(empty)`
  fallback.
- `src/bdboard/templates/partials/lanes.html` — the `.lane-closed` host (~73)
  with `hx-get="/api/lanes/closed"` / `hx-trigger="load, refresh from:body"` and
  the loading skeleton.
- `src/bdboard/templates/base.html` — `BOARD_TIME_WINDOWS` (~330) and
  `applyBoardFilter` (~340) that show/hide closed cards and rewrite the count;
  the `EventSource` → `refresh` dispatch that re-fetches the lane.
