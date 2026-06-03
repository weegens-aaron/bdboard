# Endpoint: History API (`/api/history`)

## Overview

| METHOD | Path | Purpose |
| --- | --- | --- |
| GET | `/api/history?range=&page=&page_size=&from_date=&to_date=` | Render the entire History swap region (range control + "Created vs closed" chart + paginated closed-bead list) **and** the masthead KPI strip out-of-band, in one round-trip. |

This is the single read endpoint behind the [History page](../Views/history-page.md).
It is **symmetric with [`/api/lanes`](lanes-api.md)**: a thin route that does no
business logic of its own beyond resolving the active window, then hands one
`bd` snapshot to the pure [derive layer](../Concepts/derive-layer.md) and renders
[`partials/history.html`](../../src/bdboard/templates/partials/history.html). It
exists because the History page route ([`page_history`](../../src/bdboard/app.py))
deliberately holds **no** data and never calls `bd` — first paint is instant and
the slow snapshot/derive work is fetched lazily here on HTMX `load`, on SSE
`refresh`, and on every range / custom / pager / page-size interaction (design
§D4). One fetch updates two surfaces: the response body swaps `#history-region`
while an appended `hx-swap-oob` fragment updates the masthead `#history-stats`
strip.

> [!IMPORTANT]
> This endpoint is **read-only** and carries **no CSRF requirement** — unlike the
> write surfaces ([Memory](memory-api.md), [Bead field-edit](bead-field-edit-api.md),
> [Formulas pour](formulas-api.md)) it never mutates `bd`. Every render is **pure
> derivation over one snapshot, no new `bd` subprocess per page** of the closed
> list (design §4); pagination is an in-memory slice, not a re-query.

## Request

### Headers

| Header | Required | Notes |
| --- | --- | --- |
| `HX-Request` | No | Sent by HTMX on every fetch. The handler does not branch on it — the response is always the `#history-region` partial regardless — but it documents that this endpoint is an HTMX swap target, not a navigable page. |

> [!IMPORTANT]
> There are **no** authentication or CSRF headers. The endpoint is a pure GET
> read; the only state it consumes is the query string below.

### Params / Query

All params are optional; every one degrades to a safe default so a missing or
tampered value can never break the render. The window is resolved **once** from a
single `now = datetime.now(UTC)` so the server-side `bd` fetch bound and every
in-memory derive slice agree on the exact same lower bound with no off-by-one
drift (bdboard-gp06).

| Name | Type | Required | Default | Validation |
| --- | --- | --- | --- | --- |
| `range` | query string | No | `"30d"` (`derive.DEFAULT_HISTORY_RANGE`) | `.strip().lower()`ed and checked against `derive.HISTORY_RANGES` (`7d` / `30d` / `90d` / `all`). Any unknown/empty value degrades to the default `30d` inside the handler **and** again in the derive layer. `all` is the unbounded view. Superseded by a valid custom `from_date`/`to_date`. |
| `page` | int | No | `1` | `max(1, page)` — clamped to `>= 1`. A page past the end renders a graceful "Nothing on page N — back to page 1" state rather than erroring. |
| `page_size` | int \| null | No | `50` (`derive.HISTORY_PAGE_SIZE`) | Coerced via [`derive.clamp_page_size`](../../src/bdboard/derive/history.py): parses to int and must be a member of `derive.HISTORY_PAGE_SIZES` (`{25, 50, 100}`); any other / unparseable / missing value clamps to `50`. Single source of truth so the route and the selector agree. |
| `from_date` | query string (`YYYY-MM-DD`) | No | `None` | Parsed by `derive._parse_date` (strict `%Y-%m-%d`, start-of-day UTC). Unparseable ⇒ treated as "no bound". Inclusive lower bound. |
| `to_date` | query string (`YYYY-MM-DD`) | No | `None` | Same parser; resolved to an **exclusive** start-of-next-day ceiling so a `to_date` of `2026-05-30` includes everything stamped on the 30th. Inverted `from`/`to` are swapped, not collapsed. |

> [!WARNING]
> When **either** `from_date` or `to_date` parses, the custom window **supersedes**
> `range=` for the chart, the KPIs, *and* the closed list — the precedence is
> resolved in one place ([`derive.resolve_history_bounds`](../../src/bdboard/derive/history.py)).
> The response then marks the synthetic `custom` preset active (`active_range="custom"`,
> `is_custom=True`) so the UI reflects the custom selection after each swap. An
> open-ended lower bound (only `to_date`, no `from_date`) resolves `cutoff=None`,
> leaving the underlying fetch unbounded — the user explicitly chose no lower
> bound.

### Body

None. `GET` carries no request body.

## Response

### Success

**`200 OK`**, `Content-Type: text/html` — an **HTML fragment** rendered from
[`partials/history.html`](../../src/bdboard/templates/partials/history.html), not
JSON. HTMX swaps it `innerHTML` into `#history-region`. The fragment contains:

1. **Range toolbar** — the `7d` / `30d` / `90d` / `All` filter badges (mirroring
   the board's filter-badge idiom, `aria-pressed` on the active window) plus the
   **Custom** badge and its hidden from/to date popover (`role="dialog"`).
2. **"Created vs closed" grouped-bar chart** — one fixed-height, day-bucketed
   strip pairing the created series (hatched) and closed series per day against a
   shared peak. Not colour-only: a legend names each series and every cell carries
   a descriptive text `aria-label` (`role="img"`). Empty windows render a
   "No beads created or closed to chart in …" message.
3. **Paginated closed-bead list** — newest-closed first, each a reused
   [`bead_card.html`](../../src/bdboard/templates/partials/bead_card.html)
   (`meta="history"`) that opens the shared `#bead-modal` via `hx-get /api/bead/{id}`,
   plus a Newer/Older pager and the per-page `<select>` (25 / 50 / 100). Out-of-range
   pages and empty windows render graceful copy.
4. **Out-of-band KPI strip** — [`partials/history_stats.html`](../../src/bdboard/templates/partials/history_stats.html)
   appended with `hx-swap-oob="true"`, which HTMX peels off the **same** response
   and swaps into the masthead `#history-stats` host. It carries the range-derived
   KPIs (Avg lead, Closed (range), Median lead, Throughput/day) plus, when
   available, bd's workspace-global `status_summary()` totals (Total / Closed
   all-time) under a "via bd" heading.

> [!WARNING]
> The KPI strip mixes two scopes that look alike: **Total** and **Closed
> (all time)** come from `bd status` (`store.bd.status_summary()`) and are
> **point-in-time, workspace-global** — they do **not** react to the range
> control. **Avg lead**, **Closed (range)**, **Median lead** and **Throughput**
> are **range-scoped** derivations. `status_summary()` returning `None` (any
> `bd status` hiccup) simply omits the two global cells; the range-derived KPIs
> remain the primary surface so the masthead degrades gracefully rather than
> erroring.

### Errors

| Status | When | Body |
| --- | --- | --- |
| `200` | A bad `range=`, out-of-range `page`, invalid `page_size`, or unparseable `from_date`/`to_date`. | The endpoint **never** error-statuses on bad input — each param degrades to its default (range→`30d`, page-past-end→a graceful "Nothing on page N" fragment, bad size→`50`, bad date→no bound). |
| `200` | `bd` snapshot fetch fails. | The [Store](../Concepts/store-snapshot-cache.md) leaves the existing cache in place (better stale than empty), so the region still renders. |
| `200` | `bd status` (`status_summary`) fails. | The optional "via bd" Total/Closed headline cells are omitted; the range-derived KPIs still render. |

> [!CAUTION]
> Do **not** add per-param `4xx` validation here "to be strict". The whole design
> contract is **graceful degradation**: a tampered or stale query string from an
> SSE refresh, a bookmark, or a hand-edited URL must always paint *something*
> useful, never a broken swap target. Every clamp lives in the [derive
> layer](../Concepts/derive-layer.md) precisely so the endpoint stays a thin,
> total function.

## Implementation Map

| Concern | Where |
| --- | --- |
| Handler | [`src/bdboard/app.py:api_history`](../../src/bdboard/app.py) |
| Page route (shell only) | [`src/bdboard/app.py:page_history`](../../src/bdboard/app.py) → [`templates/history.html`](../../src/bdboard/templates/history.html) |
| Window resolution | [`derive.resolve_history_bounds`](../../src/bdboard/derive/history.py) (single source of truth; `custom_bounds` + `_range_to_cutoff`) |
| Range / page-size constants | [`derive.HISTORY_RANGES`](../../src/bdboard/derive/history.py), `DEFAULT_HISTORY_RANGE`, `HISTORY_PAGE_SIZES`, `clamp_page_size` |
| Bounded snapshot read | [`store.snapshot_history(closed_after=cutoff)`](../../src/bdboard/store.py) → [`bd.list_closed_history`](../../src/bdboard/bd.py) (`bd list --status closed --sort closed --limit 0 [--closed-after <iso>]`) |
| Closed list (paginated) | [`derive.history_window`](../../src/bdboard/derive/history.py) (`{items, page, page_size, total, has_more}`) |
| Combined chart series | [`derive.combined`](../../src/bdboard/derive/history.py) (+ `combined_peak`) |
| Per-day series (legend counts) | [`derive.throughput`](../../src/bdboard/derive/history.py), [`derive.created`](../../src/bdboard/derive/history.py) |
| Lead/cycle-time KPIs | [`derive.lead_time_stats`](../../src/bdboard/derive/history.py) |
| Workspace-global headline | [`store.bd.status_summary`](../../src/bdboard/bd.py) (`bd status --json`, cached) |
| Region template | [`partials/history.html`](../../src/bdboard/templates/partials/history.html) |
| OOB KPI strip | [`partials/history_stats.html`](../../src/bdboard/templates/partials/history_stats.html) (`hx-swap-oob="true"` → masthead `#history-stats`) |
| Closed card | [`partials/bead_card.html`](../../src/bdboard/templates/partials/bead_card.html) (`meta="history"`) |

> [!IMPORTANT]
> The resolved `cutoff` is pushed **down** into the snapshot fetch as
> `--closed-after`, so a narrow range only pulls the beads closed inside its
> window instead of slurping the whole closed table into memory on every render
> (bdboard-gp06). `range=all` (and a `to_date`-only custom window) resolves
> `cutoff=None` and stays a genuine unbounded fetch by design. The history cache
> is window-aware — a wider cached snapshot already covers any narrower
> sub-window — see [Concept: Store snapshot cache](../Concepts/store-snapshot-cache.md).

## Diagram

```mermaid
sequenceDiagram
    participant Client as HTMX (history.html)
    participant App as app.py:api_history
    participant Derive as derive.history
    participant Store as Store (store.py)
    participant BD as bd (list / status)

    Client->>App: GET /api/history?range&page&page_size&from_date&to_date
    App->>App: now = utcnow(); clamp range/page/page_size
    App->>Derive: resolve_history_bounds(range, from, to, now)
    Derive-->>App: (cutoff, ceiling)
    App->>Store: snapshot_history(closed_after=cutoff)
    Store->>BD: bd list --status closed --limit 0 [--closed-after cutoff] (cache-aware)
    BD-->>Store: closed beads (+ cached active)
    Store-->>App: beads[]
    App->>Derive: history_window / combined / throughput / created / lead_time_stats
    Derive-->>App: window, series, stats (pure, one snapshot)
    App->>Store: bd.status_summary()  %% optional headline (None ⇒ omit cells)
    Store->>BD: bd status --json (cached)
    BD-->>Store: summary | None
    Store-->>App: summary | None
    App-->>Client: 200 partials/history.html (+ OOB history_stats.html)
    Note over Client: swaps #history-region; HTMX peels OOB into #history-stats
```

## curl example

```sh
# 1) Default window (last 30 days), page 1, default page size 50.
curl -s "http://127.0.0.1:7332/api/history"

# 2) Last 7 days, second page of closed beads at 25 per page.
curl -s "http://127.0.0.1:7332/api/history?range=7d&page=2&page_size=25"

# 3) Unbounded "all time" view (genuine full-table read).
curl -s "http://127.0.0.1:7332/api/history?range=all"

# 4) Custom date window — supersedes range=, inclusive of both ends.
curl -s "http://127.0.0.1:7332/api/history?from_date=2026-05-01&to_date=2026-05-31"

# 5) Bad params degrade gracefully (range -> 30d, size -> 50): still 200 HTML.
curl -s "http://127.0.0.1:7332/api/history?range=bogus&page_size=999"
```

> [!IMPORTANT]
> The response is an HTML **fragment** meant to be swapped into `#history-region`
> by HTMX, not a standalone page — fetched directly it has no `<html>` chrome.
> The masthead KPI strip rides along as an `hx-swap-oob="true"` fragment in the
> same body; a raw `curl` will show it inline at the foot of the output.

## Testing

Route behaviour is covered by
[`tests/test_api_history.py`](../../tests/test_api_history.py), which invokes the
`api_history` coroutine directly with a minimal ASGI `Request` and a stubbed
`store.snapshot_history` so no real `bd` subprocess runs:

- **KPI strip** — `test_masthead_stats_present_foot_summary_absent` /
  `test_masthead_stats_degrade_without_bd_summary` assert the OOB stats fragment
  (`history-stats`, `hx-swap-oob="true"`, the four range labels) renders, and that
  the "via bd" totals degrade out when `status_summary()` returns `None`.
- **Chart a11y** — `test_throughput_bars_have_text_aria_labels` and
  `test_created_chart_renders_with_text_aria_labels` assert the bars are not
  colour-only (`role="img"`, "created,"/"closed on" labels, hatched created
  variant); `test_combined_chart_shows_per_day_counts_and_baseline_columns`
  guards the per-day count labels and baseline-anchored columns.
- **Closed list** — `test_closed_list_cards_open_bead_modal` (cards `hx-get`
  `/api/bead/{id}` into `#bead-modal`, surface `close_reason`).
- **Range control** — `test_range_control_mirrors_filter_badge_with_aria_pressed`,
  `test_bad_range_degrades_to_default`, `test_all_range_includes_old_beads`,
  `test_window_change_changes_returned_set` (the bdboard-li44 regression: each
  window re-derives a genuinely different set).
- **Pagination / page size** — `test_pagination_page_two_shows_newer_pager`,
  `test_beyond_end_page_is_graceful`, `test_all_range_pages_through_more_than_fifty_closed`
  (bdboard-a194: no hidden 50-cap), `test_default_page_size_is_fifty`,
  `test_page_size_25_limits_page_and_selector_reflects_it`,
  `test_invalid_page_size_degrades_to_fifty`,
  `test_pager_links_preserve_active_page_size`,
  `test_range_buttons_carry_active_page_size`.
- **Custom date window** — `test_custom_*` cases assert the popover semantics,
  that custom dates supersede the preset, echo back into the inputs, and that the
  pager preserves the window.
- **Filter-bounded fetch** (bdboard-gp06) — `test_narrow_range_pushes_lower_bound_to_fetch`,
  `test_all_range_keeps_fetch_unbounded`, `test_custom_window_pushes_from_date_lower_bound`,
  `test_custom_to_only_leaves_fetch_unbounded` assert the resolved `closed_after`
  is pushed down to `snapshot_history`.
- **Consistency** — `test_window_kpi_throughput_consistent_across_ranges` asserts
  the closed-list total, the "Closed (range)" KPI (`stats.n`), and the throughput
  series all reflect the same in-window set for every range (no off-by-one).

The thin page shell is covered separately by
[`tests/test_page_history.py`](../../tests/test_page_history.py); the bounded
snapshot read by [`tests/test_store_history_window.py`](../../tests/test_store_history_window.py)
and [`tests/test_bd_closed_history.py`](../../tests/test_bd_closed_history.py);
and the pure derivations by [`tests/test_derive_history.py`](../../tests/test_derive_history.py).

## Related

- [View: History page (`/history`)](../Views/history-page.md) — the page this endpoint fills (range control, chart, closed list, masthead stats).
- [Endpoint: Lanes API (`/api/lanes`, `/api/lanes/closed`, `/api/counts`)](lanes-api.md) — the symmetric read endpoint behind the board; same "thin route + derive + partial" shape.
- [Endpoint: Bead detail API (`/api/bead/{id}`, `/audit`, `/raw`)](bead-detail-api.md) — opened by clicking a closed-bead card.
- [Endpoint: SSE events (`/api/events`)](sse-events.md) — the stream whose `beads_changed` event triggers a `refresh` re-fetch of this region.
- [Concept: Derive layer (pure view shaping)](../Concepts/derive-layer.md) — where every clamp, bound, and series computation lives.
- [Concept: Store snapshot cache & change detection](../Concepts/store-snapshot-cache.md) — the window-aware history cache and the `--closed-after` pushdown.
- [Concept: bd CLI as runtime source of truth](../Concepts/bd-cli-source-of-truth.md) — why the data is a `bd list` / `bd status` snapshot, not a local DB.
- [Concept: HTMX + server-rendered partials](../Concepts/htmx-partials-architecture.md) — why the response is an HTML fragment (with an OOB sibling) swapped in place.
- [Architecture](../Architecture.md)
- [FlowDoc Authoring Guide](../_FlowDocGuide.md)
