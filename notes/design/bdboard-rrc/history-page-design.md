# Design: History page for deep-dive retrospective analysis

- **Bead:** bdboard-rrc (design)
- **Epic:** bdboard-fo6 — History Page: deep-dive retrospective analysis of bead activity
- **Status:** design / spec only — **no implementation in this bead**
- **Date:** 2026-05-29

> This document is the deliverable for bdboard-rrc. It defines scope, the
> data contract (with a spike that resolves the epic's data-source
> question), the design decisions, and a breakdown into child
> implementation beads for the epic. It deliberately ships **no** runtime
> code.

---

## 1. Problem & goal

The board's lane filter strips intentionally cap at short windows
(**12h / 1d / 3d**, unified in bdboard-ah3) and the Closed lane is capped
at `CLOSED_LANE_LIMIT = 50` (see `derive.py`). That is a deliberate choice:
the board is a *recent-activity* surface and should stay focused.

The cost of that focus is that there is **no way to do retrospective
analysis** from bdboard:

- What closed last week / last month / last quarter?
- Throughput over time (closed beads per day/week).
- Lead time (created → closed, or started → closed) and how it trends.
- Churn / activity over a long, arbitrary window.
- A scrollable list of *all* closed work, not just the most recent 50.

**Goal:** a dedicated **History page** — the long-window complement to the
board — that surfaces (a) a long/arbitrary-range list of historical bead
activity and (b) at least one meaningful aggregation beyond a raw list
(throughput), with the data-source question resolved and the work broken
into deterministic child beads.

This bead is **design only**. No routes, templates, or derive functions
are added here.

---

## 2. Spike: where does long-window history come from? (CONFIRMED)

This is the epic's central open question ("confirm whether bd CLI exposes
the needed history … or whether a snapshot/persistence mechanism is
required"). It was exercised by hand against the installed `bd`
(`bd 1.0.x`) and this workspace (60 beads, 58 closed).

### 2.1 `bd list --all --json` already carries the timestamps we need ✅

The existing `BdClient.list_all()` call —
`bd list --all --no-pager --limit 0 --json` — returns **every** bead
(open + closed, unlimited) and each bead dict includes the full timestamp
set:

| Field | Meaning | Powers |
| --- | --- | --- |
| `created_at` | When the bead was filed | "created" events, backlog-age |
| `started_at` | First transition to `in_progress` | lead time (started→closed) |
| `updated_at` | Last mutation | churn / activity recency |
| `closed_at` | When it was closed | **throughput, closed-window list** |
| `close_reason` | Why it closed | context in the closed list |

Confirmed sample (real bead from this workspace):

```json
{
  "id": "bdboard-awc",
  "created_at": "2026-05-29T12:33:42Z",
  "started_at": "2026-05-29T12:35:03Z",
  "updated_at": "2026-05-29T12:41:55Z",
  "closed_at": "2026-05-29T12:41:55Z",
  "status": "closed"
}
```

**Headline finding:** everything needed for v1 (long-window closed list +
throughput + lead time) is **already in the snapshot bdboard fetches on
every refresh**. The History page can be built as a *pure derivation*
(`derive.py` style) over `store.snapshot()` — **no new bd call, no
snapshot/persistence layer, no Dolt access** is required for v1.

This is the opposite of the Memory-view spike (bdboard-5p1 §2.2), where the
required field genuinely did not exist in the CLI contract. Here it does.

### 2.2 What `bd history <id>` is — and why it is NOT the source

`bd history <id> --json` exists but is **per-bead**: it returns one full
issue snapshot **per Dolt commit** for a single bead (used today by the
bead-detail audit view via `BdClient.history()`). It is:

- **Not a global feed.** There is no `bd history` (all-beads) command.
- **Expensive at scale.** Building a cross-bead timeline this way would be
  N subprocess calls (one per bead), each returning the full snapshot
  history — exactly the kind of fan-out the `_subprocess_gate`
  semaphore (single concurrent bd call) makes slow.

So `bd history` is **out of scope as the primary source.** It remains
available for a *future* per-bead "status-transition timeline" enrichment
(see §6, deferred bead E) — but v1 does not need it.

### 2.3 Other CLI surfaces evaluated

| Command | Verdict |
| --- | --- |
| `bd status --json` | Returns an aggregate `summary` (`closed_issues`, `in_progress_issues`, `average_lead_time_hours`, `total_issues`, …). Useful as a **headline KPI strip**, but it is point-in-time totals, not a time series. Optional enhancement, not required. |
| `bd query "closed>30d" --all --json` | Supports **date-relative filters** (`7d`, `2w`, absolute dates, natural language) and server-side sort. Could power range queries, but it would be a *second* data path alongside `list_all`. **Decision: derive client-side from the single `list_all` snapshot** (§3, D1) to avoid a divergent second source. `bd query` is noted as a fallback if snapshot size ever becomes a problem. |
| `dolt sql` direct | Rejected for the same reason as the Memory spike: it bypasses bdboard's "bd CLI JSON is the runtime source of truth" principle and couples to bd's internal schema. |

### 2.4 Spike conclusion

> **No snapshot/persistence mechanism is required for v1.** The History
> page is a pure derivation over the existing `list_all` snapshot, which
> already carries `created_at` / `started_at` / `updated_at` /
> `closed_at` / `close_reason` for every bead. This directly answers the
> epic's data-source success criterion.

---

## 3. Design decisions

### D1 — Derive client-side from the existing snapshot (DECIDED)

The History page derives entirely from `store.snapshot()` (the same
`list_all` data the board uses) via **new pure functions in `derive.py`**.
No new `BdClient` method, no new bd subprocess, no persistence.

Rationale: single source of truth, zero new I/O, inherits the Store's
freshness/caching/SSE pipeline for free, and matches the established
`derive.py` pattern (`lanes`, `activity`, `counts`). YAGNI on a snapshot
store until a real need (e.g. wanting history that predates the current
Dolt-compacted state) appears.

### D2 — Aggregation: throughput (closed/day) is the v1 must-have (DECIDED)

The epic requires "at least one meaningful aggregation beyond a raw list."
v1 ships **throughput: count of beads closed per day** over the selected
window, rendered as a small bar/spark series. It is computed by bucketing
`closed_at` by calendar day (workspace-local or UTC — see D6).

**Lead time** (created→closed and started→closed, median + p90) is a
second, low-cost aggregation computed from the same fields; it is included
in v1 as a headline stat row because the fields are right there (D2a).
**Churn** (updates over time) is deferred (§6) — it needs `updated_at`
bucketing plus a clear definition and is not required for the epic's
single-aggregation bar.

### D3 — Time-range control: presets + "all" (DECIDED)

A range selector offers windows **beyond** the board's 12h/1d/3d:
**7d / 30d / 90d / All**. "All" is the unbounded view the epic explicitly
calls for. The control mirrors the board's existing `filter-badge` pattern
(see `lanes.html`) for visual + a11y consistency (same button semantics,
same `aria-label` style, same active-state cues). Default: **30d**.

Range filtering is applied to the **closed list and throughput** by
`closed_at`; the activity/churn views (when added) filter by `updated_at`.

### D4 — Navigation: dedicated route + masthead nav entry (DECIDED)

- New full-page route **`GET /history`** → `history.html` (extends
  `base.html`), symmetric with `/` and `/memory`.
- New partial route **`GET /api/history?range=<7d|30d|90d|all>`** → the
  list+throughput region (HTMX swap target), symmetric with `/api/lanes`
  and `/api/memory`.
- A **third nav entry** ("History") added to `partials/nav.html`
  alongside Board / Memory. `active="history"` drives the `is-active`
  styling + `aria-current="page"` exactly like the existing entries — the
  nav chrome stays DRY in one partial.

### D5 — Large result sets handled gracefully (DECIDED)

The epic requires graceful handling of large result sets (the whole point
is escaping the board's 50-cap). v1 strategy:

- **Throughput** is an aggregate → always cheap regardless of N.
- **Closed list** under "All" can be large. v1 uses **server-side
  pagination** on `/api/history` (page size ~100, default sort
  `closed_at` desc) with an HTMX "load more" / page control. Pagination
  (not virtualization) is chosen because it fits the existing
  partial-swap architecture with no client-side framework and degrades
  gracefully without JS.
- The derivation operates on the already-in-memory snapshot (no extra I/O
  per page); paging is a slice over the pre-sorted derived list.

### D6 — Day bucketing timezone (DECIDED: workspace-local, documented)

Throughput "per day" buckets `closed_at` by **the server's local
calendar day** so a user's "today" lines up with their wall clock. This
is documented because UTC bucketing would split a working day awkwardly
across the date line. The choice is a single helper in `derive.py`
(`_day_bucket`) so it is testable and swappable. `humanize_ts` /
`_epoch` in `derive.py` already establish the tz-aware parsing pattern to
reuse.

### D7 — Live refresh: inherit, don't reinvent (DECIDED)

The History page is read-only over the same snapshot the board watches,
so it **reuses the existing SSE pipeline**: when `.beads/` changes, the
page can re-fetch `/api/history` exactly as the board re-fetches
`/api/lanes`. No new watcher, no new event type. (A bead that closes
while you're looking at History should make it appear — for free.)

---

## 4. Data flow & architecture fit

```
Browser ──GET /history──────────────► app.py: page_history()
                                          └─ renders history.html (base)
Browser ──GET /api/history?range=&page=► app.py: api_history()
                                          └─ store.snapshot()          (existing)
                                          └─ derive.history_window(...) (NEW pure fn)
                                          └─ derive.throughput(...)     (NEW pure fn)
                                          └─ derive.lead_time_stats(...)(NEW pure fn)
                                          └─ render partials/history.html
```

- **No new `BdClient` method.** Reuses `store.snapshot()`.
- **New pure functions in `derive.py`** (mirrors `lanes`/`activity`):
  - `history_window(beads, range, page, page_size) -> {items, page, has_more, total}`
    — closed beads within `range`, sorted `closed_at` desc, sliced.
  - `throughput(beads, range) -> list[{day, count}]` — closed-per-day buckets.
  - `lead_time_stats(beads, range) -> {median_h, p90_h, n}` — created/started→closed.
  - small helpers: `_day_bucket(ts)`, `_range_to_cutoff(range)`.
- **Reuse** existing `humanize_ts` for relative timestamps and the
  `filter-badge` CSS for the range control. No new dependencies; pure
  FastAPI + HTMX + a tiny inline CSS bar strip for throughput — no
  Chart.js needed for a single sparkline-style strip, keeping the page
  dependency-free and consistent with the current stack.

---

## 5. UI / UX spec (v1)

- **Layout:** full page at `/history`, masthead consistent with board +
  memory (workspace title, nav with the new **History** entry active,
  theme toggle).
- **Range control:** `filter-badge`-style buttons **7d / 30d / 90d /
  All**, default 30d, each with an `aria-label` (e.g. "Show history for
  the last 30 days"). Mirrors the board's closed-lane filter idiom.
- **KPI strip (top):** small editorial stat cells (reusing the counts
  strip treatment) — **closed in range**, **median lead time**,
  **throughput/day avg**. Echoed as a one-line summary at the bottom too,
  per the reports convention.
- **Throughput chart:** a day-bucketed bar/spark strip in a
  **fixed-height container** (so it can't collapse), with each bar
  labelled for screen readers (`N closed on <date>`).
- **History list:** vertical list of closed beads, each card showing id,
  priority badge, title, `closed_at` (humanized + absolute on hover),
  `close_reason`, and assignee. Clicking opens the existing bead modal
  (`hx-get="/api/bead/{id}"`) — reuse, don't rebuild.
- **Pagination:** "Load more" / page control at the list foot
  (server-side, D5).
- **Empty states:**
  - No closed beads in range → "Nothing closed in the last 30 days —
    try a wider range."
  - Empty workspace → friendly pointer like the other surfaces.
- **Accessibility (WCAG 2.2 AA):**
  - Range buttons: same non-colour active cues as existing filter badges;
    programmatic labels; `aria-pressed`/`aria-current` as appropriate.
  - KPI + result count in an `aria-live="polite"` region so range changes
    are announced.
  - Throughput bars are **not colour-only**: each carries a text label /
    `aria-label`; the chart has an accessible name and a data summary.
  - List is list semantics (`role="list"` / `<li>`); all colours reuse
    the vetted token palette (4.5:1 text / 3:1 UI), matching the existing
    filter-badge contrast tests.

---

## 6. Child bead breakdown (for the epic)

Implementation beads to be filed under bdboard-fo6 (this design is the
canonical plan). Dependency-wire so `bd ready` surfaces A first.

| Bead | Title | Scope | Depends on |
| --- | --- | --- | --- |
| **A** | `derive.py` history functions + tests | `history_window`, `throughput`, `lead_time_stats`, `_day_bucket`, `_range_to_cutoff`; unit-test buckets/ranges/edge cases (no closed_at, tz boundaries, empty). | — |
| **B** | `/api/history` partial + `partials/history.html` | KPI strip, throughput chart, paginated closed list, range + page params, empty states. | A |
| **C** | `/history` full page + nav entry | `history.html` extends `base.html`; add **History** entry to `partials/nav.html` (`active="history"`); SSE re-fetch wiring (D7). | B |
| **D** *(deferred)* | Churn / activity-over-time view | `updated_at`-bucketed churn aggregation + view; needs a churn definition. | A |
| **E** *(deferred)* | Per-bead status-transition timeline | Optional enrichment using `bd history <id>` for one bead's lifecycle, opened from the modal. | — |
| **F** *(optional)* | KPI from `bd status --json` | Wire the aggregate summary (incl. `average_lead_time_hours`) as a headline if we prefer bd's numbers over client-derived ones. | B |

Acceptance mapping to the epic's Success Criteria:

- "analyze history over arbitrary/long ranges incl. unbounded 'all'" → D3 range control + A `history_window` (B/C surface it).
- "at least one meaningful aggregation beyond a raw list" → **D2 throughput** (A `throughput`, B renders it); lead time as a bonus.
- "data-source question resolved (CLI vs snapshot/persistence; spike if unknown)" → **§2 (RESOLVED: pure derivation over the existing `list_all` snapshot; no persistence needed)**.
- "reachable via clear navigation (route + nav entry)" → D4 (C).
- "large result sets handled gracefully (pagination or virtualization)" → **D5 server-side pagination** (A slicing + B control).

---

## 7. Out of scope for this bead

- Any runtime/template/route code (this is a design bead).
- Churn-over-time view (deferred to bead D — needs a churn definition).
- Per-bead status-transition timeline (deferred to bead E; would use
  `bd history <id>`).
- A snapshot/persistence layer — explicitly **not needed** for v1
  (§2.4); only revisit if a future requirement needs history predating
  the current Dolt-compacted state.
- Chart.js or any charting dependency — v1 uses a CSS bar strip.
