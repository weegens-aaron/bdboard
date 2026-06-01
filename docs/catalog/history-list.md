# Paginated history list

The third feature of the **History** page, rendered below the chart. See also
[history-chart.md](./history-chart.md) (the created-vs-closed grouped-bar strip
served by the *same* `/api/history` response), [history-stats.md](./history-stats.md)
(the KPI strip swapped out-of-band into the masthead by that same response),
[bead-modal.md](./bead-modal.md) (the shared detail modal each list card opens),
[store-cache.md](./store-cache.md) (the long-window snapshot the list slices),
and [sse-live-refresh.md](./sse-live-refresh.md) (the pipeline that re-fetches
the region on bead changes).

## What it shows

A **"Closed beads"** section of vertical cards — one card per closed bead,
**newest-closed first** — with a count badge in the section heading showing the
*full* in-window total (pre-pagination) and a **pager** beneath the list.

Each card surfaces:

- the **bead id** (monospace) and, when present, a **priority chip** (`P0`–`P5`);
- a **relative close time** (e.g. *"2 days ago"* via the `humanize_ts` filter)
  with the raw `closed_at` timestamp in the `title` tooltip;
- the **title**;
- a meta row with the **assignee** (when set) and the **close reason** (when set).

Clicking anywhere on a card opens the shared **bead detail modal** — the list
does not rebuild the modal, it reuses the board's (`hx-get="/api/bead/{id}"`
targeting `#bead-modal`).

The **pager** (`<nav aria-label="History pages">`) holds:

- a **‹ Newer** button (shown only when `page > 1`) → previous page;
- a **Page N** indicator;
- an **Older ›** button (shown only when `has_more`) → next page;
- a **Per page** `<select>` offering exactly **25 / 50 / 100**, defaulting to
  **50**, reflecting the active size after every swap.

The list is **read-only** — it reflects closed work, it never mutates beads.
Range and pagination state are URL-borne (carried in the buttons' `hx-get`
URLs), not element-borne, keeping the wiring DRY.

## Where the data comes from

- **Route:** `GET /api/history` → `api_history` in `src/bdboard/app.py` (~468).
  It is a **pure derivation** over the existing snapshot (design §4) — no new
  bd call per request. The route normalises `range`, clamps `page`/`page_size`,
  resolves any custom window, and calls `derive.history_window(...)`, handing
  the resulting `window` dict to `partials/history.html`. The same response also
  carries the chart series and the OOB masthead stats.
- **Query params:** `range` (`7d`/`30d`/`90d`/`all`, default `30d`), `page`
  (1-based), `page_size` (`25`/`50`/`100`, default `50`), and the optional
  custom window `from_date`/`to_date` (`YYYY-MM-DD`).
- **Derive layer:** `derive.history_window(beads, range_key, page, page_size,
  from_date, to_date)` in `src/bdboard/derive/history.py` (~162). It is a
  **pure** function that:
  1. resolves window bounds once via `_resolve_bounds` (a custom from/to
     selection supersedes the `range` preset);
  2. filters to closed beads inside `[cutoff, ceiling)` via `_closed_in_window`
     (closed by the board's `CLOSED_STATUSES` rule; beads with no parseable
     `closed_at` are excluded — they can't be placed on a timeline);
  3. sorts **newest-closed first** with a stable id tiebreak
     (`key=lambda b: (-_epoch(b.closed_at), b.id)`);
  4. slices the requested page and returns
     `{items, page, page_size, total, has_more}` — `total` is the full in-window
     count (pre-pagination), `has_more` is `end < total`.
  Page-size validation lives in `derive.clamp_page_size` (~40), the single
  source of truth shared by the route and the selector.
- **Source of truth:** `await store.snapshot_history()` in `src/bdboard/store.py`
  (~117), which returns the **active + history-closed** (count-capped) issues.
  The History page deliberately uses the long-window history-closed cache —
  **not** the board's short date-windowed closed set — so ranges wider than the
  board's closed window don't silently miss older closed work (bdboard-p8v).
  Underneath it is still the in-memory Store cache (lazily loaded from the bd
  CLI, refreshed by the file watcher).
- **Templates:**
  - `templates/history.html` — the page shell; hosts the `#history-region`
    swap target with an instant skeleton.
  - `templates/partials/history.html` — renders the `.history-list-section`:
    the count badge, the `.history-list` of `.bead-card.history-card` cards, and
    the `.history-pager` (Newer/Older + page indicator + page-size selector).
  - `templates/partials/history_skeleton.html` — the load placeholder (six
    `.skeleton-row` blocks reserve the list space).

## What changes its state

The list lives inside `#history-region`, the single HTMX swap target on
`history.html`:

```html
<section id="history-region" hx-get="/api/history"
         hx-trigger="load, refresh from:body" hx-swap="innerHTML">
  {% include "partials/history_skeleton.html" %}
</section>
```

Triggers and controls that re-render it:

1. **`load`** — fires once on first paint, fetching the default **30d** window,
   **page 1**, size **50**. The shell returns instantly with the skeleton; HTMX
   then swaps in the real region.
2. **Range filter** — the `7d / 30d / 90d / All` (and **Custom**) controls each
   `hx-get` `/api/history` for `#history-region`. Changing the range
   **resets to page 1** (the badges hard-code `page=1`) but **preserves the
   active page size**, re-deriving the in-window closed set against the new
   window.
3. **Custom date range** — the Custom popover submits `from_date`/`to_date`; a
   valid custom selection **supersedes** the `range=` preset for the list (and
   everything else), resolved in one place by `derive._resolve_bounds`. The
   pager and page-size selector reuse the custom query string (`window_qs`) so
   paging stays inside the chosen window rather than snapping back to a preset.
4. **Pager Newer / Older** — re-fetch the adjacent page within the current
   window (`page ± 1`), preserving the active page size and any custom window.
5. **Page-size selector** — changing it **resets to page 1** and re-swaps the
   region with the chosen size. The `base.html` persistence JS mirrors the
   choice into `localStorage` so it survives reloads and navigation (like the
   theme toggle); the selected `<option>` is rendered server-side from
   `active_page_size` so it reflects state after every swap.
6. **`refresh from:body`** — the SSE live-update hook. When the file watcher
   detects a `.beads/` change, the server broadcasts a `beads_changed` event
   (`GET /api/events`); the `EventSource` in `base.html` dispatches a synthetic
   `refresh` on `<body>` and the region re-fetches. This SSE-driven refresh
   re-fetches the **default** window with **no query params** — i.e. it snaps
   back to 30d / page 1 / size 50, the same "snap back to fresh data" behaviour
   the board's lanes region has; the user re-clicks a range/page to re-scope.

## Edge cases & notes

- **Page size clamped to {25, 50, 100}, default 50.** `derive.clamp_page_size`
  parses the input and returns it only if it is a member of `HISTORY_PAGE_SIZES`;
  any missing, garbage, or out-of-set value (e.g. a tampered `?page_size=9999`)
  falls back to `HISTORY_PAGE_SIZE` (50). One source of truth shared by the
  route and the selector so a bad query param can never break paging.
- **Invalid range degrades to the 30d default.** The route lowercases/strips
  `range` and, if it is not in `HISTORY_RANGES`, resets it to
  `DEFAULT_HISTORY_RANGE` (`30d`) before deriving — so a bad `?range=` produces
  a sensible window rather than an error.
- **Page is floored to 1.** Both the route (`page = max(1, page)`) and
  `history_window` clamp non-positive pages to 1, so `?page=0` or negative
  values never produce a negative slice.
- **Out-of-range page → graceful empty.** Asking for a page beyond the data
  yields `items=[]` and `has_more=False`. The template then shows a *"Nothing on
  page N — back to page 1"* message with a button that re-fetches page 1 of the
  current window, rather than a blank section.
- **Empty window.** When nothing closed in the window the section shows a muted
  empty-state line: *"Nothing closed in the last &lt;window&gt; — try a wider
  range."* (or *"Nothing closed in &lt;window&gt; — try a wider range."* for a
  custom selection). The count badge reads `0`.
- **Newest-closed first, stable.** Sorting is by descending `closed_at` with an
  id tiebreak, so beads closed at the same instant keep a deterministic order
  across pages (no items skipped or duplicated at page boundaries).
- **Beads without a parseable `closed_at` are excluded** — they cannot be placed
  on the timeline, so they never appear in the list (matching the chart's
  closed-series rule).
- **Inverted custom bounds are swapped.** `custom_bounds` swaps a `from` that is
  after `to` so the window stays meaningful; the `to` day is inclusive (the
  ceiling is the exclusive start of the *next* day).
- **Count badge is the full total, not the page size.** The `{{ total }}` badge
  reflects every closed bead in the window, even when only one page is shown —
  it is `window["total"]`, computed pre-pagination.
- **Long-window source, not the board window.** The list slices
  `store.snapshot_history()` (count-capped history-closed), so the `90d`/`All`
  ranges surface closed work older than the board's short closed window
  (bdboard-p8v). The cap is a count cap, not a date cap.
- **`history_skeleton.html` placeholder.** The list region is reserved by six
  `.skeleton-row` blocks (and a title line) that mirror the real layout so the
  page paints instantly and hydrates without a layout shift. It is decorative
  (`aria-hidden`); `#history-region` carries `aria-busy` until the real partial
  lands.

## Source files

- `src/bdboard/app.py` — `api_history` route (~468): normalises `range`, floors
  `page`, clamps `page_size` via `derive.clamp_page_size`, resolves the custom
  window, calls `history_window`, and hands `window` + `page_size`/`page_sizes`
  to the partial; `sse_events` (~281) drives the `refresh` trigger.
- `src/bdboard/derive/history.py` — `history_window` (~162, the paginated closed
  slice), `clamp_page_size` (~40), the bounds primitives `_resolve_bounds`,
  `custom_bounds`, `_closed_in_window`, and the `HISTORY_RANGES` /
  `DEFAULT_HISTORY_RANGE` / `HISTORY_PAGE_SIZES` / `HISTORY_PAGE_SIZE` constants.
- `src/bdboard/store.py` — `snapshot_history` (~117), the active+history-closed
  long-window snapshot source of truth.
- `src/bdboard/templates/history.html` — the page shell + `#history-region` swap
  host (`hx-trigger="load, refresh from:body"`).
- `src/bdboard/templates/partials/history.html` — the `.history-list-section`:
  count badge, `.history-list` of `.bead-card.history-card` cards (with the
  `hx-get="/api/bead/{id}"` modal hook), the `.history-pager` (Newer/Older
  buttons, `.history-page-indicator`, `.history-page-size` selector), and the
  empty/out-of-range copy.
- `src/bdboard/templates/partials/history_skeleton.html` — the load placeholder
  (`.history-list-skeleton` rows).
- `src/bdboard/static/styles.css` — `.history-list`, `.history-card`,
  `.history-closed-when`, `.history-close-reason`, `.history-pager`,
  `.history-page-indicator`, `.history-page-size*`, `.history-empty`.
- `tests/test_derive_history.py` — `history_window` coverage
  (`test_history_window_pagination`, `..._out_of_range_page_is_empty`,
  `..._sorted_newest_closed_first`, `..._excludes_closed_without_closed_at`,
  `..._clamps_bad_page_and_size`, `..._custom_range_filters_both_bounds`) and
  the `clamp_page_size` suite (default-50, allowed-set, out-of-set, garbage).
- `tests/test_api_history.py` — route render/pager coverage
  (`test_pagination_page_two_shows_newer_pager`,
  `test_default_page_size_is_fifty`, and the range-button page/size assertions).