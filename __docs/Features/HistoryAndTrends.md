# History & Trends

## What It Does

Gives you a long-window retrospective surface at `/history`: a range/custom-date
control, a combined **created-vs-closed per-day** bar chart, a server-paginated
list of **closed** beads (newest-closed first), and a range-scoped KPI strip
(throughput, lead/cycle time) in the masthead — all derived from one snapshot
and repainted live whenever the workspace changes.

## Why It Exists

The board (`/`) is a *recent-activity* surface: its lane filter caps at
12h/1d/3d and its Closed lane is fetched within a small date window, so anything
that closed a week ago is invisible there (`Bd.list_closed`, bdboard-p8v). That
deliberate short-window scope leaves three retrospective questions unanswered:
*what got finished over the last month/quarter?*, *are we closing faster than we
file (net flow / backlog burn)?*, and *how long do beads actually take from
filing to done, and from claim to done?*. History & Trends answers all three
without bloating the board's hot path. It is the explicit complement to the
board: **count-uncapped but window-bounded** (`Bd.list_closed_history`,
bdboard-a194 / bdboard-gp06), so older closures stay reachable via the filters
while memory pressure is controlled by the resolved lower bound rather than a
static fetch cap. It reuses the same `bd`-as-source-of-truth, snapshot-cache,
pure-derive, HTMX-partial, and SSE live-refresh machinery as the rest of the app
so the whole retrospective is one read-only swap region with zero new
infrastructure.

## How It Works

### User Perspective

- Open **/history** (linked from the masthead nav on every page). The page
  paints a range-bar + chart + six-row shimmer skeleton instantly, then hydrates
  the region via an HTMX `load` fetch to `GET /api/history` — a "Created vs
  closed" grouped-bar chart, then `Closed beads <total>` over a paginated list
  of cards, then a Prev/Next pager and per-page selector. The masthead shows a
  range-scoped KPI strip that arrives **out-of-band** in the same response.
- **Pick a preset range** — click `7d` / `30d` / `90d` / `All` (default `30d`);
  the badge fires `hx-get="/api/history?range=<r>&page=1&page_size=<size>"`,
  re-swapping the whole region and (OOB) the masthead KPIs. The active badge
  reads `aria-pressed="true"`.
- **Pick a custom date range** — click `Custom` to open the popover, fill From
  and/or To, click **Apply**; the `<form>` submits `from_date`/`to_date`, which
  supersede `range=` for the list, chart, and KPIs. **Clear** returns to the
  active preset; selecting any preset also dismisses the popover.
- **Page through closed beads** — `‹ Newer` / `Older ›` re-fetch the adjacent
  page within the current window (preserving `page_size` and any custom dates).
- **Change rows per page** — the per-page `<select>` (25/50/100) resets to page
  1 and persists the choice to `localStorage` (`bdboard-history-page-size`) so
  it survives reloads/navigation.
- **Open a closed bead** — click a card; `hx-get="/api/bead/{id}"` opens the
  shared bead modal (the same one the board uses).
- All of it stays live: the watcher turns any `.beads/` change into an SSE
  `beads_changed → refresh from:body` re-fetch for the *same* window
  (`base.html` re-injects the active window into the bare fetch), so a bead
  closing while you watch appears without a manual reload.

### System Perspective

The page route `page_history` (`src/bdboard/app.py`) renders a cheap shell and
never blocks on a `bd` subprocess — all `bd`-backed reads and every derivation
happen on `GET /api/history`. `api_history` resolves the active window **once**
from a single `now` via `derive.resolve_history_bounds` (custom `from`/`to`
supersede the preset `range`), then pushes that lower `cutoff` *down* to the bd
query through `store.snapshot_history(closed_after=cutoff)` — a narrow range
fetches only the beads closed inside it instead of slurping the whole closed
table (bdboard-gp06). On the cache-warm path the window-aware history cache
(`Store._history_covers`) serves a covering super-window from memory with **no**
bd call at all. From that one in-memory snapshot the handler derives every
view — the paginated closed list (`history_window`), the combined created+closed
per-day series (`combined`) plus its `created`/`throughput` arms, and the
lead/cycle-time KPIs (`lead_time_stats`) — purely, with zero extra I/O per page.
It also fetches the optional workspace-global headline
`store.bd.status_summary()` (`None` on any hiccup → cells simply omitted). The
whole response is a single **HTML fragment**: `partials/history.html` swaps into
`#history-region`, and the embedded `partials/history_stats.html` `<dl>` rides
along with `hx-swap-oob="true"` so HTMX peels it off into the masthead's
`#history-stats` host — one fetch, two surfaces, kept in sync on every range
click and SSE refresh.

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant H as HTMX (history.html / base.html)
    participant PR as page_history (app.py)
    participant R as api_history (app.py)
    participant D as derive.history
    participant S as Store (store.py)
    participant BD as BdClient (bd.py)
    participant Proc as bd subprocess
    participant T as history.html + history_stats.html

    U->>PR: GET /history
    PR-->>H: 200 history.html shell + skeletons (never blocks on bd)
    H->>R: GET /api/history (hx-trigger="load"; base.html injects active window + page_size)
    R->>R: range_key clamp; page=max(1,page); size=clamp_page_size(page_size)
    R->>D: resolve_history_bounds(range, from, to, now) -> (cutoff, ceiling)
    R->>S: snapshot_history(closed_after=cutoff)
    alt history cache covers window
        S-->>R: active + cached history (no bd call)
    else cache miss / wider window
        S->>BD: list_closed_history(closed_after=cutoff)
        BD->>Proc: bd list --status closed --sort closed --no-pager --limit 0 [--closed-after <iso>] (gated)
        alt bd read fails
            Proc-->>BD: error
            BD-->>S: raise -> caught, history cache stays empty
            S-->>R: active + [] (degraded)
        else ok
            Proc-->>BD: [closed beads JSON]
            BD-->>S: closed list -> cache + record cutoff
            S-->>R: active + history
        end
    end
    R->>D: history_window / combined / throughput / created / lead_time_stats (pure)
    R->>S: bd.status_summary() (bd status --json, TTL-cached; None on hiccup)
    S-->>R: summary | None
    R->>T: render partials/history.html (+ OOB partials/history_stats.html)
    T-->>H: 200 fragment (region body + hx-swap-oob stats <dl>)
    H->>U: innerHTML swap #history-region; OOB swap #history-stats

    Note over U,T: Live refresh — watcher detects .beads/ change
    H->>R: SSE beads_changed -> refresh from:body (bare; base.html re-injects window)
    R-->>H: 200 fresh region + OOB stats for the same window
```

## Key Data Shapes

History is query-param in and HTML-fragment out (never JSON on the wire), but
several internal shapes carry the feature. Real field names below.

The **window** slice `derive.history_window` returns (paginated closed list):

```json
{
  "items": [
    { "id": "bdboard-mol-bfs.3", "title": "FlowDoc: History & trends", "status": "closed", "closed_at": "2026-05-30T17:04:00Z", "created_at": "2026-05-28T09:00:00Z", "started_at": "2026-05-29T10:00:00Z", "priority": 2 }
  ],
  "page": 1,
  "page_size": 50,
  "total": 137,
  "has_more": true
}
```

The **combined** per-day series `derive.combined` returns (one gap-free
timeline; both arms zero-filled across the span):

```json
[
  { "day": "2026-05-03", "created": 4, "closed": 2 },
  { "day": "2026-05-04", "created": 0, "closed": 1 }
]
```

The **throughput** / **created** per-day series (each a partial of the same
`_daily_count_series` pipeline — closed-at vs created-at):

```json
[
  { "day": "2026-05-03", "count": 2 },
  { "day": "2026-05-04", "count": 1 }
]
```

The **lead_time_stats** KPI block `derive.lead_time_stats` returns (hour-valued
floats rounded to 1 dp, or `null` when a metric has no data):

```json
{
  "n": 137,
  "median_lead_h": 41.5,
  "p90_lead_h": 188.0,
  "median_cycle_h": 6.2,
  "p90_cycle_h": 33.1,
  "avg_cycle_h": 12.4
}
```

The optional workspace-global headline `store.bd.status_summary()` (the
`summary` sub-object of `bd status --json`; `null` on any bd hiccup):

```json
{
  "total_issues": 412,
  "closed_issues": 318,
  "in_progress_issues": 11,
  "average_lead_time_hours": 53.7
}
```

The full template context `api_history` hands `partials/history.html` (real
keys):

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
  "window": { "items": [], "page": 1, "page_size": 50, "total": 137, "has_more": true },
  "created_total": 142,
  "combined_series": [{ "day": "2026-05-03", "created": 4, "closed": 2 }],
  "combined_peak": 9,
  "stats": { "n": 137, "median_lead_h": 41.5, "p90_lead_h": 188.0, "median_cycle_h": 6.2, "p90_cycle_h": 33.1, "avg_cycle_h": 12.4 },
  "avg_per_day": 4.6,
  "bd_summary": { "total_issues": 412, "closed_issues": 318, "in_progress_issues": 11, "average_lead_time_hours": 53.7 }
}
```

## API Surface

| Method | Path | Purpose | → Endpoint doc |
| --- | --- | --- | --- |
| GET | `/history` | Full-page shell (`history.html`); paints skeletons, then hydrates `#history-region` via an HTMX `load` fetch. Never blocks on `bd`; surfaces a workspace error as `error.html` (`500`). | _(page route; see [History page](../Views/HistoryPage.md))_ |
| GET | `/api/history` | The read-only swap region: resolves the window (`range`/`page`/`page_size`/`from_date`/`to_date`), pushes the lower bound to `bd list --closed-after`, derives the paginated closed list + combined/throughput/created series + lead-time KPIs from one snapshot, and renders `partials/history.html` plus the OOB `partials/history_stats.html`. | [HistoryApi](../Endpoints/HistoryApi.md) |
| GET | `/api/bead/{id}` | Opens the shared bead modal when a closed card is clicked. | [BeadDetailApi](../Endpoints/BeadDetailApi.md) |
| GET | `/api/events` | Long-lived SSE stream; a `beads_changed` event fires `refresh from:body`, re-fetching `#history-region` live (close-as-you-watch). | [SseEvents](../Endpoints/SseEvents.md) |

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |
| Page shell route (renders shell, surfaces workspace-validation error as `500`) | `src/bdboard/app.py` | `page_history` |
| Region API handler (resolve window once, fetch snapshot, derive all views, render region + OOB stats) | `src/bdboard/app.py` | `api_history` |
| Range presets + default + page-size set/default | `src/bdboard/derive/history.py` | `HISTORY_RANGES` / `DEFAULT_HISTORY_RANGE` / `HISTORY_PAGE_SIZES` / `HISTORY_PAGE_SIZE` |
| Page-size coercion to the allowed set (single source of truth) | `src/bdboard/derive/history.py` | `clamp_page_size` |
| Window-bounds resolver (custom `from`/`to` supersede preset `range`) — shared by route + every derive | `src/bdboard/derive/history.py` | `resolve_history_bounds` / `_resolve_bounds` / `custom_bounds` / `_range_to_cutoff` / `_parse_date` |
| Paginated closed-list slice (`{items, page, page_size, total, has_more}`) | `src/bdboard/derive/history.py` | `history_window` / `_closed_in_window` |
| Closed-per-day series (combined chart `closed` arm + `avg_per_day` denom) | `src/bdboard/derive/history.py` | `throughput` / `_daily_count_series` / `_bucket_by_day` / `_fill_daily_series` |
| Created-per-day series (`created_total` + combined chart `created` arm) | `src/bdboard/derive/history.py` | `created` / `_created_in_window` |
| Combined created+closed per-day timeline (one gap-free series) | `src/bdboard/derive/history.py` | `combined` / `_iter_day_span` |
| Lead/cycle-time KPI block (`{n, median_lead_h, p90_lead_h, median_cycle_h, p90_cycle_h, avg_cycle_h}`) | `src/bdboard/derive/history.py` | `lead_time_stats` / `_percentile` |
| Snapshot provider (active + window-bounded closed; window-aware cache) | `src/bdboard/store.py` | `Store.snapshot_history` / `_history_covers` / `_load_history` / `_history_cutoff` |
| Count-uncapped, `--closed-after`-bounded closed fetch | `src/bdboard/bd.py` | `BdClient.list_closed_history` / `LIST_TIMEOUT_S` |
| Optional workspace-global headline (`bd status --json` → `summary`, TTL-cached) | `src/bdboard/bd.py` | `BdClient.status_summary` / `STATUS_TIMEOUT_S` |
| Single-writer serialization for every bd subprocess (dolt is single-writer) | `src/bdboard/bd.py` | `BdClient._subprocess_gate` |
| Region template (toolbar, combined chart, paginated list, pager, page-size select) | `src/bdboard/templates/partials/history.html` | `.history-region-inner` / `.history-ranges` / `.history-throughput` / `.history-pager` |
| OOB masthead KPI strip (global totals + range KPIs, `hx-swap-oob`) | `src/bdboard/templates/partials/history_stats.html` | `dl#history-stats` / `stat_info` macro |
| Page shell + masthead host + `load`/`refresh from:body` triggers + skeleton | `src/bdboard/templates/history.html` | `#history-region` / `#history-stats` |
| Bare-fetch window + page-size re-injection (so SSE/load keep the active window) | `src/bdboard/templates/base.html` | `htmx:configRequest` injectors (`activePresetRange` / `activeCustom` / `storedSize`) |
| Closed-list card markup (`meta="history"`; click opens the shared modal) | `src/bdboard/templates/partials/bead_card.html` | `bead_card` |
| Regression tests | `tests/` | `test_api_history.py`, `test_derive_history.py`, `test_store_history_window.py`, `test_bd_closed_history.py`, `test_bd_status_summary.py`, `test_page_history.py`, `test_created_bar_contrast.py` |

## Configuration

| Key | Default | Effect |
| --- | --- | --- |
| `DEFAULT_HISTORY_RANGE` (`src/bdboard/derive/history.py`) | `"30d"` | The window used when `range` is missing/invalid (a bad `?range=` degrades to this, never errors). |
| `HISTORY_RANGES` (`src/bdboard/derive/history.py`) | `{7d, 30d, 90d, all}` | The valid preset keys → `timedelta` cutoffs; `all` maps to `None` (unbounded full-table read). |
| `HISTORY_PAGE_SIZES` (`src/bdboard/derive/history.py`) | `(25, 50, 100)` | The allowed rows-per-page set the `<select>` offers and `clamp_page_size` validates against. |
| `HISTORY_PAGE_SIZE` (`src/bdboard/derive/history.py`) | `50` | Default/fallback page size on a missing/invalid/tampered `page_size`. |
| `LIST_TIMEOUT_S` (`src/bdboard/bd.py`) | `15.0` s | Per-`bd list` subprocess timeout for the closed-history fetch (generous: large workspaces). On timeout the fetch raises; `store` swallows it and the region degrades to empty. |
| `STATUS_TIMEOUT_S` (`src/bdboard/bd.py`) | `8.0` s | `bd status --json` timeout for the optional headline. On timeout `status_summary` returns `None` and the global Total/Closed cells are omitted. |
| `BDBOARD_WORKSPACE` (env) | `$PWD` / cwd | Workspace whose `.beads/` the history reads target. |
| `BDBOARD_BD_BIN` (env) | `bd` | The `bd` binary the history subprocesses invoke; must resolve. |

> [!NOTE]
> The ranges, page-size set/default, and the two timeouts are **module-level
> constants**, not environment variables — change them in source (and re-run the
> history tests). Only the `BDBOARD_*` keys are runtime-configurable.

## Edge Cases

> [!WARNING]
> **"Avg lead" in the masthead is *not* bd's lead time.** The headline
> `stats.avg_cycle_h` is the **mean claim→close cycle time** (`started_at →
> closed_at`), while `stats.median_lead_h` IS created→close lead time, and
> `bd_summary.average_lead_time_hours` is bd's *workspace-global* created→close
> figure. Three different spans by design — don't conflate them.

> [!WARNING]
> **Custom `from_date`/`to_date` supersede `range=` entirely.** The moment
> either parses, `derive._resolve_bounds` ignores the preset for the closed
> list, every series, AND the KPIs. The `to_date` day is **fully included** via
> an exclusive start-of-next-day ceiling (`custom_bounds`), and an inverted
> `from > to` is silently swapped so the window never collapses to empty.

> [!WARNING]
> **History is count-uncapped but window-bounded.** Unlike the board's
> date-capped `list_closed`, the history fetch runs `--limit 0` (bdboard-a194)
> so older closures stay reachable; memory pressure is instead controlled by the
> resolved `--closed-after` lower bound (bdboard-gp06). Only `range=all`
> (`cutoff=None`) is a genuine full-table read — expect it to be the heaviest
> query on a large workspace.

> [!WARNING]
> **Beads with no parseable timestamp silently drop off the timeline.** A closed
> bead with no `closed_at` is excluded from the closed list and throughput;
> cycle metrics skip beads lacking `started_at`; negative/zero durations (clock
> skew) are dropped from lead/cycle stats. Counts can therefore be lower than a
> naïve "all closed" tally — that's intentional, not data loss.

> [!CAUTION]
> **A bd-read failure degrades to an *empty* region, not an error.** A transient
> `bd list` timeout on a cache-cold load momentarily blanks the closed
> list/chart (`store` logs `bd list_closed_history failed; history cache stays
> empty`). The next successful SSE `refresh from:body` repaints it — don't
> mistake a degraded blank for "nothing closed". Check the logs.

## Error Scenarios

| Trigger | Behavior | User sees |
| --- | --- | --- |
| `?range=` unknown/empty | Degrades to `DEFAULT_HISTORY_RANGE` in `api_history` and again in `derive._range_to_cutoff` | `200` — the 30d window renders; no error |
| `?page_size=` out-of-set but integer (e.g. `42`) | `derive.clamp_page_size` returns `50` | `200` — 50-row pages; no error |
| `?page=` / `?page_size=` non-integer | FastAPI `int` coercion rejects before `api_history` runs | `422` — `RequestValidationError` JSON `{"detail": [...]}` |
| `?page=0` or negative | Clamped to `max(1, page)` | `200` — page 1 |
| `from_date`/`to_date` unparseable | `derive._parse_date` returns `None` (treated as "no bound"); if neither parses, falls back to the preset `range` | `200` — preset window renders |
| `from_date > to_date` | Swapped in `derive.custom_bounds` | `200` — window stays meaningful |
| `bd list_closed_history` fails (timeout / non-zero / bad JSON) | `Store._load_history` logs and leaves the history cache empty; route derives over `[]` | `200` (degraded) — `Nothing closed in the last <window>…` + `No beads created or closed to chart…` |
| `bd status` fails | `status_summary()` returns `None` | `200` — masthead global `Total`/`Closed` cells omitted; range KPIs remain |
| Page past the end (`page > 1`, no items) | `history_window` returns empty `items`, `has_more=False` | `200` — `Nothing on page <n> — back to page 1` link-button |
| `GET /history` and `_validate_or_warn()` fails (broken workspace) | Page route returns `error.html` | `500` — workspace error page |
| Unexpected exception escaping `api_history` | FastAPI default handler | `500` — `Internal Server Error` (normal bd failures are caught upstream and never reach here) |

## Testing

- **Route behavior** — `tests/test_api_history.py` (the big one) covers
  `GET /api/history` end to end against a stubbed snapshot: range selection,
  pagination, page-size clamping, custom-window precedence, the OOB stats swap,
  and the bd-failure **degrade** path (empty region, not `500`).
- **Pure derivations** — `tests/test_derive_history.py` exhaustively covers
  `history_window` (pagination/sort/out-of-range pages), `throughput`/`created`
  (gap-fill, day bucketing), `combined` (merged timeline), `lead_time_stats`
  (lead vs cycle, percentiles, skew dropping), `resolve_history_bounds` /
  `custom_bounds` (precedence, inversion, exclusive ceiling), and
  `clamp_page_size`.
- **Window cache** — `tests/test_store_history_window.py` covers
  `snapshot_history` / `_history_covers`: a wider cache serves a narrower
  sub-window with no bd call; an unbounded request re-queries a bounded cache.
- **Fetch bound** — `tests/test_bd_closed_history.py` asserts the
  `--closed-after` push-down and the `--limit 0` count-uncapped shape.
- **Headline** — `tests/test_bd_status_summary.py` covers the optional
  `status_summary` (summary extraction + `None` on hiccup).
- **Shell** — `tests/test_page_history.py` covers the cheap shell render and the
  workspace-error `500`.
- **Accessibility** — `tests/test_created_bar_contrast.py` keeps the created
  bars' colour + hatch within WCAG AA so the chart isn't colour-only.
- **Manual check** — start the server, open `/history`; confirm the skeleton →
  region swap, click each range + Custom, page through, change rows-per-page
  (persists across reload), and open a closed card (modal). From a terminal:
  ```bash
  curl -i 'http://127.0.0.1:8765/api/history'
  curl -i 'http://127.0.0.1:8765/api/history?range=90d&page=2&page_size=25'
  curl -i 'http://127.0.0.1:8765/api/history?from_date=2026-05-01&to_date=2026-05-31'
  ```
  Expect `200` + the `partials/history.html` fragment (with the embedded
  `hx-swap-oob` stats `<dl>`); a bad `range=` renders the 30d default; a
  non-integer `page`/`page_size` yields `422`.

## Related

- [History page (`/history`)](../Views/HistoryPage.md) — the full-page view
  (range control, Custom popover, pager, page-size selector, skeletons) this
  feature is the behavior-first overview of.
- [History API (`/api/history`)](../Endpoints/HistoryApi.md) — the HTTP contract
  for the single read-only swap region (request params, response shapes,
  validation, error table) this feature drives.
- [Bead detail API (`/api/bead/{id}`)](../Endpoints/BeadDetailApi.md) — the
  endpoint behind the shared modal each closed card opens.
- [SSE events (`/api/events`)](../Endpoints/SseEvents.md) — the live-refresh
  stream that re-fetches the region on `.beads/` changes.
- [Lanes API (`/api/lanes`, `/api/lanes/closed`, `/api/counts`)](../Endpoints/LanesApi.md)
  — the board's read-only hydration endpoints; their date-capped `list_closed`
  is the short-window complement to this feature's uncapped,
  `--closed-after`-bounded `list_closed_history` (the board/History closed-record
  split, bdboard-p8v / bdboard-a194).
- [Board page (`/`)](../Views/BoardPage.md) — the short-window recent-activity
  surface this feature is the long-window complement to (its 12h/1d/3d lane
  filter and date-capped Closed lane).
- [Live auto-refresh (Feature)](LiveAutoRefresh.md) — the SSE `beads_changed →
  refresh from:body` mechanism that repaints this region on every workspace
  change.
- [bd CLI as runtime source of truth](../Concepts/BdCliSourceOfTruth.md) — why
  the closed record and `bd status` totals bottom out in `bd list`/`bd status`
  subprocesses serialized by `_subprocess_gate`.
- [Store snapshot cache & change detection](../Concepts/StoreSnapshotCache.md) —
  the window-aware history cache (`_history_covers`/`_history_cutoff`),
  `--closed-after` push-down (bdboard-gp06), and count-uncapped fetch
  (bdboard-a194) this feature relies on.
- [Derive layer (pure view shaping)](../Concepts/DeriveLayer.md) — the pure
  `derive.history` functions (`history_window`, `throughput`, `created`,
  `combined`, `lead_time_stats`, `resolve_history_bounds`) that shape this
  feature with zero I/O.
- [HTMX + server-rendered partials](../Concepts/HtmxPartialsArchitecture.md) —
  the `hx-get` + `innerHTML` swap idiom and the `hx-swap-oob` masthead-stats
  pattern this feature embodies (one fetch, two surfaces).
- [Features index](index.md) · [Architecture](../Architecture.md#key-flows) ·
  [Manifest](../_Manifest.md) — the feature catalog and system view this sits in.
