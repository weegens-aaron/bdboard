# Counts strip (upper-right stats)

Part of the **Board** page masthead. See also [board-lanes.md](./board-lanes.md)
(the swim lanes the counts summarize), [sse-live-refresh.md](./sse-live-refresh.md)
(the live-update pipeline that re-fetches this strip), and
[store-cache.md](./store-cache.md) (the cached snapshot the counts are derived
from). The History page reuses the **same** skeleton placeholder for its own
masthead stats strip (`#history-stats`) — see
[history-stats.md](./history-stats.md).

## What it shows

A compact, right-aligned **per-status totals strip** in the top row of the board
masthead, opposite the workspace title. It is a definition list (`<dl>`) of
small stat cells, each showing an uppercase status **label** (`<dt>`) above a
large numeric **value** (`<dd>`):

- **OPEN** — total active (open) beads.
- **BLOCKED** — beads with an unmet blocking dependency.
- **DEFERRED** — beads parked/deferred.
- **CLOSED** — beads in the board's closed window.

The set is **fixed and always rendered in this order** so the header geometry
never jitters as numbers change. Cells whose value is `0` are de-emphasized
(muted label *and* value) via the `counts-cell-zero` class — they keep their
column so the layout stays stable, but they recede visually. Cells are separated
by hairline vertical rules (`border-left`), the first cell having none.

Note: **`in_progress` is intentionally omitted.** bdboard is a single-flight
workflow tool — only one bead is in progress at a time, so a perpetual `0`/`1`
stat is noise. The In Progress swim lane already surfaces that one active bead.

## Where the data comes from

- **Route:** `GET /api/counts` → `api_counts` in `src/bdboard/app.py` (~1131).
  It renders `partials/counts.html` with a single context value, `counts`.
- **Derive layer:** `derive.counts(beads)` in `src/bdboard/derive/lanes.py`
  (~389) is a **pure** function. It tallies beads by lowercased status, then
  builds an ordered dict over the fixed `["open", "blocked", "deferred",
  "closed"]` set (including zeros). Any *non-standard* status that actually has
  beads is appended at the end (so unexpected statuses still surface rather than
  vanishing), but standard zero-count statuses are always present for layout
  stability.
- **Source of truth:** `await store.snapshot()` in `src/bdboard/store.py` (~105),
  which returns **active + board-closed** issues from the in-memory Store cache
  (lazily loaded from the bd CLI, refreshed by the file watcher). The counts are
  thus a derived view of the same cached snapshot that powers the swim lanes —
  no separate query, no separate source of truth.
- **Templates:**
  - `partials/counts.html` — the real strip: loops `counts.items()`, emitting a
    `counts-cell` per status and adding `counts-cell-zero` when `n == 0`.
  - `partials/counts_skeleton.html` — the load placeholder: mirrors the real
    structure with shimmer spans so the masthead reserves layout space (no
    reflow) while data hydrates. It takes a `cells` param (defaults to **4** to
    match the board) so the History strip can reserve **6** columns from the
    same DRY partial.

## What changes its state

The strip lives in `dashboard.html` (~14) as the `#counts` host:

```html
<div class="masthead-counts" id="counts" aria-busy="true"
     hx-get="/api/counts"
     hx-trigger="load, refresh from:body" hx-swap="innerHTML">
  {% include "partials/counts_skeleton.html" %}
</div>
```

Two triggers drive it:

1. **`load`** — fires once when the board shell paints. The page shell returns
   instantly with the skeleton inside `#counts`; HTMX then fetches `/api/counts`
   and swaps the real strip into the host (`hx-swap="innerHTML"`). This keeps
   the masthead from blocking on the bd-backed snapshot.
2. **`refresh from:body`** — the SSE live-update hook. When the file watcher
   detects a bead change, the server broadcasts a `beads_changed` SSE event
   (`GET /api/events`, `sse_events` in `app.py` ~281). The `EventSource` in
   `base.html` (~446–452) listens for it and dispatches a synthetic `refresh`
   DOM event on `<body>`; every region wired with `hx-trigger="refresh
   from:body"` (counts, lanes, etc.) re-fetches itself. So any board mutation —
   from anywhere, including another agent or terminal — re-renders the counts
   within ~one watcher cycle, no page reload.

The strip is **read-only** — it reflects state, it never mutates beads.

## Edge cases & notes

- **Zero counts stay visible.** `derive.counts` always emits the full standard
  status set even when the workspace is empty, so the strip never collapses to
  fewer columns. The template marks zero cells with `counts-cell-zero`; CSS
  mutes both label and value (`src/bdboard/static/styles.css` ~474–479) without
  removing the cell — layout stability over noise reduction.
  (Covered by `tests/test_derive_counts.py::test_counts_returns_fixed_status_set_even_when_empty`.)
- **`in_progress` is never shown.** Excluded by design (single-flight workflow).
  (Covered by `test_counts_excludes_in_progress`.)
- **Stable order regardless of data.** The fixed `status_order` is honored even
  when only some statuses have beads.
  (Covered by `test_counts_preserves_status_order_with_mixed_data`.)
- **Unexpected statuses surface, but only if non-zero.** A non-standard status
  (e.g. a future/custom status) is appended after the fixed set *only* when it
  has at least one bead — it won't pollute the strip with a zero column.
  (Covered by `test_counts_includes_custom_statuses_at_end`.)
- **Case-insensitive tally.** Statuses are lowercased before counting, so
  `OPEN`/`Open`/`open` all fold together.
  (Covered by `test_counts_case_insensitive`.)
- **Skeleton vs. real strip — aria-busy lifecycle.** `#counts` ships with
  `aria-busy="true"` and the skeleton inside it (`aria-hidden="true"`,
  `role`-presentation shimmer) so assistive tech treats the placeholder as a
  loading affordance, not content. After the first (and every) HTMX swap
  settles, the `htmx:afterSettle` handler in `base.html` (~227) flips the host's
  `aria-busy` to `"false"`. The `innerHTML` swap preserves the host element
  (and its `aria-busy` attribute) across refreshes, which is exactly why this
  attribute-flip approach works here.
- **No layout shift on hydrate.** Because the skeleton mirrors the real strip's
  cell structure and reserves the right number of columns (`cells` default 4),
  the masthead doesn't reflow when real numbers land.
  (Covered by `tests/test_snappy_transitions.py` — board shell hydrates lanes +
  counts lazily, and the masthead includes the `counts-skeleton`.)
- **Strip must stay on the top row.** The counts host belongs on the masthead
  TOP row beside the brand, **not** inside `.masthead-actions`.
  (Enforced by `tests/test_masthead_two_row_layout.py::test_counts_strip_is_not_inside_the_actions_group`.)
- **Same window as the board.** CLOSED reflects `store.snapshot()`'s
  board-closed set, which is bounded by the board's short closed window — it is
  **not** the long-window history-closed set used by the History page. For a
  longer retrospective, use the History page.
- **CLOSED tracks the active time filter (bdboard-de4z).** The board's
  12h/1d/3d time filter is purely client-side, and its `applyBoardFilter` keeps
  the CLOSED cell in lockstep with the visible Closed lane by writing the *same*
  `visibleCount` into the `[data-count-status="closed"]` cell (via
  `syncMastheadClosedCount` in `base.html`). Each counts cell carries a
  `data-count-status` hook so the JS targets the closed cell by status, not by
  the text-transformed label. The sync is guarded behind the closed lane's real
  `[data-closed-count]` badge so it never clobbers the server total with a stale
  `0` before the lane hydrates; and the `htmx:afterSettle` handler re-applies the
  saved filter when `#counts` itself settles, so an out-of-order hydration can't
  strand the unfiltered total. OPEN/BLOCKED/DEFERRED are window-invariant
  (no timestamped cards) and keep their server-rendered totals.
  (Covered by `tests/test_board_counts_filter_sync.py`.)

## Source files

- `src/bdboard/app.py` — `api_counts` route (~1131); `sse_events` SSE stream
  (~281) that drives the `refresh` trigger.
- `src/bdboard/derive/lanes.py` — `counts` (~389), the pure status-tally
  derivation.
- `src/bdboard/store.py` — `snapshot` (~105), the active+closed cached snapshot
  source of truth.
- `src/bdboard/templates/partials/counts.html` — the real counts strip
  (`counts-cell` / `counts-cell-zero`).
- `src/bdboard/templates/partials/counts_skeleton.html` — the shimmer load
  placeholder (shared with History via the `cells` param).
- `src/bdboard/templates/dashboard.html` — the `#counts` masthead host with
  `hx-get`/`hx-trigger="load, refresh from:body"` (~14).
- `src/bdboard/templates/base.html` — the `EventSource` → `refresh` dispatch
  (~446) and the `htmx:afterSettle` `aria-busy` flip (~227).
- `src/bdboard/static/styles.css` — `.counts`, `.counts-cell`, `.counts-label`,
  `.counts-value`, `.counts-cell-zero` styling (~447–479).
- `tests/test_derive_counts.py` — fixed-set/zero, in_progress exclusion, order,
  custom-status append, case-insensitivity.
- `tests/test_snappy_transitions.py` — lazy hydration + skeleton presence.
- `tests/test_masthead_two_row_layout.py` — counts strip stays on the top row.
