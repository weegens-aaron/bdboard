# Feature: History & trends

## What it does

History & trends is bdboard's **retrospective / analytics** capability: a
dedicated page (`/history`) that answers *what got done, how fast, and at what
rate* over a selectable time window. Where the [board](../Views/board-page.md)
shows what is *in flight*, this feature surfaces three views of completed work
over a 7d / 30d / 90d / All range (default 30d) plus an optional custom from/to
date window: (1) headline **KPIs** — bd's workspace-global Total / Closed
all-time alongside range-scoped Avg lead, Closed-in-range, Median lead, and
Throughput/day; (2) a **"Created vs closed" grouped-bar chart** that pairs the
beads-filed and beads-closed counts per day on one continuous timeline so net
flow / backlog burn reads at a glance; and (3) a **paginated list of closed
beads**, newest-closed first, each card opening the shared bead modal. Every
surface is a *pure derivation over one `bd` snapshot* — no per-page or per-metric
subprocess — and every surface reacts live to the same SSE refresh pipeline the
rest of the dashboard uses.

## Why it exists

Throughput, lead time, and the closed backlog are exactly the numbers a
maintainer needs to reason about velocity and cycle time, but on the CLI those
answers are scattered across ad-hoc `bd list --status=closed` invocations and
hand-rolled date math. Surfacing them as a first-class, range-filterable page
turns "how are we trending?" into a single glance. Three concrete needs drive
the feature:

1. **Velocity & cycle-time at a glance.** Counting closures and computing lead /
   cycle times by hand is tedious and error-prone; the page derives them
   deterministically from the same snapshot the board already holds.
2. **Net-flow readability.** Closures alone don't tell you whether the backlog is
   growing or shrinking — you need *created vs closed* on one timeline. The
   combined grouped-bar chart makes burn-down/burn-up legible per day.
3. **Reachable long-tail history without blowing up memory.** The board's closed
   lane is intentionally count-capped (newest ~50); a retrospective surface must
   reach arbitrarily far back (`bdboard-a194`) *without* slurping the entire
   closed table on every render. The window's resolved lower bound is therefore
   pushed down into the `bd` query as `--closed-after` (`bdboard-gp06`), so a
   narrow range fetches only its beads while `All` stays a genuine unbounded read.

## How it works

### User perspective

The user opens `/history` and the page paints instantly with skeleton
placeholders, then the real region swaps in a beat later (lazy `hx-get` to
[`/api/history`](../Endpoints/history-api.md)). They can:

- **Switch the time window** — click a `7d` / `30d` / `90d` / `All` range badge;
  the whole region (chart, KPIs, list) re-renders for that window. `aria-pressed`
  marks the active range.
- **Pick a custom window** — open the **Custom** popover (a real
  `<form role="dialog">` with From/To `type="date"` inputs); the submitted dates
  *supersede* the preset for the chart, KPIs, *and* list. **Clear** returns to
  the last preset.
- **Page through closed beads** — Newer / Older pager and a per-page selector
  (25 / 50 / 100, persisted to `localStorage`).
- **Open a closed bead** — click any card to load its detail into the shared
  `#bead-modal`.
- **See live updates** — a bead closing anywhere (another tab, the CLI, an
  agent) re-renders the region automatically; the user never reloads.

### System perspective

The page route ([`page_history`](../../src/bdboard/app.py)) is deliberately
*data-free*: it runs the shared `_validate_or_warn()` workspace guard and renders
[`history.html`](../../src/bdboard/templates/history.html) with only `workspace`,
`workspace_path`, and `active="history"`. It **never** calls `bd`, so first paint
is instant. All real work happens in the lazy region fetch
([`api_history`](../../src/bdboard/app.py)):

1. **Resolve the window once.** From a single `now = datetime.now(UTC)`, the
   handler clamps `range` (unknown → `30d`), clamps `page` (`>= 1`) and
   `page_size` (to `{25,50,100}`, default 50 via
   [`derive.clamp_page_size`](../../src/bdboard/derive/history.py)), and resolves
   the `(cutoff, ceiling)` bounds via
   [`derive.resolve_history_bounds`](../../src/bdboard/derive/history.py) — the
   single source of truth that makes a custom from/to window supersede the preset.
2. **Bounded snapshot read.** It pushes the resolved `cutoff` down into
   [`store.snapshot_history(closed_after=cutoff)`](../../src/bdboard/store.py),
   which (cache-aware) shells
   [`bd.list_closed_history`](../../src/bdboard/bd.py)
   (`bd list --status closed --sort closed --no-pager --limit 0 [--closed-after <iso>]`)
   merged with the cached active beads — uncapped on count but bounded on window.
3. **Pure derivation over that one snapshot.** The handler computes the paginated
   closed list ([`history_window`](../../src/bdboard/derive/history.py)), the
   combined created+closed series ([`combined`](../../src/bdboard/derive/history.py)
   + `combined_peak`), the standalone `created` / `throughput` per-day tallies for
   the legend counts, and the lead/cycle-time KPIs
   ([`lead_time_stats`](../../src/bdboard/derive/history.py)).
4. **Optional global headline.** It also requests bd's own aggregate via
   [`store.bd.status_summary`](../../src/bdboard/bd.py) (`bd status --json`,
   cached); `None` on any hiccup simply omits the two global cells.
5. **One response, two surfaces.** It renders
   [`partials/history.html`](../../src/bdboard/templates/partials/history.html)
   into `#history-region` while an appended `hx-swap-oob` fragment
   ([`history_stats.html`](../../src/bdboard/templates/partials/history_stats.html))
   updates the masthead `#history-stats` KPI strip — in a single round-trip.

## Sequence

```mermaid
sequenceDiagram
    actor User
    participant Page as /history (page_history)
    participant HX as HTMX (#history-region)
    participant App as app.py:api_history
    participant Derive as derive.history
    participant Store as Store
    participant BD as bd (list / status)

    User->>Page: GET /history
    Page-->>User: shell + skeleton (no bd call)
    HX->>App: GET /api/history?range&page&page_size&from_date&to_date
    App->>App: now = utcnow(); clamp range/page/page_size
    App->>Derive: resolve_history_bounds(...) -> (cutoff, ceiling)
    App->>Store: snapshot_history(closed_after=cutoff)
    Store->>BD: bd list --status closed --limit 0 [--closed-after cutoff] (cache-aware)
    BD-->>Store: closed beads (+ cached active)
    Store-->>App: beads[]
    App->>Derive: history_window / combined / throughput / created / lead_time_stats
    Derive-->>App: window, series, stats (pure, one snapshot)
    App->>Store: bd.status_summary()  %% optional headline (None -> omit cells)
    Store->>BD: bd status --json (cached)
    BD-->>Store: summary | None
    App-->>HX: 200 partials/history.html (+ OOB history_stats.html)
    Note over User,HX: HTMX swaps #history-region and peels the OOB strip into #history-stats.<br/>A later SSE "beads_changed" event re-fires this same fetch.
```

## Implementation Map

| Concern | Where | Notes |
| --- | --- | --- |
| Page route (shell only) | [`src/bdboard/app.py:page_history`](../../src/bdboard/app.py) → [`templates/history.html`](../../src/bdboard/templates/history.html) | Workspace guard + render; holds no data, never calls `bd`. |
| Region handler | [`src/bdboard/app.py:api_history`](../../src/bdboard/app.py) | Thin route: resolve window, one snapshot, pure derive, render partial + OOB strip. |
| Window resolution (single source of truth) | [`derive.resolve_history_bounds`](../../src/bdboard/derive/history.py) (`custom_bounds`, `_range_to_cutoff`, `_resolve_bounds`) | Custom from/to supersedes the preset; `(cutoff, ceiling)` shared by fetch + every slice. |
| Range / page-size constants | [`derive.HISTORY_RANGES`](../../src/bdboard/derive/history.py), `DEFAULT_HISTORY_RANGE`, `HISTORY_PAGE_SIZES`, `clamp_page_size` | `7d/30d/90d/all`; `{25,50,100}` default 50. |
| Bounded snapshot read | [`store.snapshot_history(closed_after)`](../../src/bdboard/store.py) → [`bd.list_closed_history`](../../src/bdboard/bd.py) | Count-uncapped, window-bounded; window-aware history cache (`_history_covers`). |
| Paginated closed list | [`derive.history_window`](../../src/bdboard/derive/history.py) | `{items, page, page_size, total, has_more}`; in-memory slice, no per-page I/O. |
| Combined chart series | [`derive.combined`](../../src/bdboard/derive/history.py) (+ `combined_peak`) | created+closed zipped onto one gap-free timeline; shared y-peak. |
| Per-day legend tallies | [`derive.throughput`](../../src/bdboard/derive/history.py), [`derive.created`](../../src/bdboard/derive/history.py) | `partial`s of one `_daily_count_series` pipeline (closed-at / created-at). |
| Lead / cycle-time KPIs | [`derive.lead_time_stats`](../../src/bdboard/derive/history.py) | median/p90 lead (created→closed) + median/p90/avg cycle (started→closed). |
| Workspace-global headline | [`store.bd.status_summary`](../../src/bdboard/bd.py) (`bd status --json`, cached) | Optional Total / Closed all-time; `None` ⇒ cells omitted. |
| Per-bead status timeline | [`derive.status_timeline`](../../src/bdboard/derive/history.py) (used by [`app.py`](../../src/bdboard/app.py) audit view) | The per-bead trend sibling: collapses `bd history <id>` snapshots to status transitions + dwell time; reuses the audit fetch (no extra subprocess). |
| Region template | [`partials/history.html`](../../src/bdboard/templates/partials/history.html) | Range toolbar + Custom popover, combined chart, paginated list + pager + size selector. |
| OOB KPI strip | [`partials/history_stats.html`](../../src/bdboard/templates/partials/history_stats.html) (`hx-swap-oob="true"` → masthead `#history-stats`) | Range KPIs + optional "via bd" totals, per-cell info popovers. |
| Skeletons (no flash-empty) | [`partials/history_skeleton.html`](../../src/bdboard/templates/partials/history_skeleton.html), [`partials/counts_skeleton.html`](../../src/bdboard/templates/partials/counts_skeleton.html) | First-paint shimmer for region + stats host. |
| Closed card | [`partials/bead_card.html`](../../src/bdboard/templates/partials/bead_card.html) (`meta="history"`) | Opens `/api/bead/{id}` in `#bead-modal`. |
| Client wiring | [`templates/base.html`](../../src/bdboard/templates/base.html) | SSE → `refresh`, page-size persistence, active-window re-injection on bare refresh, Custom-popover JS. |

## Config

| Name | Where | Default | Effect |
| --- | --- | --- | --- |
| `range` (query) | [`api_history`](../../src/bdboard/app.py) / [`HISTORY_RANGES`](../../src/bdboard/derive/history.py) | `30d` (`DEFAULT_HISTORY_RANGE`) | Selects the window (`7d`/`30d`/`90d`/`all`); unknown/empty degrades to default. |
| `page` (query) | [`api_history`](../../src/bdboard/app.py) | `1` | Closed-list page; clamped `>= 1`; past-end renders a graceful empty state. |
| `page_size` (query) | [`derive.clamp_page_size`](../../src/bdboard/derive/history.py) | `50` (`HISTORY_PAGE_SIZE`) | Per-page size; clamped to `HISTORY_PAGE_SIZES = {25,50,100}`, else `50`. |
| `from_date` / `to_date` (query) | [`derive.custom_bounds`](../../src/bdboard/derive/history.py) | `None` | `YYYY-MM-DD` custom window; inclusive lower / exclusive next-day-ceiling; supersedes `range=`. |
| `bdboard-history-page-size` (localStorage) | [`base.html`](../../src/bdboard/templates/base.html) | unset → `50` | Persists the chosen page size across reloads/SSE refreshes; re-injected onto bare `/api/history` fetches. |

> [!IMPORTANT]
> The window is resolved **once** from a single `now`, and that same
> `(cutoff, ceiling)` drives both the server-side `--closed-after` fetch bound and
> every in-memory derive slice. This single-resolver discipline is what guarantees
> the chart, the KPIs, and the closed list all agree on the exact same window with
> no off-by-one drift (`bdboard-gp06`). Never re-derive the bound separately per
> metric.

## Edge Cases

> [!WARNING]
> - **Two KPI scopes that look alike.** *Total* and *Closed (all time)* come from
>   bd's workspace-global `status_summary()` and do **not** react to the range
>   control; *Avg lead*, *Closed (range)*, *Median lead*, and *Throughput* are
>   range-scoped derivations. Each cell carries an info-icon popover spelling out
>   the scope so the two are never conflated.
> - **No static count cap.** History is uncapped on count (`--limit 0`) precisely
>   so the long tail stays reachable; a fixed cap would silently truncate to the
>   newest N closures (`bdboard-a194`). It is bounded only by the *window*.
> - **`all` and `to_date`-only windows stay unbounded.** `range=all` resolves
>   `cutoff=None`, a genuine full-table read; a custom window with only a `to_date`
>   (no `from_date`) also resolves `cutoff=None` — the user explicitly chose no
>   lower bound.
> - **Inverted custom dates are swapped, not collapsed.** A `from` later than `to`
>   is reordered so the window stays meaningful instead of yielding an empty set.
> - **`to_date` is inclusive of its whole day.** The ceiling is the *exclusive*
>   start-of-next-day, so `to_date=2026-05-30` includes everything stamped on the
>   30th.
> - **Beads with no parseable timestamp are excluded** from the relevant series:
>   no `closed_at` ⇒ off the closed list / throughput; no `created_at` ⇒ off the
>   created series; no `started_at` ⇒ off the cycle-time metrics. They can't be
>   placed on a timeline.
> - **Negative/zero durations are dropped** from lead/cycle stats (clock skew or
>   odd data) so a single bad row can't poison the medians.
> - **Live refresh hits a bare `/api/history`.** The SSE re-fetch carries no query
>   params, so `base.html` reads the active range/custom window + persisted page
>   size from the live DOM and re-injects them — otherwise a live refresh would
>   snap back to the 30d default (`bdboard-li44`).

> [!CAUTION]
> Do **not** add per-param `4xx` validation to `/api/history` "to be strict." The
> contract is graceful degradation: a tampered/stale query string (from a
> bookmark, an SSE refresh, or a hand-edited URL) must always paint *something*
> useful, never a broken HTMX swap target. Every clamp lives in the
> [derive layer](../Concepts/derive-layer.md) precisely so the endpoint stays a
> thin, total function.

## Error Scenarios

| What fails | What the user sees | How the system degrades |
| --- | --- | --- |
| Bad `range` / out-of-range `page` / invalid `page_size` / unparseable date | A correctly-rendered region for the safe default (`30d` / "Nothing on page N" / size 50 / "no bound") | Every param degrades in the derive layer; the endpoint **never** error-statuses on input — always `200` HTML. |
| `bd list` snapshot fetch fails | The previous snapshot keeps rendering (no flash-empty) | [`store`](../Concepts/store-snapshot-cache.md) leaves the existing cache in place — better stale than empty. |
| `bd status` (`status_summary`) fails / returns malformed JSON | The "via bd" Total / Closed all-time cells vanish | `status_summary()` returns `None`; the range-derived KPIs remain the primary surface. |
| Workspace invalid at page load | [`error.html`](../../src/bdboard/templates/error.html) with HTTP `500` | `page_history` runs `_validate_or_warn()` so a broken workspace fails *visibly* rather than painting an empty page. |
| Empty window (nothing created or closed) | "No beads created or closed to chart in …" + an empty-list message | The chart and list render explicit empty states rather than blank space. |

## Testing

The handler, the bounded fetch, and the pure derivations are each tested in
isolation (no real `bd` subprocess — `store.snapshot_history` is stubbed):

- [`tests/test_api_history.py`](../../tests/test_api_history.py) — the route
  end-to-end: KPI strip presence + `status_summary=None` degradation, chart a11y
  (`role="img"`, text `aria-label`s, hatched created variant, per-day counts),
  closed-list cards opening the modal, range control (`aria-pressed`,
  bad-range→default, `all` includes old beads, each window re-derives a genuinely
  different set — `bdboard-li44`), pagination / page-size clamping
  (`bdboard-a194` no hidden 50-cap), custom date-window precedence + popover echo,
  the `--closed-after` pushdown (`bdboard-gp06`), and KPI/throughput/list
  cross-consistency for every range.
- [`tests/test_derive_history.py`](../../tests/test_derive_history.py) — the pure
  functions: `resolve_history_bounds` / `custom_bounds` precedence, window
  filtering, gap-free day-fill, `combined` alignment, percentile / lead / cycle
  math, and `status_timeline` transitions + dwell.
- [`tests/test_store_history_window.py`](../../tests/test_store_history_window.py)
  — the window-aware history cache (`_history_covers`) and bounded re-fetch.
- [`tests/test_bd_closed_history.py`](../../tests/test_bd_closed_history.py) — the
  count-uncapped `--limit 0` fetch and the `--closed-after` flag wiring.
- [`tests/test_bd_status_summary.py`](../../tests/test_bd_status_summary.py) — the
  optional headline summary parse + `None`-on-hiccup behaviour.
- [`tests/test_page_history.py`](../../tests/test_page_history.py) — the thin page
  shell (no `bd` call, workspace-guard `500`).
- [`tests/test_created_bar_contrast.py`](../../tests/test_created_bar_contrast.py)
  — WCAG contrast of the created-vs-closed bars.

## Related

- [View: History page (`/history`)](../Views/history-page.md) — the page surface this feature presents: chrome, page structure, components, and user actions.
- [Endpoint: History API (`/api/history`)](../Endpoints/history-api.md) — the single read endpoint behind the feature; request/response contract, params, and degradation rules.
- [Endpoint: Bead detail API (`/api/bead/{id}`, `/audit`, `/raw`)](../Endpoints/bead-detail-api.md) — opened by clicking a closed-bead card; also hosts the per-bead status timeline.
- [Endpoint: SSE events (`/api/events`)](../Endpoints/sse-events.md) — the stream whose `beads_changed` event re-fetches the history region live.
- [Feature: Live auto-refresh](live-auto-refresh.md) — the broadcast → re-fetch machinery that keeps this feature's region live.
- [Flow: Live-refresh pipeline](../Flows/live-refresh-pipeline.md) — the end-to-end refresh mechanics this feature rides on.
- [Concept: Derive layer (pure view shaping)](../Concepts/derive-layer.md) — where every bound, clamp, series, and KPI computation lives.
- [Concept: Store snapshot cache & change detection](../Concepts/store-snapshot-cache.md) — the window-aware history cache and the `--closed-after` pushdown.
- [Concept: bd CLI as runtime source of truth](../Concepts/bd-cli-source-of-truth.md) — why the data is a `bd list` / `bd status` snapshot, not a local DB.
- [Concept: HTMX + server-rendered partials](../Concepts/htmx-partials-architecture.md) — why the page is a thin shell + lazy region fetch with an OOB sibling.
- [View: Board page (`/`)](../Views/board-page.md) — the in-flight counterpart whose chrome this page mirrors.
- [Architecture](../Architecture.md)
- [FlowDoc Authoring Guide](../_FlowDocGuide.md)
