# Created-vs-closed chart

The lead feature of the **History** page. See also
[history-stats.md](./history-stats.md) (the KPI strip rendered out-of-band by
the *same* `/api/history` response), [history-list.md](./history-list.md) (the
paginated closed list below the chart), [board-time-filter.md](./board-time-filter.md)
(the board's short-window lane filter this chart's range control complements),
[store-cache.md](./store-cache.md) (the cached snapshot the series derive from),
and [sse-live-refresh.md](./sse-live-refresh.md) (the pipeline that re-fetches
the region on bead changes).

## What it shows

A single fixed-height **grouped bar strip** titled **"Created vs closed"** that
plots two daily time series over the selected window:

- **Created** (violet, diagonal-hatched) — beads *filed* per calendar day,
  regardless of their current status (an open bead filed in-window still
  counts).
- **Closed** (blue, solid) — beads *closed* per calendar day.

The x-axis is a **continuous, gap-free timeline**: every calendar day from the
first through the last day that had *either* a creation or a close in the
window gets a cell, even days with zero activity (they render as empty
baseline). Each day cell holds a **grouped pair** of mini columns — created on
the left, closed on the right — and both bars **grow UP from the shared bottom
baseline**, which sits directly adjacent to the date labels (`MM-DD`, the day
key sliced `[5:]`). A per-day count label floats above each bar (blank when the
count is `0`).

Both series are scaled against **one shared peak** (`combined_peak`, the single
largest created-or-closed value on any day in the window) so the two metrics
stay directly comparable day to day — you can read net flow / backlog burn at a
glance. A header **legend** names each series and shows its range-scoped total
(Created `{{ created_total }}`, Closed `{{ stats.n }}`).

It is **not colour-only** (WCAG / design §5 a11y): the three distinguishing
cues are position (grouped pair), colour (violet vs blue), and pattern (the
created series carries a diagonal hatch that survives greyscale / colour-blind
viewing). The whole chart is `role="img"` with a descriptive `aria-label`
conveying the date span, both totals, and the peak; each day cell also carries
its own per-day `aria-label` ("N created, M closed on YYYY-MM-DD").

Note: this is a **pure CSS/flexbox bar chart** (percentage-height `<span>`s in
a `<ul>`), *not* a Chart.js canvas — there is no client-side charting library
in the render path.

## Where the data comes from

- **Route:** `GET /api/history` → `api_history` in `src/bdboard/app.py` (~468).
  A pure derivation over the snapshot — **no new bd call** per request. It
  renders `partials/history.html` with `combined_series` and `combined_peak`
  (plus the range/pagination context the rest of the region uses).
- **Derive layer:** `derive.combined(beads, range_key, from_date, to_date)` in
  `src/bdboard/derive/history.py`. It is a **pure** function that:
  1. resolves the window bounds once via `_resolve_bounds` (custom from/to
     supersedes the `range` preset);
  2. buckets closed beads by `closed_at` day (`_closed_in_window` +
     `_bucket_by_day`) and created beads by `created_at` day
     (`_created_in_window` + `_bucket_by_day`);
  3. takes the **union** of populated days and walks every calendar day from
     first to last (`_iter_day_span`), emitting
     `[{"day": "YYYY-MM-DD", "created": int, "closed": int}, ...]` with `0`
     fill for missing days so the grouped bars stay aligned.
  The legend totals come from siblings: `created_total` is summed from
  `derive.created(...)` and the closed total is `stats.n` from
  `derive.lead_time_stats(...)`. `combined_peak` is computed in the route as
  `max(max(d["created"], d["closed"]) for d in combined_series)`.
- **Source of truth:** `await store.snapshot_history()` in
  `src/bdboard/store.py` (~117), which returns **active + history-closed**
  (uncapped) issues. The History page deliberately uses the long-window
  history-closed cache — **not** the board's short date-windowed closed set —
  so ranges wider than the board's closed window don't silently miss older work
  (bdboard-p8v). Underneath it's still the in-memory Store cache (lazily loaded
  from the bd CLI, refreshed by the file watcher).
- **Templates:**
  - `templates/history.html` — the full page shell; hosts the `#history-region`
    swap target with an instant skeleton.
  - `templates/partials/history.html` — renders the `.history-throughput`
    section: the legend, the `.throughput-chart-combined` strip, and each day's
    `.throughput-pair` of `.throughput-col` mini columns.
  - `templates/partials/history_skeleton.html` — the load placeholder.

## What changes its state

The chart lives inside `#history-region`, the single HTMX swap target on
`history.html`:

```html
<section id="history-region" hx-get="/api/history"
         hx-trigger="load, refresh from:body" hx-swap="innerHTML">
  {% include "partials/history_skeleton.html" %}
</section>
```

Triggers and controls that re-render it:

1. **`load`** — fires once on first paint, fetching the default **30d** window.
   The page shell returns instantly with the skeleton; HTMX then swaps in the
   real region.
2. **Range filter** — the `7d / 30d / 90d / All` filter-badge buttons each
   `hx-get="/api/history?range=<r>&..."` targeting `#history-region`. Changing
   the range re-derives *all* series against the new window, so the chart's day
   span, bars, peak, and legend totals all update together. The active badge is
   marked with `aria-pressed`.
3. **Custom date range** — the Custom popover submits `from_date`/`to_date`
   (`YYYY-MM-DD`); a valid custom selection **supersedes** the `range=` preset
   for the chart and everything else (resolved in one place by
   `derive._resolve_bounds`), and the synthetic `custom` key owns the active
   cue.
4. **`refresh from:body`** — the SSE live-update hook. When the file watcher
   detects a `.beads/` change, the server broadcasts a `beads_changed` event
   (`GET /api/events`); the `EventSource` in `base.html` dispatches a synthetic
   `refresh` on `<body>` and the region re-fetches. Note this SSE-driven
   refresh re-fetches the **default** window (no query params) — the same
   "snap back to fresh data" behaviour the board's lanes region has; range/page
   selection lives in the URLs the buttons fire, not in the element.

The chart is **read-only** — it reflects state, it never mutates beads. (Range
and pagination state are URL-borne, not element-borne, keeping the wiring DRY.)

## Edge cases & notes

- **Axis orientation bug history (bdboard-oey — "created-vs-closed upside
  down").** When the two formerly-separate created/closed strips were merged
  into one grouped view (bdboard-ijd), the bars rendered **upside down**: they
  hung downward from the top of the plot area while the date labels sat at the
  bottom, so a larger value extended *further down* instead of up from the
  baseline. Root cause: the base `.throughput-bar` carried `align-self:
  stretch`, which was harmless in the old column-direction strips (cross-axis
  horizontal) but broke once the two series sat in a **row-direction**
  `.throughput-pair`. The fix (this is the current layout) gives each series
  its own `.throughput-col` — a `flex-direction: column; justify-content:
  flex-end` mini column that anchors its bar to the shared bottom baseline so
  bars grow **UP** toward the labels. The combine also dropped the per-day
  count labels; they were restored via the `.throughput-count` span (blank
  string when `0`, matching the pre-combine behaviour). Regression-guarded by
  `test_combined_chart_shows_per_day_counts_and_baseline_columns` in
  `tests/test_api_history.py`.
- **Peak scaling.** Bar heights are `count / combined_peak * 100` percent.
  `combined_peak` is the single max across *both* series so created and closed
  bars share one scale and stay comparable. When `combined_peak == 0` (nothing
  in the window) the height expression short-circuits to `0` rather than
  dividing by zero — but in practice an all-zero window produces an empty
  `combined_series`, so the empty-state copy renders instead (see next).
- **Empty series.** If nothing was created *or* closed in the window,
  `derive.combined` returns `[]`; the template falls back to a muted
  empty-state line — *"No beads created or closed to chart in
  &lt;window&gt;."* — with the human-readable window label (preset phrase, or
  the custom from/to dates, including open-ended single-bound phrasing).
- **Gap-free continuous timeline.** Days with zero activity inside the span are
  filled (`count`/`created`/`closed` = `0`) by `_iter_day_span` so the strip
  reads as a continuous axis rather than collapsing to only active days. Days
  *outside* the first-to-last span are not shown.
- **Created counts open beads too.** The created series filters by
  `created_at` and is **status-agnostic** — a still-open bead filed in the
  window counts — which is the deliberate complement to the closed series:
  *created* answers "how much did we file?", *closed* answers "how much did we
  finish?".
- **Unparseable timestamps are dropped.** Beads with no parseable
  `created_at` / `closed_at` cannot be placed on a timeline and are excluded
  from their respective series (`_created_in_window` / `_closed_in_window`).
- **Long-window source, not the board window.** The chart derives from
  `store.snapshot_history()` (uncapped history-closed), so the `90d`/`All`
  ranges surface closed work older than the board's short closed window
  (bdboard-p8v). The cap is a count cap, not a date cap.
- **SSE refresh snaps to default.** A live SSE refresh re-fetches the default
  30d window without the user's selected range — intentional parity with the
  board lanes; the user re-clicks a range to re-scope.

## Source files

- `src/bdboard/app.py` — `api_history` route (~468): computes `combined_series`
  and `combined_peak`, resolves range vs custom window, hands context to the
  partial; `sse_events` (~281) drives the `refresh` trigger.
- `src/bdboard/derive/history.py` — `combined` (the created+closed merged
  series), plus the shared primitives `_resolve_bounds`, `_closed_in_window`,
  `_created_in_window`, `_bucket_by_day`, `_iter_day_span`, `_fill_daily_series`;
  `created` and `throughput` (sibling standalone series); `HISTORY_RANGES` /
  `DEFAULT_HISTORY_RANGE` (the range presets).
- `src/bdboard/store.py` — `snapshot_history` (~117), the active+history-closed
  long-window snapshot source of truth (`_load_history`).
- `src/bdboard/templates/history.html` — the page shell + `#history-region`
  swap host (`hx-trigger="load, refresh from:body"`).
- `src/bdboard/templates/partials/history.html` — the `.history-throughput`
  chart markup: legend, `role="img"` strip, per-day `.throughput-pair` /
  `.throughput-col` / `.throughput-count` / `.throughput-bar-created` /
  `.throughput-bar-closed`, and the empty-state copy.
- `src/bdboard/templates/partials/history_skeleton.html` — the load
  placeholder.
- `src/bdboard/static/styles.css` — `.throughput-chart`, `.throughput-bars`,
  `.throughput-bar-cell`, `.throughput-pair`, `.throughput-col`,
  `.throughput-bar`, `.throughput-bar-created` (violet + hatch),
  `.throughput-bar-closed`, `.throughput-count`, `.history-legend*`
  (~2314–2460); the `flex-end` baseline anchoring that fixed bdboard-oey.
- `tests/test_api_history.py` —
  `test_combined_chart_shows_per_day_counts_and_baseline_columns` (per-day
  counts + baseline columns, the bdboard-oey regression guard) and the broader
  `/api/history` render/range/pagination coverage.
- `notes/bugs/bdboard-oey/created-vs-closed-upside-down.png` — the original
  upside-down regression screenshot.
