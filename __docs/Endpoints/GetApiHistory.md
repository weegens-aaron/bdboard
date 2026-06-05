# GET /api/history

> [!NOTE]
> The route is registered as `GET /api/history`
> (`@app.get("/api/history", response_class=HTMLResponse)`). It is the data
> half of the [History (/history)](../Views/HistoryView.md) view: a
> long-window retrospective on **closed** beads. The page route `GET /history`
> ([page_history](../Views/HistoryView.md)) renders only a cheap shell whose
> single `#history-region` lazy-loads from **this** endpoint on `load`, on
> every range / Custom / pager / page-size change, and on every SSE-driven
> `refresh from:body`. The handler does **no new `bd` mutation** — it pulls a
> window-bounded snapshot and runs the pure [Derive Layer](../Concepts/DeriveLayer.md)
> history functions over it, then renders `partials/history.html` plus an
> out-of-band masthead stats fragment.

## Overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/history` | None (reads are unauthenticated — bdboard is a single-user localhost dashboard with no cookies/session; CSRF guards only the `POST`/`DELETE` write paths) | Render the History swap region (`partials/history.html`) — a range/custom-date control, an OOB masthead KPI strip, a grouped "Created vs closed" per-day bar chart, and a server-side-paginated newest-closed-first list — derived purely from one window-bounded snapshot of closed beads, symmetric with `GET /api/lanes`. |

## Request

`GET` with no request body. All inputs are optional query-string parameters.
The `#history-region` fires this on `load` and on `refresh from:body`; the
range badges, the Custom date popover, the pager, and the per-page selector
each re-fetch it with different query strings, all targeting `#history-region`
with `hx-swap="innerHTML"`.

### Path/Query Params

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `range` | query | string | No (defaults to `derive.DEFAULT_HISTORY_RANGE` = `"30d"`) | One of `7d` / `30d` / `90d` / `all`; selects the look-back window. Bound as `range: str = derive.DEFAULT_HISTORY_RANGE`. Lower-cased + `.strip()`'d; anything not in `derive.HISTORY_RANGES` degrades to `"30d"`. `all` resolves to an unbounded (`cutoff=None`) full-table view. |
| `page` | query | int | No (defaults to `1`) | 1-based page index into the paginated closed list. Bound as `page: int = 1`, then floored with `page = max(1, page)` so `0`/negatives can't break paging. Out-of-range high pages return an empty `items` with a graceful "back to page 1" affordance. |
| `page_size` | query | int \| null | No (defaults to `None` → `50`) | Closed-list rows per page. Bound as `page_size: int \| None = None`, then clamped by `derive.clamp_page_size` to the allowed set `{25, 50, 100}` (`derive.HISTORY_PAGE_SIZES`); a missing/invalid/tampered value falls back to `derive.HISTORY_PAGE_SIZE` (`50`). `base.html` JS injects the localStorage-persisted size into bare `/api/history` fetches. |
| `from_date` | query | string \| null | No | Custom-window inclusive lower bound, `YYYY-MM-DD` (the `<input type="date">` wire format). When it (or `to_date`) parses, the custom window **supersedes** `range=` for the closed list, every series, and the KPIs (`derive._resolve_bounds`), and the range control flips to the synthetic `custom` preset. Unparseable/absent → no lower bound. |
| `to_date` | query | string \| null | No | Custom-window upper bound, `YYYY-MM-DD`. Resolved to an **exclusive** start-of-next-day ceiling by `derive.custom_bounds`, so `to_date=2026-05-30` includes everything stamped on the 30th. Inverted `from`/`to` pairs are swapped rather than collapsed to empty. |

### Headers

| Header | Required | Notes |
| --- | --- | --- |
| `HX-Request` | No | Sent automatically by HTMX on every `hx-get`. Not inspected by the handler — the route always returns the same fragment whether or not HTMX is driving it (it's a partial, not a full page). |
| `X-CSRF-Token` | No | **Not** required. CSRF is enforced only on the `POST`/`DELETE` mutation paths (see [CSRF Protection](../Concepts/CsrfProtection.md)); this read carries no token. |

### Body

No request body. (Shown for template completeness — the wire request has an
empty body; the only inputs are the query-string parameters above.)

```json
{}
```

### Validation Rules

| Field | Rule | Error |
| --- | --- | --- |
| `range` | Lower-cased + stripped; must be a key of `derive.HISTORY_RANGES` (`7d`/`30d`/`90d`/`all`). Any other/empty value silently degrades to `derive.DEFAULT_HISTORY_RANGE` (`"30d"`). | — (no error path; degrades) |
| `page` | Coerced to int by FastAPI; floored via `page = max(1, page)`. `0`/negatives become `1`; high out-of-range pages return empty `items`. | `422` only if non-int-coercible |
| `page_size` | Clamped by `derive.clamp_page_size` to `{25, 50, 100}`; `None`/invalid → `50`. A tampered query param can never break paging. | — (no error path; clamps) |
| `from_date` / `to_date` | Parsed by `derive._parse_date` strictly as `%Y-%m-%d`; any other shape (or a time component) is treated as "no bound". A valid pair where `from > to` is swapped. | — (no error path; ignored if unparseable) |
| Resolved cutoff agreement | The route resolves `(cutoff, ceiling)` ONCE from a single `now` via `derive.resolve_history_bounds`, pushes `cutoff` down to the `bd` query (`--closed-after`), and the derive layer re-applies the exact same bounds in-memory — no off-by-one drift between fetch filter and slice (bdboard-gp06). | — (invariant, not user-facing) |

### Rate Limit

| Limit | Window | Scope |
| --- | --- | --- |
| None (no rate limiter) | — | Single-user localhost dashboard — no token-bucket / IP throttle. Structural throttles: the shared `BdClient._subprocess_gate` semaphore serializes every `bd` subprocess, the `Store` history cache is **window-aware** (a snapshot fetched with a wider/absent lower bound already covers any narrower sub-window, so only a deeper-reaching request re-queries `bd` — `Store._history_covers`), and the optional `bd status` headline is TTL-cached + in-flight-deduped (`STATUS_TIMEOUT_S = 8.0s`). |

## Response

`Content-Type: text/html` (`response_class=HTMLResponse`). The body is an HTML
**fragment**, not JSON — bdboard is server-rendered HTMX. The route returns the
re-rendered History region that HTMX swaps into `#history-region` via
`hx-swap="innerHTML"`, plus a `hx-swap-oob="true"` masthead stats `<dl>` that
HTMX peels off and swaps into `#history-stats` in the same response.

### Success

`200 OK` — the re-rendered `partials/history.html`. It contains: the range
control (7d/30d/90d/All + a Custom date popover, the active window marked with
`aria-pressed`), the grouped **Created vs closed** per-day bar chart
(fixed-height container so it can't collapse; created bars carry a diagonal
hatch + text `aria-label`s so the series survive greyscale / colour-blind
viewing), the paginated **Closed beads** list (newest-closed-first cards that
reuse `partials/bead_card.html` and open the shared bead modal), the pager +
per-page selector, and the out-of-band masthead stats fragment
(`partials/history_stats.html`).

The handler hands the template these context values (real names, derived from
one snapshot):

```json
{
  "range_key": "30d",
  "active_range": "30d",
  "is_custom": false,
  "from_date": "",
  "to_date": "",
  "ranges": ["7d", "30d", "90d", "all"],
  "page_size": 50,
  "page_sizes": [25, 50, 100],
  "window": {
    "items": [
      {
        "id": "bdboard-mol-q7j.17",
        "title": "FlowDoc maintainer: Endpoint: GET /api/history",
        "status": "closed",
        "priority": 2,
        "assignee": "Aaron Weegens",
        "created_at": "2026-06-05T09:00:00Z",
        "started_at": "2026-06-05T10:00:00Z",
        "closed_at": "2026-06-05T18:00:00Z"
      }
    ],
    "page": 1,
    "page_size": 50,
    "total": 1,
    "has_more": false
  },
  "created_total": 12,
  "combined_series": [
    {"day": "2026-06-04", "created": 3, "closed": 1},
    {"day": "2026-06-05", "created": 9, "closed": 4}
  ],
  "combined_peak": 9,
  "stats": {
    "n": 5,
    "median_lead_h": 26.4,
    "p90_lead_h": 71.2,
    "median_cycle_h": 6.1,
    "p90_cycle_h": 19.8,
    "avg_cycle_h": 8.3
  },
  "avg_per_day": 2.5,
  "bd_summary": {
    "total_issues": 412,
    "closed_issues": 388,
    "in_progress_issues": 3,
    "average_lead_time_hours": 51.7
  }
}
```

> [!NOTE]
> `bd_summary` is **optional sugar** (design §6): it comes from
> `bd status --json` (workspace-global, point-in-time totals — NOT
> range-scoped). On any `bd` hiccup `store.bd.status_summary()` returns
> `None` and the template simply omits the headline cells, leaving the
> range-derived KPIs as the primary surface. Everything else
> (`window`, `combined_series`, `stats`, `created_total`) is a **pure
> derivation** over the one window-bounded snapshot — no per-page or
> per-series extra I/O.

Rendered fragment shape (abbreviated):

```html
<div class="history-region-inner">
  <div class="history-toolbar">
    <div class="history-ranges" role="group" aria-label="History time range">
      <button type="button" class="filter-badge filter-badge-active"
              aria-pressed="true"
              hx-get="/api/history?range=30d&page=1&page_size=50"
              hx-target="#history-region" hx-swap="innerHTML">30d</button>
      <!-- 7d / 90d / All + Custom popover (from_date/to_date inputs) … -->
    </div>
  </div>
  <section class="history-throughput" aria-label="Beads created and closed per day">
    <!-- grouped created (hatched) + closed bars, fixed-height, text aria-labels -->
  </section>
  <section class="history-list-section" aria-label="Closed beads">
    <h2 class="history-section-title">Closed beads <span class="lane-count">1</span></h2>
    <ul class="history-list" role="list"><!-- bead_card.html × page --></ul>
    <nav class="history-pager" aria-label="History pages"><!-- prev/next + per-page select --></nav>
  </section>
  <!-- partials/history_stats.html emitted with hx-swap-oob="true" -> #history-stats -->
</div>
```

When the window is empty the list section renders a friendly empty state
(`Nothing closed in the last 30 days — try a wider range.`), and the chart
section renders `No beads created or closed to chart in 30 days.` instead of the
bar strip — both still `200`.

### Errors

| Status | Code | When |
| --- | --- | --- |
| `422` | FastAPI request-validation error | Only if `page`/`page_size` are sent with a value that fails int coercion (in practice rare; query strings are strings and `page_size=None` is the default). `range`/`from_date`/`to_date` never 422 — bad values degrade silently. |
| `500` | Unhandled exception | This handler does **not** wrap its `bd` calls in a try/except (unlike the memory read). If `store.snapshot_history()` raises (e.g. `bd list` exits non-zero, times out at `LIST_TIMEOUT_S = 15.0s`, or returns non-list JSON), the exception propagates and FastAPI returns a 500. The OPTIONAL `bd status` headline is the exception: `status_summary()` swallows its own failures and returns `None`, so a flaky `bd status` only drops the headline cells — it never 500s the region. |
| _(no `403`)_ | — | Reads are unauthenticated; there is no CSRF gate on this path (contrast the `POST`/`DELETE` siblings). |

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |
| Route handler (resolve window once, derive views, render region + OOB stats) | `src/bdboard/app.py` | `api_history` |
| Query-param binding (`range`, `page`, `page_size`, `from_date`, `to_date`) | `src/bdboard/app.py` | `api_history` signature |
| Resolve `(cutoff, ceiling)` once from a single `now` (shared by fetch + slice) | `src/bdboard/derive/history.py` | `resolve_history_bounds` (→ `_resolve_bounds`) |
| Range preset → cutoff; default-on-invalid | `src/bdboard/derive/history.py` | `_range_to_cutoff`, `HISTORY_RANGES`, `DEFAULT_HISTORY_RANGE` |
| Custom from/to → inclusive lower / exclusive ceiling | `src/bdboard/derive/history.py` | `custom_bounds`, `_parse_date` |
| Page-size clamp to `{25,50,100}` | `src/bdboard/derive/history.py` | `clamp_page_size`, `HISTORY_PAGE_SIZES`, `HISTORY_PAGE_SIZE` |
| Paginated closed-bead window (newest-closed-first, `has_more`) | `src/bdboard/derive/history.py` | `history_window` (→ `_closed_in_window`) |
| Closed-per-day series (throughput) | `src/bdboard/derive/history.py` | `throughput` (partial of `_daily_count_series`) |
| Created-per-day series + range-scoped `created_total` | `src/bdboard/derive/history.py` | `created` (partial of `_daily_count_series`) |
| Combined created+closed series on one gap-free timeline | `src/bdboard/derive/history.py` | `combined`, `_iter_day_span`, `_bucket_by_day` |
| Lead-time / cycle-time KPIs (`n`, median/p90 lead & cycle, avg cycle) | `src/bdboard/derive/history.py` | `lead_time_stats`, `_percentile` |
| Window-aware, count-uncapped history snapshot (active + bounded closed) | `src/bdboard/store.py` | `Store.snapshot_history`, `Store._history_covers`, `Store._load_history` |
| Count-uncapped, window-bounded `bd list --status closed --closed-after` | `src/bdboard/bd.py` | `BdClient.list_closed_history` |
| Optional workspace-global headline (`bd status --json`) | `src/bdboard/bd.py` | `BdClient.status_summary` |
| Gated JSON subprocess runner + timeouts | `src/bdboard/bd.py` | `BdClient._run_json`, `BdClient._subprocess_gate`, `LIST_TIMEOUT_S`, `STATUS_TIMEOUT_S` |
| Region partial (range control, chart, paginated list, pager, OOB stats) | `src/bdboard/templates/partials/history.html` | (toolbar + `history-throughput` + `history-list-section` + pager) |
| OOB masthead KPI strip | `src/bdboard/templates/partials/history_stats.html` | (`hx-swap-oob` `<dl>` → `#history-stats`) |
| Instant skeleton before the first swap | `src/bdboard/templates/partials/history_skeleton.html` | (perceived-perf placeholder) |
| Reused closed-bead card | `src/bdboard/templates/partials/bead_card.html` | (card loop, `meta="history"`) |
| Page shell + `#history-region` lazy-load wiring | `src/bdboard/templates/history.html` | (`hx-get="/api/history"`, `load, refresh from:body`) |
| Persisted page-size injection into bare fetches | `src/bdboard/templates/base.html` | (`htmx:configRequest` page_size shim) |
| Endpoint regression coverage | `tests/test_api_history.py` | `test_bad_range_degrades_to_default`, `test_default_page_size_is_fifty`, `test_invalid_page_size_degrades_to_fifty`, `test_window_change_changes_returned_set`, `test_custom_range_supersedes_preset_filtering`, `test_narrow_range_pushes_lower_bound_to_fetch`, `test_all_range_keeps_fetch_unbounded`, … |

```mermaid
sequenceDiagram
    participant Browser as Browser (#history-region)
    participant Route as api_history (GET /api/history)
    participant Derive as derive.history (pure)
    participant Store as Store (window-aware cache)
    participant BD as BdClient (bd subprocess)
    Browser->>Route: GET /api/history?range&page&page_size&from_date&to_date<br/>(load · range/Custom/pager click · refresh from:body)
    Route->>Route: now = datetime.now(UTC); clamp page, page_size
    Route->>Derive: resolve_history_bounds(range, from, to, now) -> (cutoff, ceiling)
    Route->>Store: snapshot_history(closed_after=cutoff)
    alt cache covers cutoff (_history_covers)
        Store-->>Route: cached active + closed beads (superset OK)
    else deeper/uncovered
        Store->>BD: list_closed_history(closed_after=cutoff) [gated, --limit 0]
        BD-->>Store: closed beads JSON
        Store-->>Route: active + closed beads
    end
    Route->>Derive: history_window / throughput / created / combined / lead_time_stats<br/>(same bounds re-applied in-memory)
    Derive-->>Route: window, series, stats
    Route->>BD: status_summary() (optional headline)
    alt bd status ok
        BD-->>Route: summary dict
    else bd hiccup
        BD-->>Route: None (headline omitted)
    end
    Route->>Route: render partials/history.html (+ OOB history_stats.html)
    Route-->>Browser: 200 region fragment -> swap #history-region<br/>+ OOB swap #history-stats
```

## Example

Default 30-day window, first page (50 rows) — exactly what the
`#history-region` fetches on `load`:

```bash
curl -i "http://127.0.0.1:8000/api/history"
```

A successful call returns `200` with the re-rendered region fragment; HTMX swaps
it into `#history-region` and peels the OOB stats `<dl>` into `#history-stats`.

A 7-day window, second page, 25 rows per page:

```bash
curl -i "http://127.0.0.1:8000/api/history?range=7d&page=2&page_size=25"
```

The unbounded `all` view (genuine full-table read, `--closed-after` omitted):

```bash
curl -i "http://127.0.0.1:8000/api/history?range=all"
```

A custom date range — supersedes `range=`, marks the synthetic `custom` preset
active, and (because `to_date` resolves to an exclusive next-day ceiling)
includes everything closed on the 30th:

```bash
curl -i "http://127.0.0.1:8000/api/history?from_date=2026-05-01&to_date=2026-05-30"
```

A bad `range=` degrades to the 30-day default rather than erroring (the range
control comes back with `30d` marked `aria-pressed="true"`):

```bash
curl -i "http://127.0.0.1:8000/api/history?range=bogus"
# → 200  …<button … aria-pressed="true" hx-get="/api/history?range=30d&page=1&page_size=50">30d</button>…
```

## Related

- [Endpoints index](index.md) — every route bdboard exposes.
- [History (/history)](../Views/HistoryView.md) — the page surface whose
  `#history-region` lazy-loads, paginates, range-filters, and SSE-refreshes from
  **this** endpoint; it lists this route under its API Dependencies.
- [GET /api/bead/{id}](GetApiBead.md) — the shared bead detail modal opened when
  a closed-bead card in this region's list is clicked.
- [GET /api/lanes](GetApiLanes.md) — the board's symmetric region endpoint; both
  return a `partials/*` HTMX fragment derived from a `Store` snapshot rather than
  JSON.
- [GET /api/events](GetApiEvents.md) — the SSE stream whose `beads_changed` event drives
  the `refresh from:body` re-fetch of this region across tabs (see the Endpoints
  index until its own doc lands).
- [Derive Layer](../Concepts/DeriveLayer.md) — the pure `derive.history`
  functions (`history_window`, `throughput`, `created`, `combined`,
  `lead_time_stats`, `resolve_history_bounds`) that shape every view here from
  one snapshot.
- [Store Snapshot & Change Detection](../Concepts/StoreSnapshotChangeDetection.md)
  — the window-aware history cache (`snapshot_history` / `_history_covers`) that
  serves a wider superset rather than re-querying `bd` for a sub-window.
- [Subprocess Serialization & Caching](../Concepts/SubprocessSerializationAndCaching.md)
  — the semaphore + TTL cache + in-flight dedup behind `list_closed_history` and
  `status_summary`.
- [SSE Event Bus](../Concepts/SseEventBus.md) — the `beads_changed` broadcast
  that keeps this region live across tabs after a write elsewhere.
- [bd CLI as Source of Truth](../Concepts/BdCliSourceOfTruth.md) — why this path
  shells `bd list`/`bd status` instead of reading `.beads/` directly.
- [Back to docs index](../index.md)
