# Stats summary

The KPI strip of the **History** page. See also
[history-chart.md](./history-chart.md) (the created-vs-closed chart rendered by
the *same* `/api/history` response — this strip and the chart share one
round-trip), [history-list.md](./history-list.md) (the paginated closed list
below the chart), [board-counts.md](./board-counts.md) (the board's masthead
counts strip this one is deliberately symmetric with), [store-cache.md](./store-cache.md)
(the cached snapshot the range-scoped stats derive from), and
[sse-live-refresh.md](./sse-live-refresh.md) (the pipeline that re-fetches the
region — and therefore re-swaps this strip — on bead changes).

## What it shows

A single horizontal **stat strip** (`<dl class="counts history-stats">`) that
lives in the **masthead header** of the History page, mirroring the board's
`.masthead-counts` chrome so the two surfaces look and behave the same. It is a
*single editorial row* combining **two different data sources** into one
typographically consistent line of `Label / value` cells:

1. **bd workspace totals** (point-in-time, **NOT** range-scoped, optional sugar):
   - **Total** — every bead in the workspace (`bd_summary.total_issues`).
   - **Closed** — every bead ever closed in the workspace
     (`bd_summary.closed_issues`).
   These two cells only render when bd's status summary is available; on any bd
   hiccup they are silently omitted (see Edge cases).

2. **Range-derived KPIs** (these *do* react to the active range control):
   - **Avg lead** — mean **claim→close** cycle time (started_at → closed_at)
     over the active range (`stats.avg_cycle_h`). Note the label says "lead" but
     the metric is actually *cycle* time (active work time), deliberately distinct
     from bd's workspace-global created→close backlog-age lead time.
   - **Closed (range)** — beads closed *within* the active range (`stats.n`).
   - **Median lead** — median **created→close** lead time (filed to closed) over
     the active range (`stats.median_lead_h`).
   - **Throughput** — average beads closed per day over the active range
     (`avg_per_day`).

Each cell carries a small, keyboard-accessible **info-icon popover** (the
`stat_info` Jinja macro) that holds the fuller explanation — the verbose "via
bd", "claim→close, {range}", and range-scope qualifiers that used to crowd the
header inline. The popover is CSS-only: the `<button>` reveals a `role="tooltip"`
span on hover/focus/click, and `aria-describedby` ties the tooltip to the button
so screen readers announce the explanation regardless of visual state.

Durations are rendered through the `humanize_hours` filter (`24m`, `2.5h`,
`1.5d`, or `—` for `None`). Cells whose value is zero / `None` pick up the
`counts-cell-zero` muting class so empty stats recede visually. The whole strip
is `role="status"` with `aria-live="polite"` and `aria-label="History
statistics"` so a range change is announced to assistive tech.

## Where the data comes from

- **Route:** `GET /api/history` → `api_history` in `src/bdboard/app.py` (~468).
  A pure derivation over the snapshot — **no new bd call** for the range-scoped
  KPIs. It computes `stats` and `avg_per_day`, fetches the optional `bd_summary`,
  and renders `partials/history.html`, which `{% include %}`s
  `partials/history_stats.html`.
- **Delivery mechanism (key quirk):** the stats strip is **not** rendered inline
  in `#history-region`. Instead `partials/history_stats.html` is emitted as an
  **`hx-swap-oob="true"`** `<dl>` (`id="history-stats"`). HTMX peels it off the
  `/api/history` response and swaps it out-of-band into the masthead host
  `#history-stats`, while the rest of the same response fills `#history-region`
  (the chart + list). One fetch, two surfaces — no second endpoint and no client
  JS, keeping the range-scoped header values live on every range click and SSE
  refresh (DRY).
- **Range-derived KPIs (derive layer):** all pure functions in
  `src/bdboard/derive/history.py`, sharing one window resolved by
  `_resolve_bounds` (custom from/to supersedes the `range` preset):
  - `lead_time_stats(beads, range_key, from_date, to_date)` →
    `{n, median_lead_h, p90_lead_h, median_cycle_h, p90_cycle_h, avg_cycle_h}`.
    `n` counts closed beads in the window; lead times are created→closed,
    cycle times are started→closed. Negative/zero durations (clock skew) are
    dropped and beads lacking a parseable `started_at` are excluded from the
    cycle metrics.
  - `avg_per_day` is computed in the **route** as
    `round(stats["n"] / len(series), 1) if series else 0`, where `series` is the
    `throughput(...)` closed-per-day series (so the denominator is the number of
    days in the closed-activity span — see Edge cases).
- **bd totals (optional):** `await store.bd.status_summary()` →
  `Bd.status_summary` in `src/bdboard/bd.py` (~422), which shells out to
  `bd status --json` and returns the `summary` sub-object
  (`total_issues`, `closed_issues`, `average_lead_time_hours`, …) or `None` on
  any bd failure / malformed payload. Cached + in-flight-deduped via `_cached`
  under a single workspace-global key, and dropped by `invalidate_caches` on a
  watcher fire so post-mutation totals refresh.
- **Source of truth (for range KPIs):** `await store.snapshot_history()` in
  `src/bdboard/store.py` (~117) — the active + history-closed (count-capped)
  snapshot, the same long-window source the chart and list use, so the strip's
  closed/lead numbers cover work older than the board's short closed window
  (bdboard-p8v). Underneath it is the in-memory Store cache (lazily loaded from
  the bd CLI, refreshed by the file watcher).
- **Templates / filter:**
  - `templates/partials/history_stats.html` — the OOB `<dl>` and the `stat_info`
    popover macro.
  - `templates/history.html` — renders the masthead host
    `<div class="masthead-counts" id="history-stats" aria-busy="true">` so the
    strip exists on first paint before the OOB swap lands.
  - `humanize_hours` filter registered in `app.py` (~91) from
    `derive/timeutil.py` (~79).

## What changes its state

The strip is re-rendered (via the OOB swap) every time `/api/history` is
re-fetched, which is driven by `#history-region`'s HTMX wiring on
`history.html`:

1. **`load`** — first paint fetches the default **30d** window; the masthead host
   shows its `aria-busy` skeleton until the OOB `<dl>` swaps in.
2. **Range filter (`7d / 30d / 90d / All`)** — each filter-badge button
   `hx-get="/api/history?range=<r>&..."` re-derives `stats` and `avg_per_day`
   against the new window, so **Avg lead / Closed (range) / Median lead /
   Throughput** all update together. The bd **Total / Closed** cells do *not*
   change — they are workspace-global. `range_human` (from the `range_labels`
   map: `7d→"7 days"`, etc.) is interpolated into every popover so the tooltips
   name the active window.
3. **Custom date range** — the Custom popover submits `from_date`/`to_date`
   (`YYYY-MM-DD`); a valid custom selection **supersedes** the `range=` preset
   for the range-derived KPIs (resolved once by `derive._resolve_bounds`).
4. **`refresh from:body`** — the SSE live-update hook. A `.beads/` change fires
   the file watcher → `beads_changed` event (`GET /api/events`) → the
   `EventSource` in `base.html` dispatches a synthetic `refresh` on `<body>` and
   `#history-region` re-fetches. This SSE-driven refresh re-fetches the
   **default** 30d window (no query params) — the same "snap back to fresh data"
   behaviour the board's regions have; the user re-clicks a range to re-scope.

The strip is **read-only** — it reflects state and never mutates beads. Range and
pagination state are URL-borne (carried in the buttons' query strings), not
element-borne, keeping the wiring DRY.

## Edge cases & notes

- **Range degradation to default.** A missing or garbage `?range=` value is
  normalised in the route: `range_key` is lowercased/stripped and, if it is not
  in `derive.HISTORY_RANGES` (`7d/30d/90d/all`), it falls back to
  `derive.DEFAULT_HISTORY_RANGE` (`30d`). The same guard lives inside
  `_range_to_cutoff`, so both the template's active-state cue and the derive
  calls always agree on a valid window rather than erroring. A bad `?range=`
  therefore silently renders the 30d window.
- **bd totals are optional sugar.** `status_summary()` returns `None` on any bd
  hiccup (subprocess failure, timeout, malformed JSON), and the template guards
  the bd cells with `{% if bd_summary %}`. When bd is unavailable the **Total**
  and **Closed (all time)** cells simply vanish, leaving the range-derived KPIs
  as the primary surface — the masthead degrades gracefully instead of 500-ing.
  These bd numbers are point-in-time and **never** react to the range control.
- **Throughput denominator is the activity span, not calendar days.**
  `avg_per_day = stats["n"] / len(series)` divides by `len(series)` — the number
  of entries in the `throughput` series, which is the gap-filled span from the
  first to the last day that had a *close* in the window (not the total number
  of calendar days in the selected range). So a 30d range with closes only in a
  5-day span averages over ~5 days, not 30. When nothing closed (`series == []`)
  it short-circuits to `0` rather than dividing by zero.
- **None / zero metrics.** `median_lead_h`, `avg_cycle_h`, etc. are `None` when
  there is no qualifying data; `humanize_hours(None)` renders an em-dash `—`, and
  the cell picks up `counts-cell-zero` muting. `stats.n == 0` (nothing closed in
  range) likewise mutes the **Closed (range)** cell.
- **Lead vs cycle naming.** "Avg lead" is intentionally the *cycle* time
  (started→closed, active work time), while "Median lead" is the *lead* time
  (created→closed, filed-to-done). The two answer different questions; the
  popovers spell out the distinction. Beads with no parseable `started_at` are
  excluded from the cycle metric; clock-skew negatives are dropped.
- **`combined_peak` is computed here but consumed by the chart, not this strip.**
  The route also computes `combined_peak = max((max(d["created"], d["closed"])
  for d in combined_series), default=0)` in the *same* `/api/history` handler.
  Despite living next to the stats derivation, `combined_peak` is **not**
  displayed in the KPI strip — it is the shared y-axis scale for the
  created-vs-closed bars (see [history-chart.md](./history-chart.md)). The
  `default=0` on the generator guards the empty-window case (no created/closed
  days) so the `max(...)` over an empty `combined_series` yields `0` instead of
  raising `ValueError`; downstream the chart's `count / combined_peak` height
  expression short-circuits to `0` when the peak is `0`. It is documented here
  because the bead asked for it, but the canonical home is the chart doc.
- **Long-window source, not the board window.** Range KPIs derive from
  `store.snapshot_history()` (count-capped history-closed), so `90d`/`All` ranges
  surface closed work older than the board's short closed window (bdboard-p8v).
  The cap is a count cap, not a date cap.
- **First-paint host vs OOB swap.** The masthead `#history-stats` host is
  rendered by `history.html` with `aria-busy="true"` so the strip occupies space
  before data arrives; the OOB `<dl>` (same id) then replaces it. Because the OOB
  swap targets the id, there is no layout shift.

## Source files

- `src/bdboard/app.py` — `api_history` route (~468): computes `stats` (via
  `derive.lead_time_stats`) and `avg_per_day`, fetches optional `bd_summary` (via
  `store.bd.status_summary`), also computes `combined_peak`, and hands the
  context to `partials/history.html`; `sse_events` (~281) drives the `refresh`
  trigger; `humanize_hours` filter registration (~91).
- `src/bdboard/derive/history.py` — `lead_time_stats` (the range-scoped
  KPI bundle, incl. `n`, `median_lead_h`, `avg_cycle_h`), `throughput` (the
  closed-per-day series whose length is the `avg_per_day` denominator), the
  shared window primitives `_resolve_bounds` / `_range_to_cutoff` /
  `custom_bounds` / `_closed_in_window`, and `HISTORY_RANGES` /
  `DEFAULT_HISTORY_RANGE` (range presets + degradation default).
- `src/bdboard/derive/timeutil.py` — `humanize_hours` (~79), the duration
  formatter used by the lead/cycle cells.
- `src/bdboard/bd.py` — `status_summary` (~422), the optional `bd status --json`
  workspace totals (cached, `None` on failure).
- `src/bdboard/store.py` — `snapshot_history` (~117), the active+history-closed
  long-window snapshot source of truth for the range KPIs.
- `src/bdboard/templates/partials/history_stats.html` — the OOB
  `<dl class="counts history-stats" id="history-stats" hx-swap-oob="true">`, the
  six KPI cells, and the accessible `stat_info` info-icon/popover macro.
- `src/bdboard/templates/partials/history.html` — `{% include
  "partials/history_stats.html" %}` (emits the OOB fragment) plus the
  `range_labels` / `range_human` map the popovers interpolate.
- `src/bdboard/templates/history.html` — the masthead host
  `#history-stats` (`aria-busy` skeleton) the OOB fragment swaps into.
- `src/bdboard/static/styles.css` — `.history-stats` (~2215), `.counts-cell` /
  `.counts-cell-zero` / `.counts-label` / `.counts-value` shared with the board
  counts strip, and `.stat-info` / `.stat-info-pop` popover styling (~2289).
