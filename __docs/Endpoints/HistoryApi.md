# GET /api/history

The **History swap region** behind the `/history` page. A single read-only HTMX
target that renders the long-window retrospective surface: a range/custom-date
control, a combined *created-vs-closed* per-day bar chart, a paginated list of
**closed** beads (newest-closed first), and — emitted out-of-band into the
masthead — a range-scoped KPI strip. It is the complement to the board's
short-window 12h/1d/3d lane filter and 50-cap closed lane.

The route is **pure derivation over a snapshot** (design §4): it issues no
mutation and, on the cache-warm path, no new `bd` subprocess at all. It resolves
the active window **once** from a single `now`, pushes that lower bound down to
the bd closed-history fetch (so a narrow range fetches only the beads closed
inside it rather than slurping the whole closed table), then shapes every
view — the paginated closed list, the throughput/created/combined per-day
series, and the lead-time KPIs — from that one in-memory snapshot before handing
them to `partials/history.html`.

Like every bdboard route it returns an **HTML fragment**
(`response_class=HTMLResponse`), never JSON. The response carries two surfaces in
one round-trip: `partials/history.html` swaps into `#history-region`, and the
`partials/history_stats.html` `<dl>` it includes rides along as an
`hx-swap-oob="true"` element that HTMX peels off and swaps into the masthead's
`#history-stats` host. One fetch keeps the body and the header KPIs in sync on
every range click and SSE refresh — no second endpoint, no client framework.

## Overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/history` | None (localhost single-user tool); read-only, no body, no CSRF token involved | Render the History swap region (HTMX target). Resolves the window (`range`/custom dates), pushes the lower bound to `bd list --status closed --closed-after`, then derives the paginated closed list + per-day series + range KPIs from one snapshot. Returns `partials/history.html` plus the OOB `partials/history_stats.html`. |

> [!NOTE]
> This is a **read-only** route — there is no `bd` mutation, no request body,
> and therefore **no CSRF token** (unlike the sibling write routes such as
> [Memory API](MemoryApi.md) and [Bead field-edit API](BeadFieldEditApi.md)).
> Being localhost single-user, it has no login or per-user authorization either.

> [!IMPORTANT]
> The History page is deliberately **count-uncapped** but **window-bounded**.
> A static fetch cap would silently truncate to the newest N closures and make
> anything older unreachable regardless of the filters (bdboard-a194), so
> `bd list` runs with `--limit 0`. Memory pressure is instead controlled by the
> resolved `closed_after` lower bound (bdboard-gp06) — only `range=all` (which
> resolves `cutoff=None`) stays a genuine full-table read.

## Request

`GET /api/history` is fully driven by **query parameters** — there are no path
params, no required headers, and no body. The range control badges, pager,
page-size `<select>`, and Custom-date popover form each fire an `hx-get` with the
appropriate params; the bare `load` and SSE `refresh from:body` fetches send
none, and `base.html` JS re-injects the active window + persisted page size on
those bare requests so a busy SSE stream can't snap the user back to the default.

### Path/Query Params

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `range` | query | string | No (default `derive.DEFAULT_HISTORY_RANGE` = `"30d"`) | One of `7d` / `30d` / `90d` / `all` (keys of `derive.HISTORY_RANGES`). `.strip().lower()`ed; any value not in the set degrades to `30d`. `all` resolves to an unbounded `cutoff=None`. Sent by the preset range badges as `?range=<r>&page=1&page_size=<size>`. Superseded by a valid `from_date`/`to_date`. |
| `page` | query | int | No (default `1`) | 1-based page of the closed list; clamped server-side to `max(1, page)`. Drives the pure in-memory slice in `derive.history_window` — no extra I/O per page. Sent by the Prev (`‹ Newer`) / Next (`Older ›`) pager buttons. |
| `page_size` | query | int \| None | No (default `None` → clamped to `50`) | Rows per page; coerced by `derive.clamp_page_size` to the allowed set `{25, 50, 100}` (`derive.HISTORY_PAGE_SIZES`), falling back to `50` (`HISTORY_PAGE_SIZE`) on missing/invalid/tampered input. Sent by the per-page `<select id="history-page-size-select">` and mirrored into bare `load`/SSE fetches from `localStorage['bdboard-history-page-size']` by `base.html`'s `htmx:configRequest` injector. |
| `from_date` | query | string `YYYY-MM-DD` | No | Inclusive start-of-day lower bound of a custom window. When it (or `to_date`) parses, it **supersedes** `range=` for every series, the closed list, and the KPIs (precedence resolved in one place by `derive._resolve_bounds`). Non-`YYYY-MM-DD` shapes are treated as "no bound". Sent by the Custom popover `<form>`. |
| `to_date` | query | string `YYYY-MM-DD` | No | Custom-window upper bound; resolved to an **exclusive** start-of-next-day ceiling (`derive.custom_bounds`) so the chosen `to` day is fully included. Inverted `from`/`to` are swapped so the window never collapses to empty. Sent by the Custom popover `<form>`. |

### Headers

| Header | Required | Notes |
| --- | --- | --- |
| _(none required)_ | No | Read-only GET — no `X-CSRF-Token`, no `Content-Type` (no body). HTMX adds its usual `HX-Request: true` / `HX-Target: history-region` headers, but the handler ignores them; the same response is correct for a plain browser GET. |

### Body

None. `GET /api/history` carries no request body — all input is in the query
string. (For comparison, the mutating sibling routes use a form body; this route
does not.)

```json
// No request body — GET with query params only, e.g.:
// /api/history?range=90d&page=2&page_size=25
// /api/history?from_date=2026-05-01&to_date=2026-05-31&page=1&page_size=50
```

### Validation Rules

All "validation" here is **degrade-don't-error**: a bad query param can never
break the swap. Every rule resolves to a safe default rather than a 4xx.

| Field | Rule | Behavior on violation |
| --- | --- | --- |
| `range` | Must be a key of `derive.HISTORY_RANGES` (`7d`/`30d`/`90d`/`all`) | Unknown/empty degrades to `DEFAULT_HISTORY_RANGE` (`30d`) inside the handler and again in `derive._range_to_cutoff` — no error. |
| `page` | Coerced to `max(1, page)` | Zero/negative clamps to page 1. A non-int query value is rejected by FastAPI's `int` coercion as `422` before the handler runs (see Errors). |
| `page_size` | Must parse to a member of `{25, 50, 100}` | Missing/invalid/tampered → `derive.clamp_page_size` returns `50`. A non-int query value is `422`'d by FastAPI before the handler. |
| `from_date` / `to_date` | Must match `%Y-%m-%d` | Unparseable → `derive._parse_date` returns `None` (treated as "no bound"); if neither parses, the route falls back to the `range=` preset. |
| `from_date` > `to_date` | Inverted custom window | Swapped in `derive.custom_bounds` so the window stays meaningful. |

### Rate Limit

| Limit | Window | Scope |
| --- | --- | --- |
| None explicit. On a cache-warm snapshot the route makes **zero** bd calls (pure derive). On a cache miss / wider window, the `bd list` (closed history) and the optional `bd status` reads are **serialized** by `BdClient._subprocess_gate` (`asyncio.Semaphore(1)`) and each bounded by its own timeout (`LIST_TIMEOUT_S=15.0`, `STATUS_TIMEOUT_S=8.0`). | per-process | All bd reads/writes across all tabs/clients share the one single-writer gate, so concurrent history loads queue behind any in-flight bd subprocess rather than racing dolt. The window-aware history cache means a narrower sub-window is served from memory with no bd call at all. |

## Response

A single **HTML fragment** (`text/html`, `response_class=HTMLResponse`), never
JSON. The body is `partials/history.html` (for the `#history-region` `innerHTML`
swap); embedded within it is `partials/history_stats.html` carrying
`hx-swap-oob="true"`, which HTMX detaches and swaps into the masthead's
`#history-stats` host. Both surfaces update from this one response.

### Success

**`200 OK`** — the History region fragment + OOB stats strip. The template
receives this context from `api_history` (real keys):

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
    "items": [ { "id": "bdboard-...", "title": "...", "status": "closed", "closed_at": "2026-05-30T17:04:00Z", "created_at": "...", "priority": 2 } ],
    "page": 1,
    "page_size": 50,
    "total": 137,
    "has_more": true
  },
  "created_total": 142,
  "combined_series": [ { "day": "2026-05-03", "created": 4, "closed": 2 } ],
  "combined_peak": 9,
  "stats": {
    "n": 137,
    "median_lead_h": 41.5,
    "p90_lead_h": 188.0,
    "median_cycle_h": 6.2,
    "p90_cycle_h": 33.1,
    "avg_cycle_h": 12.4
  },
  "avg_per_day": 4.6,
  "bd_summary": {
    "total_issues": 412,
    "closed_issues": 318,
    "in_progress_issues": 11,
    "average_lead_time_hours": 53.7
  }
}
```

Rendered, the fragment is the `.history-region-inner` block: the range toolbar
(`7d`/`30d`/`90d`/`All` + the Custom popover), the `Created vs closed` combined
bar chart (or a "No beads created or closed to chart…" empty state), the
paginated `Closed beads` list of `bead_card.html` cards with a Prev/Next pager
and page-size `<select>` (or a context-aware empty state), and the OOB
`<dl class="counts history-stats" hx-swap-oob="true">` masthead strip.

> [!NOTE]
> `bd_summary` is **optional sugar**: `store.bd.status_summary()` returns `None`
> on any bd hiccup, and `partials/history_stats.html` simply omits the global
> `Total` / `Closed` cells when it's `None`, leaving the range-derived KPIs as
> the primary surface. The route never 500s just because `bd status` failed.

> [!WARNING]
> "Avg lead" in the masthead is the **mean claim→close cycle time**
> (`stats.avg_cycle_h`, `started_at → closed_at`), NOT bd's workspace-global
> created→close lead time. "Median lead" (`stats.median_lead_h`) IS
> created→close. They measure different spans by design — don't conflate them.

### Errors

This route is failure-tolerant by construction: a bd outage degrades to an empty
region / missing headline rather than a 5xx. The only hard error statuses come
from FastAPI's own param coercion.

| Status | Code (source / shape) | When |
| --- | --- | --- |
| 422 | FastAPI `RequestValidationError` JSON (`{"detail": [...]}`) | A non-integer `page` or `page_size` query value — FastAPI's `int` coercion rejects it before `api_history` runs. (Out-of-set-but-integer `page_size` does **not** error; it clamps to 50.) |
| 200 (degraded) | Empty region — `Nothing closed in the last <window>…` / `No beads created or closed to chart in <window>` | `store.snapshot_history` swallows a `bd list` failure (logs `store: bd list_closed_history failed; history cache stays empty`) and returns `active + []`, so the closed list and series render empty rather than erroring. |
| 200 (degraded) | Masthead headline cells omitted | `store.bd.status_summary()` returned `None` (bd `status` timeout / non-zero / malformed) — the global `Total`/`Closed` cells are dropped; range KPIs remain. |
| 500 | FastAPI default `Internal Server Error` | Only on an unexpected exception escaping the handler (e.g. a bug in a derive function on malformed snapshot data). The normal bd-failure paths are caught upstream in `store` and never reach here. |

> [!CAUTION]
> Because bd-read failures degrade to an **empty** region (not an error), a
> transient `bd list` timeout can momentarily blank the closed list/chart on a
> cache-cold load. The next successful SSE `refresh from:body` re-fetch repaints
> it. Don't mistake a degraded blank for "no closed beads" — check the logs for
> `store: bd list_closed_history failed`.

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |
| Route handler (resolve window, fetch snapshot, derive all views, render) | `src/bdboard/app.py` | `api_history` |
| Full-page shell that lazy-loads this region via HTMX `load` + SSE `refresh` | `src/bdboard/app.py` | `page_history` |
| Range presets + default + page-size set/default | `src/bdboard/derive/history.py` | `HISTORY_RANGES` / `DEFAULT_HISTORY_RANGE` / `HISTORY_PAGE_SIZES` / `HISTORY_PAGE_SIZE` |
| Page-size coercion to the allowed set (single source of truth) | `src/bdboard/derive/history.py` | `clamp_page_size` |
| Window bounds resolver (custom from/to supersede preset `range`) — shared by route + derives | `src/bdboard/derive/history.py` | `resolve_history_bounds` / `_resolve_bounds` / `custom_bounds` / `_range_to_cutoff` / `_parse_date` |
| Paginated closed-list slice (`{items, page, page_size, total, has_more}`) | `src/bdboard/derive/history.py` | `history_window` / `_closed_in_window` |
| Closed-per-day series (combined chart `closed` arm + `avg_per_day`) | `src/bdboard/derive/history.py` | `throughput` / `_daily_count_series` / `_bucket_by_day` / `_fill_daily_series` |
| Created-per-day series (`created_total` + combined chart `created` arm) | `src/bdboard/derive/history.py` | `created` / `_created_in_window` |
| Combined created+closed per-day timeline (one gap-free series) | `src/bdboard/derive/history.py` | `combined` / `_iter_day_span` |
| Lead/cycle-time KPI block (`{n, median_lead_h, p90_lead_h, median_cycle_h, p90_cycle_h, avg_cycle_h}`) | `src/bdboard/derive/history.py` | `lead_time_stats` / `_percentile` |
| Snapshot provider (active + window-bounded history-closed; window-aware cache) | `src/bdboard/store.py` | `Store.snapshot_history` / `_history_covers` / `_load_history` / `_history_cutoff` |
| Count-uncapped, `--closed-after`-bounded closed fetch (`bd list --status closed --sort closed --no-pager --limit 0`) | `src/bdboard/bd.py` | `BdClient.list_closed_history` / `LIST_TIMEOUT_S` |
| Optional workspace-global headline (`bd status --json` → `summary`, TTL-cached) | `src/bdboard/bd.py` | `BdClient.status_summary` / `STATUS_TIMEOUT_S` |
| Single-writer serialization for every bd subprocess (dolt is single-writer) | `src/bdboard/bd.py` | `BdClient._subprocess_gate` |
| Region template (toolbar, combined chart, paginated list, pager, page-size select) | `src/bdboard/templates/partials/history.html` | `.history-region-inner` / `.history-ranges` / `.history-throughput` / `.history-pager` |
| OOB masthead KPI strip (global totals + range KPIs, `hx-swap-oob`) | `src/bdboard/templates/partials/history_stats.html` | `dl#history-stats` / `stat_info` macro |
| Region + masthead host, `load`/`refresh from:body` triggers, skeleton | `src/bdboard/templates/history.html` | `#history-region` / `#history-stats` |
| Bare-fetch window + page-size re-injection (so SSE/load keep the active window) | `src/bdboard/templates/base.html` | `htmx:configRequest` injectors (`activePresetRange` / `activeCustom` / `storedSize`) |
| Closed-list card markup (clicking opens the shared bead modal) | `src/bdboard/templates/partials/bead_card.html` | `bead_card` |
| Regression tests | `tests/test_api_history.py`, `tests/test_derive_history.py`, `tests/test_store_history_window.py`, `tests/test_bd_closed_history.py`, `tests/test_page_history.py` | range/pagination/custom-window/degrade/fetch-bound coverage |

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant H as HTMX (history.html / base.html)
    participant R as api_history (app.py)
    participant D as derive.history
    participant S as Store (store.py)
    participant BD as BdClient (bd.py)
    participant Proc as bd subprocess
    participant T as history.html + history_stats.html

    Note over U,T: First paint / SSE refresh (bare) — base.html re-injects active window
    U->>H: #history-region load / refresh from:body
    H->>R: GET /api/history (range/from/to + page_size injected by base.html)
    R->>R: clamp page=max(1,page); size=clamp_page_size(page_size)
    R->>D: resolve_history_bounds(range, from, to, now) -> (cutoff, ceiling)
    R->>S: snapshot_history(closed_after=cutoff)
    alt cache covers window
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
    R->>D: history_window / throughput / created / combined / lead_time_stats (pure)
    R->>S: bd.status_summary() (bd status --json, TTL-cached; None on hiccup)
    S-->>R: summary | None
    R->>T: render history.html (+ OOB history_stats.html)
    T-->>H: 200 fragment (region body + hx-swap-oob stats <dl>)
    H->>U: innerHTML swap #history-region; OOB swap #history-stats

    Note over U,T: Range / pager / page-size / custom — explicit window wins
    U->>H: click 90d / Older › / Per page / Custom Apply
    H->>R: GET /api/history?range=90d&page=2&page_size=25 (or from_date/to_date)
    R-->>H: 200 fresh fragment for that window/page
    H->>U: re-swap #history-region + #history-stats
```

## Example

Bare region fetch (what the page fires on `load`; server resolves the default
30d window, page 1, page size 50):

```bash
curl -i 'http://127.0.0.1:8765/api/history'
```

Pick a preset window, jump to page 2, and ask for 25 rows (what the range badge
+ pager + page-size select produce):

```bash
curl -i 'http://127.0.0.1:8765/api/history?range=90d&page=2&page_size=25'
```

Unbounded "all time" view (full-table read by design — `cutoff=None`):

```bash
curl -i 'http://127.0.0.1:8765/api/history?range=all&page=1&page_size=100'
```

Custom date window (supersedes `range=`; the `to_date` day is fully included via
the exclusive next-day ceiling):

```bash
curl -i 'http://127.0.0.1:8765/api/history?from_date=2026-05-01&to_date=2026-05-31&page=1&page_size=50'
```

All return `200` with the `partials/history.html` fragment (plus the embedded
`hx-swap-oob` stats `<dl>`) for an `innerHTML` swap into `#history-region`. A bad
`range=` silently renders the 30d default; a bad-but-integer `page_size` clamps
to 50; a non-integer `page`/`page_size` yields `422`.

## Related

- [History & trends (Feature)](../Features/HistoryAndTrends.md) — the
  behavior-first overview of the whole History surface this endpoint powers
  (the feature spec this route implements).
- [History page (`/history`)](../Views/HistoryPage.md) — the full-page view
  whose range control, pager, page-size selector, and Custom-date popover drive
  every call to this route; the page shell renders `#history-region` +
  `#history-stats`, then hydrates them from the first `/api/history` fetch and
  re-fetches on every SSE `refresh from:body` (the `beads_changed` →
  `refresh from:body` live-refresh mechanism that repaints this region
  out-of-band on every workspace change).
- [Board page (`/`)](../Views/BoardPage.md) — the short-window counterpart this
  endpoint complements; the board's `/api/lanes` region is the symmetric
  read-only swap target `api_history` is modelled on (pure derive over a
  snapshot, HTML fragment, no mutation).
- [Lanes API (`/api/lanes`, `/api/lanes/closed`, `/api/counts`)](LanesApi.md) —
  the board's read-only hydration endpoints this route is symmetric with; their
  date-capped `list_closed` board path is the complement to this route's
  uncapped, `--closed-after`-bounded `list_closed_history` path (the board/History
  closed-record split, bdboard-p8v / bdboard-a194).
- [Bead detail API (`/api/bead/{id}`, …)](BeadDetailApi.md) — the modal opened
  when a card in this endpoint's closed list is clicked (`bead_card.html`).
- [bd CLI as runtime source of truth](../Concepts/BdCliSourceOfTruth.md) — why
  this route bottoms out in `bd list`/`bd status` subprocesses serialized by
  `_subprocess_gate` rather than touching the dolt store directly.
- [Store snapshot cache & change detection](../Concepts/StoreSnapshotCache.md) —
  the window-aware history cache (`_history_covers`/`_history_cutoff`),
  `--closed-after` push-down (bdboard-gp06), and count-uncapped fetch
  (bdboard-a194) this route relies on.
- [Derive layer (pure view shaping)](../Concepts/DeriveLayer.md) — the pure
  `derive.history` functions (`history_window`, `throughput`, `created`,
  `combined`, `lead_time_stats`, `resolve_history_bounds`) that shape this
  response with zero I/O.
- [HTMX + server-rendered partials](../Concepts/HtmxPartialsArchitecture.md) —
  the `hx-get` + `innerHTML` swap idiom and the `hx-swap-oob` masthead-stats
  pattern this endpoint embodies (one fetch, two surfaces).
- [Endpoints index](index.md) · [Architecture](../Architecture.md#api-surface) ·
  [Manifest](../_Manifest.md) — the API surface and doc catalog this item sits in.
