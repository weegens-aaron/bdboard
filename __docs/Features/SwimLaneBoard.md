# Swim-lane Board

## What It Does

The board at `/` arranges every in-flight bead into a horizontal **Epics**
strip plus five status swim lanes — **Deferred / Blocked / Ready / In Progress /
Closed** — alongside a synthesized **Activity** feed, all rendered from the live
`bd` store and kept current as the workspace changes underneath you.

## Why It Exists

`bd ready` / `bd list` answer "what can I work on?" one terminal query at a time;
they don't give you the *shape* of the whole queue at a glance. The swim-lane
board is bdboard's answer to "show me everything, bucketed by what I'd do with
it, newest-and-highest-priority first" without anyone hand-maintaining a kanban:

- **Lanes are derived, not stored.** A bead's lane is a *pure function* of its
  status and its (unmet) blocking dependencies — there is no "lane" field in
  `bd`, no drag-to-move, nothing to keep in sync. `derive.lanes` re-buckets the
  snapshot on every render, so the board can never drift from the source of
  truth. The same applies to the Epics strip (`derive.epic_lane`), the Activity
  feed (`derive.activity`), and the masthead counts (`derive.counts`).
- **"Functionally blocked" beats "literally blocked."** An `open` bead whose
  `blocks`/`blocked-by` target isn't closed yet is shown in **Blocked**, not
  Ready — so the Ready lane is genuinely "pick the top card and go," and you
  never claim work that's secretly waiting on something.
- **Recent-activity surface, not an archive.** The board is the *short-window*
  view: its Closed lane is date-bounded (`BOARD_CLOSED_WINDOW_DAYS = 3`) at
  fetch time and narrowed further by a client-side 12h/1d/3d filter. Anything
  older lives on the [History page](../Views/HistoryPage.md). This deliberate
  split keeps the header CLOSED KPI and the Closed-lane count counting the *same
  set* (bdboard-p8v).
- **Fast first paint, heavy parts deferred.** The active lanes derive from an
  active-only snapshot (~5KB); the heavy Closed lane (~495KB on big workspaces)
  lazy-loads via a nested fetch *after* the active lanes paint — a ~100x TTFP
  win (bdboard-0yy).

It reuses the same `bd`-as-source-of-truth, snapshot-cache, pure-derive,
HTMX-partial, and SSE live-refresh machinery as the rest of the app — the board
is "just" four derivations rendered into one swap region.

## How It Works

### User Perspective

- **Open the board.** `GET /` paints an instant shell: a two-row masthead (a
  counts-strip skeleton up top; nav + theme toggle + **+ Pour Formula** below),
  a 12h/1d/3d board toolbar, and a full lane skeleton. No blank screen.
- **Watch it hydrate.** The masthead counts swap in from `/api/counts`; the
  Epics strip + Deferred/Blocked/Ready/In Progress lanes + Activity feed swap in
  from `/api/lanes`; then the heavy **Closed** lane fills from a nested
  `/api/lanes/closed` fetch.
- **Read the lanes.** Epics render as a horizontal, dependency-ordered chain of
  chips (each with a status icon + label). Active lanes are sorted **priority
  ascending (P0 first), then most-recently-updated**. The Closed lane is sorted
  **most-recently-closed first**.
- **Filter by recency.** Click `12h` / `1d` / `3d`; the choice (default `1d`)
  shows/hides Closed cards by their `data-closed-at` age **client-side**, updates
  the lane's count badge, and re-syncs the masthead CLOSED cell — no server
  round-trip.
- **Open any bead.** Click an epic chip, a lane card, or an Activity row — all
  fire `hx-get="/api/bead/{id}"` into the shared `#bead-modal`.
- **Pour a formula.** **+ Pour Formula** opens a two-step `<dialog>` (pick →
  fill variables → pour); new beads arrive live.
- **It stays live.** Any `.beads/` change broadcasts an SSE `beads_changed`
  pulse → `refresh from:body`, re-fetching counts + lanes + closed lane so a
  bead changing state appears without a reload.

### System Perspective

`GET /` (`index`) validates the workspace and returns `dashboard.html` (extends
`base.html`) with skeletons — it **never blocks on a `bd` subprocess**. Three
read-only HTMX targets then hydrate it. `api_counts` derives `derive.counts`
over the full `store.snapshot()` (active + board-closed). `api_lanes` fetches the
**active-only** `store.snapshot_active()`, runs `_hydrate_epic_dependencies` (a
concurrent per-epic `bd show --long` pass so wired epic chains can be sequenced),
then renders `partials/lanes.html` from `derive.epic_lane` / `derive.lanes` /
`derive.activity`. `api_lanes_closed` fetches the date-bounded
`store.snapshot_closed()` and renders `partials/closed_lane.html` into the
lazy `.lane-closed` placeholder. All three are pure derivations over snapshots
the `Store` already holds, return **HTML fragments**, and are wired
`hx-trigger="load, refresh from:body"` so they hydrate once and re-fetch on every
SSE pulse.

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant V as dashboard.html / .lanes-region
    participant Rc as api_counts (app.py)
    participant Rl as api_lanes (app.py)
    participant Rcl as api_lanes_closed (app.py)
    participant St as Store (snapshot cache)
    participant BD as BdClient (bd.py)
    participant D as derive.lanes (counts/epic_lane/lanes/activity)
    participant Bus as bus.broadcast (SSE)

    U->>V: GET / (index)
    V->>V: paint counts_skeleton + lanes_skeleton (no bd call)

    V->>Rc: GET /api/counts (hx-trigger="load")
    Rc->>St: snapshot() (active + board-closed)
    St->>BD: list_active() + list_closed() (lazy, cached)
    BD-->>St: beads
    Rc->>D: counts(beads)
    Rc-->>V: partials/counts.html (swap #counts)

    V->>Rl: GET /api/lanes (hx-trigger="load")
    Rl->>St: snapshot_active() (~5KB)
    St-->>Rl: active beads
    Rl->>BD: _hydrate_epic_dependencies -> per-epic bd show --long (concurrent)
    Rl->>D: epic_lane / lanes / activity
    Rl-->>V: partials/lanes.html (swap .lanes-region; .lane-closed = placeholder)

    V->>Rcl: GET /api/lanes/closed (nested hx-trigger="load")
    Rcl->>St: snapshot_closed() (date-bounded)
    St-->>Rcl: closed beads
    Rcl-->>V: partials/closed_lane.html (swap .lane-closed)
    V->>V: applyBoardFilter() narrows Closed cards + syncs masthead CLOSED

    Note over Bus,V: a .beads/ change -> SSE beads_changed
    Bus-->>V: refresh from:body
    V->>Rc: GET /api/counts
    V->>Rl: GET /api/lanes
    V->>Rcl: GET /api/lanes/closed
```

## Key Data Shapes

The feature is HTML-fragment out on the wire (no JSON responses), but these
internal shapes carry it. Real field names below.

A **raw active bead** (an element of `store.snapshot_active()`, from
`bd list --no-pager --limit 0`) — what `derive.lanes` buckets and the card
renders from:

```json
{
  "id": "bdboard-mol-bfs.1",
  "title": "FlowDoc maintainer: Feature: Swim-lane board",
  "issue_type": "task",
  "status": "in_progress",
  "priority": 2,
  "assignee": "Aaron Weegens",
  "created_by": "Aaron Weegens",
  "created_at": "2026-06-04T09:00:00Z",
  "updated_at": "2026-06-04T10:24:56Z",
  "closed_at": null,
  "close_reason": null,
  "parent": "bdboard-mol-bfs",
  "dependency_count": 0,
  "dependencies": []
}
```

A **dependency edge** as read by `_has_unmet_blocking_dep` (field names are
normalized — `deps` or `dependencies`; `type` or `dependency_type`;
`depends_on_id` / `target` / `id` / `dependsOnId`):

```json
{
  "dependency_type": "blocked-by",
  "depends_on_id": "bdboard-mol-bfs"
}
```

The **`derive.lanes` return** — the bucket map `partials/lanes.html` renders
(the `closed` bucket is empty on the active-only `/api/lanes` path; the Closed
lane is filled separately by `/api/lanes/closed`):

```json
{
  "deferred": [],
  "ready": [ { "id": "…", "title": "…", "priority": 0, "status": "open", "updated_at": "…" } ],
  "in_progress": [ { "id": "…", "status": "in_progress" } ],
  "blocked": [ { "id": "…", "status": "blocked" } ],
  "closed": []
}
```

An **`derive.epic_lane` element** — an epic chip, enriched with the derived
display status (`status_key`/`status_icon`/`status_label`; an `open` epic with an
unmet blocker is surfaced as `blocked`):

```json
{
  "id": "bdboard-mol-bfs",
  "title": "FlowDoc maintainer: discover & scaffold …",
  "issue_type": "epic",
  "status": "in_progress",
  "priority": 1,
  "assignee": "Aaron Weegens",
  "status_key": "in_progress",
  "status_icon": "▶",
  "status_label": "In Progress"
}
```

An **`derive.activity` element** (synthesized "current state as event", newest
first — bd exposes no cross-bead audit feed):

```json
{
  "id": "bdboard-mol-bfs.1",
  "title": "FlowDoc maintainer: Feature: Swim-lane board",
  "actor": "Aaron Weegens",
  "verb": "in progress",
  "ts": "2026-06-04T10:24:56Z",
  "ts_epoch": 1780999496.0,
  "priority": 2
}
```

The **`derive.counts` return** — the masthead KPI strip context (fixed status
order for stable geometry; `in_progress` is intentionally omitted):

```json
{ "open": 4, "blocked": 1, "deferred": 0, "closed": 12 }
```

## API Surface

| Method | Path | Purpose | → Endpoint doc |
| --- | --- | --- | --- |
| GET | `/` | The board page shell — `index` renders `dashboard.html` (skeletons) instantly, never blocking on `bd`; hydrated by the partials below. | [BoardPage](../Views/BoardPage.md) |
| GET | `/api/lanes` | Render the Epics strip + Deferred/Blocked/Ready/In Progress lanes + Activity feed from the active-only snapshot (with per-epic dependency hydration) → `partials/lanes.html`. | [LanesApi](../Endpoints/LanesApi.md) |
| GET | `/api/lanes/closed` | Render the Closed lane only from the date-bounded (`BOARD_CLOSED_WINDOW_DAYS=3`) closed snapshot → `partials/closed_lane.html`; lazy-loaded after the active lanes paint. | [LanesApi](../Endpoints/LanesApi.md) |
| GET | `/api/counts` | Render the masthead Open/Blocked/Deferred/Closed KPI strip over the full snapshot → `partials/counts.html` (no In Progress — see Configuration). | [LanesApi](../Endpoints/LanesApi.md) |
| GET | `/api/bead/{id}` | Open the shared bead modal when an epic chip, lane card, or Activity row is clicked. | [BeadDetailApi](../Endpoints/BeadDetailApi.md) |
| GET | `/api/events` | SSE stream; a `beads_changed` event fires `refresh from:body`, re-fetching all three board regions so the board updates live. | [SseEvents](../Endpoints/SseEvents.md) |

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |
| Board page shell route (validate workspace → render skeleton, never blocks on bd) | `src/bdboard/app.py` | `index` |
| Active-lanes route (active snapshot → epic hydration → strip/lanes/activity) | `src/bdboard/app.py` | `api_lanes` |
| Closed-lane route (date-bounded closed snapshot → closed partial) | `src/bdboard/app.py` | `api_lanes_closed` |
| Masthead counts route (full snapshot → counts partial) | `src/bdboard/app.py` | `api_counts` |
| Concurrent per-epic dependency hydration (so wired epic chains can be ordered) | `src/bdboard/app.py` | `_hydrate_epic_dependencies` / `_load` |
| Workspace validation surfaced as the page's 500 error | `src/bdboard/app.py` | `_validate_or_warn` |
| Lane bucketing (status + unmet-blocker → Deferred/Ready/In Progress/Blocked/Closed) | `src/bdboard/derive/lanes.py` | `lanes` |
| Epic strip ordering (topo-sort wired chains, anchor the active/next-ready epic) | `src/bdboard/derive/lanes.py` | `epic_lane` / `_epic_lane_rank` / `_topo_component_order` |
| "Functionally blocked" detection (open + unmet `blocks`/`blocked-by` target) | `src/bdboard/derive/lanes.py` | `_has_unmet_blocking_dep` |
| Dependency field normalization (deps/dependencies, type variants, target-id chain) | `src/bdboard/derive/lanes.py` | `get_dependency_list` / `get_dependency_type` / `get_dependency_target_id` |
| Epic / molecule-wrapper / closed classification | `src/bdboard/derive/lanes.py` | `_is_epic` / `_is_molecule` / `_is_closed` |
| Activity feed synthesis ("current state as event", newest first) | `src/bdboard/derive/lanes.py` | `activity` |
| Masthead counts (fixed status order; omits in_progress) | `src/bdboard/derive/lanes.py` | `counts` |
| Lane keys / closed statuses / board window / status icons | `src/bdboard/derive/lanes.py` | `LANES` / `CLOSED_STATUSES` / `BOARD_CLOSED_WINDOW_DAYS` / `_STATUS_META` |
| Stable created_at-then-id ordering key | `src/bdboard/derive/lanes.py` | `_stable_key` / `timeutil._epoch` |
| Active snapshot source (~5KB fast path) | `src/bdboard/store.py` | `Store.snapshot_active` / `Store._load_active` |
| Date-bounded closed snapshot source | `src/bdboard/store.py` | `Store.snapshot_closed` / `Store._load_closed` |
| Full (active + closed) snapshot for counts | `src/bdboard/store.py` | `Store.snapshot` |
| `bd list` active fetch (`--no-pager --limit 0`) | `src/bdboard/bd.py` | `BdClient.list_active` |
| `bd list` closed fetch (`--status closed --closed-after <cutoff> --sort closed`) | `src/bdboard/bd.py` | `BdClient.list_closed` |
| SSE fan-out so the board re-fetches on `.beads/` change | `src/bdboard/events.py` | `EventBus.broadcast` (`bus.broadcast`) |
| Lanes partial (Epics strip, four active lanes, lazy Closed placeholder, Activity) | `src/bdboard/templates/partials/lanes.html` | whole template |
| Closed-lane partial (card list + count, `data-closed-at` for the filter) | `src/bdboard/templates/partials/closed_lane.html` | whole template |
| Shared bead card (active lanes, closed lane, History) | `src/bdboard/templates/partials/bead_card.html` | whole template |
| Counts partial (masthead KPI `<dl>`) | `src/bdboard/templates/partials/counts.html` | whole template |
| Loading skeletons (no blank flash / layout jump) | `src/bdboard/templates/partials/lanes_skeleton.html` / `counts_skeleton.html` / `bead_card_skeleton.html` | whole templates |
| Page shell + board time-filter JS (`applyBoardFilter` / `syncMastheadClosedCount`) | `src/bdboard/templates/dashboard.html` / `base.html` | whole templates |
| Lane / epic / count / activity derivation tests | `tests/` | `test_derive_epics.py`, `test_derive_counts.py`, `test_deferred_fallback.py`, `test_board_counts_filter_sync.py` |

## Configuration

| Key | Default | Effect |
| --- | --- | --- |
| `BOARD_CLOSED_WINDOW_DAYS` (`src/bdboard/derive/lanes.py`) | `3` | The look-back window bounding the board's Closed set at fetch time (`bd list --closed-after`). Keeps the Closed-lane count and the masthead CLOSED KPI counting the same date-bounded set (bdboard-p8v). Older closures live on the History page. |
| `LANES` (`src/bdboard/derive/lanes.py`) | `("deferred","ready","in_progress","blocked","closed")` | The stable lane keys used as template selectors. **Render order is controlled by the template**, not this tuple (`lanes.html` renders Deferred → Blocked → Ready → In Progress, then Closed + Activity). |
| `CLOSED_STATUSES` (`src/bdboard/derive/lanes.py`) | `{"closed","resolved","done"}` | Which statuses count as "closed" for lane bucketing, the activity verb, and unmet-blocker resolution. |
| `counts` status order (`src/bdboard/derive/lanes.py`) | `["open","blocked","deferred","closed"]` | The fixed KPI order for stable header geometry; zero counts are still emitted to avoid layout jitter. `in_progress` is intentionally omitted (single-flight tool — the In Progress lane already shows the one active bead). |
| Board time filter (`base.html`) | `12h` / `1d` / `3d`, default `1d` | Client-only recency window persisted in `sessionStorage['bdboard-time-filter']`; narrows the Closed lane via `data-closed-at` and re-syncs the masthead CLOSED cell. Never round-trips to the server. |
| `LIST_TIMEOUT_S` (`src/bdboard/bd.py`) | (module constant) | Per-`bd list` subprocess timeout for `list_active` / `list_closed`. On failure the affected snapshot cache stays empty and the lane renders its empty state. |
| `BDBOARD_WORKSPACE` (env) | `$PWD` / cwd | Workspace whose `.beads/` the board reads. |
| `BDBOARD_BD_BIN` (env) | `bd` | The `bd` binary the list/show subprocesses invoke; must resolve. |

> [!NOTE]
> The lane keys, closed-status set, board window, and counts order are
> **module-level constants** in `derive/lanes.py`, not environment variables —
> change them in source (and re-run the derive tests). Only `BDBOARD_*` are
> runtime-configurable, and the recency window is a browser-side preference.

## Edge Cases

> [!WARNING]
> **`/api/lanes` fetches the active-only snapshot, so a bead blocking on a
> *closed* bead is conservatively shown as Blocked.** Without the closed set in
> the initial fetch, `_has_unmet_blocking_dep` can't see that the target is
> already done, so it treats the unknown target as unmet. The next
> full-snapshot SSE refresh corrects it — an accepted tradeoff for the ~100x
> payload reduction (bdboard-0yy).

> [!WARNING]
> **An `open` bead with an unmet blocking dependency lands in Blocked, not
> Ready.** Lane assignment is "functional," not literal: `_has_unmet_blocking_dep`
> walks `blocks`/`blocked-by`/`blocked_by` edges, and an unknown target id is
> treated as unmet (conservative). So Ready means genuinely actionable.

> [!WARNING]
> **Epics and `molecule` wrappers never get a swim-lane card.** `derive.lanes`
> excludes `issue_type == "epic"` (they live in the Epics strip) and
> `issue_type == "molecule"` (the redundant formula-pour grouping wrapper —
> Option A). The molecule still parents the poured tree in `bd`; it just doesn't
> earn a card here.

> [!WARNING]
> **The Closed lane count and the masthead CLOSED KPI must agree — and only do
> because both read the same date-bounded set.** The lane renders
> `store.snapshot_closed()` (board window) and the KPI counts the full
> `store.snapshot()`; they stay consistent only because `list_closed` bounds the
> closed set to `BOARD_CLOSED_WINDOW_DAYS` at fetch time (bdboard-p8v). The
> client-side 12h/1d/3d filter then narrows *both* in lockstep via
> `syncMastheadClosedCount`.

> [!CAUTION]
> **The Activity feed is synthesized, not a real audit log.** bd exposes no
> cross-bead audit feed, so `derive.activity` emits one row per bead from its
> most-recent timestamp with a verb inferred from current status — it is
> "current state as event," not a true history. On first paint it shows active
> events only; closed events appear after a full-snapshot SSE refresh. For real
> per-bead history, open the bead modal's audit trail.

## Error Scenarios

| Trigger | Behavior | User sees |
| --- | --- | --- |
| `GET /` with an invalid/unresolvable workspace | `index` calls `_validate_or_warn`, returns `error.html` | `500` — a workspace error page instead of an empty board |
| `GET /api/lanes` and `bd list_active` fails/times out | `Store._load_active` logs and leaves the active cache empty; `derive` runs over `[]` | `200` — every active lane renders its *"(empty)"* row and the Epics strip *"(no active epics)"* |
| `GET /api/lanes/closed` and `bd list_closed` fails/times out | `Store._load_closed` logs and leaves the closed cache empty | `200` — the Closed lane renders *"(empty)"* with a `0` count |
| `GET /api/counts` and the snapshot is empty | `derive.counts` returns all-zero fixed-order counts | `200` — KPI cells read `0` (with `counts-cell-zero` muting), header geometry stable |
| Active lane bucket is empty | `lanes.html` `{% else %}` branch | *"(empty)"* `lane-empty` row in that lane |
| No active epics | `lanes.html` `{% else %}` branch on the strip | *"(no active epics)"* row |
| No timestamped beads | `activity()` returns `[]` → `lanes.html` `{% else %}` | *"no activity yet"* row in the Activity lane |
| The recency filter hides every Closed card | `applyBoardFilter` recomputes the visible count | Closed count badge + masthead CLOSED read `0`; cards are hidden, not removed |
| A dependency cycle among epics | `_topo_component_order` appends the leftover nodes by stable key | The strip still renders deterministically (no crash, no infinite loop) |
| Click a bead whose id no longer resolves | `/api/bead/{id}` returns the modal-error fragment | `404` — *"We couldn't find that bead…"* in the modal |

## Testing

- **Lane bucketing** — `tests/test_derive_epics.py` covers epic exclusion from
  the main columns and the strip ordering; `tests/test_deferred_fallback.py`
  covers the catch-all Deferred bucket for non-standard statuses.
- **Counts** — `tests/test_derive_counts.py` pins the fixed status order, the
  zero-inclusion (stable geometry), and the deliberate `in_progress` omission.
- **Counts ↔ closed-lane sync** — `tests/test_board_counts_filter_sync.py`
  covers the masthead CLOSED cell staying in lockstep with the client-side
  recency filter.
- **Contrast / a11y** — `tests/test_bead_status_contrast.py`,
  `test_epic_status_contrast.py`, `test_counts_contrast.py`,
  `test_closed_filter_contrast.py`, and `test_snappy_transitions.py` cover the
  lane/epic/count colour tokens and motion behavior against WCAG AA.
- **Manual check** — start the server, open `/`. Confirm the skeleton → lanes
  swap, the lazily-loaded Closed lane, the 12h/1d/3d filter narrowing the Closed
  set + masthead, and clicking a chip/card/row opening the modal. From a
  terminal:
  ```bash
  curl -i 'http://127.0.0.1:8765/api/lanes' -H 'HX-Request: true'
  curl -i 'http://127.0.0.1:8765/api/lanes/closed' -H 'HX-Request: true'
  curl -i 'http://127.0.0.1:8765/api/counts' -H 'HX-Request: true'
  ```
  Expect three HTML fragments: the Epics strip + active lanes + Activity, the
  Closed lane card list, and the masthead counts `<dl>`.

## Related

- [Board page (`/`)](../Views/BoardPage.md) — the full-page view this feature is
  the behavior-first overview of (shell, masthead, toolbar, lanes region).
- [Lanes API (`/api/lanes`, `/api/lanes/closed`, `/api/counts`)](../Endpoints/LanesApi.md)
  — the three read-only hydration endpoints behind the strip, lanes, closed
  lane, and counts.
- [Bead detail API (`/api/bead/{id}`)](../Endpoints/BeadDetailApi.md) — the
  shared modal each epic chip, lane card, and Activity row opens.
- [Bead detail & inline editing (Feature)](BeadDetailAndInlineEditing.md) — the
  modal feature the board's clickable references open.
- [Formula pour (Feature)](FormulaPour.md) — the **+ Pour Formula** dialog
  reachable from this board; a pour lands new beads that appear live in the lanes.
- [Live auto-refresh (Feature)](LiveAutoRefresh.md) — the SSE `beads_changed →
  refresh from:body` mechanism that re-fetches the board's counts + lanes on
  every `.beads/` change.
- [Live-refresh pipeline (Flow)](../Flows/LiveRefreshPipeline.md) — the
  bd-write → watcher → refresh → broadcast → re-fetch flow that repaints this
  board's lanes and counts.
- [Server startup & workspace resolution (Flow)](../Flows/ServerStartup.md) —
  the boot path that resolves and validates the workspace this board reads.
- [SSE events (`/api/events`)](../Endpoints/SseEvents.md) — the live-refresh
  stream the board's regions ride.
- [Derive layer (pure view shaping)](../Concepts/DeriveLayer.md) — where the
  `lanes` / `epic_lane` / `activity` / `counts` derivations live.
- [Store snapshot cache & change detection](../Concepts/StoreSnapshotCache.md) —
  the active / board-closed / full snapshot split this board reads from.
- [bd CLI as runtime source of truth](../Concepts/BdCliSourceOfTruth.md) — why
  the lanes, counts, and epic hydration bottom out in `bd list` / `bd show`.
- [HTMX + server-rendered partials](../Concepts/HtmxPartialsArchitecture.md) —
  the `hx-get` + lazy nested-load (`/api/lanes` → `/api/lanes/closed`) pattern
  this board is built on.
- [Watcher debounce/cooldown & self-feedback skip](../Concepts/WatcherScheduling.md)
  — how the `refresh` pulse re-fetching this board is debounced and kept from
  looping on bdboard's own reads.
- [Features index](index.md) · [Architecture](../Architecture.md#api-surface) ·
  [Manifest](../_Manifest.md) — the feature catalog and system view this sits in.
