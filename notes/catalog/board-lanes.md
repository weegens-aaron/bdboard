# Open lanes

Part of the **Board** page — the main horizontal region of swim lanes plus the
Epic strip. See also [board-closed-lane.md](./board-closed-lane.md) (the Closed
lane, which lazy-loads separately into this same grid),
[board-counts.md](./board-counts.md) (the masthead stats strip the lanes
summarize), [sse-live-refresh.md](./sse-live-refresh.md) (the live-update
pipeline that re-fetches the lanes), [store-cache.md](./store-cache.md) (the
cached snapshot the lanes are derived from), and
[bead-modal.md](./bead-modal.md) (the detail view a card opens when clicked).

## What it shows

The board's central content: an **Epic strip** across the top followed by a row
of **status swim lanes**, each holding cards for the beads in that state.

- **Epic strip** (`.epic-lane`) — a horizontal list of active **epics**, each a
  chip showing id, priority, title, status icon+label, and assignee. Epics are
  sequenced left-to-right along their dependency chains (predecessor →
  successor), with the currently-active (or next-ready) epic anchored first.
- **Open status lanes** — four columns rendered in this fixed order:
  - **Deferred** — open-ish beads that aren't ready, blocked, or in progress.
  - **Blocked** — beads with status `blocked`, *or* open beads with an unmet
    blocking dependency.
  - **Ready** — open beads with no unmet blocking dependency (available work).
  - **In Progress** — beads with status `in_progress`.
- **Closed lane** — a fifth lane that loads separately after first paint; it has
  its own catalog doc ([board-closed-lane.md](./board-closed-lane.md)).
- **Activity lane** — a synthesized recent-activity feed (one row per bead using
  its most recent timestamp + an inferred verb).

Each lane has a title with a **count badge** and a list of **cards**. A card
shows the bead id, a priority pill (`P0`–`Pn`), the title, and a meta row
(assignee, issue type, dependency count). Clicking any card or epic chip fires an
HTMX `GET /api/bead/<id>` into the `#bead-modal` target to open the detail view.

## Where the data comes from

- **Route:** `GET /api/lanes` → `api_lanes` in `src/bdboard/app.py` (~414). It
  renders `partials/lanes.html` with three context values: `epic_lane`, `lanes`,
  and `activity`. **Performance note (bdboard-0yy):** this route fetches
  **active-only** issues (~5KB) for fast first paint; the heavy Closed lane is
  fetched separately via `GET /api/lanes/closed` → `api_lanes_closed` (~443),
  which renders `partials/closed_lane.html`.
- **Derive layer:** all in `src/bdboard/derive/lanes.py`, pure functions over the
  snapshot list (no I/O, no caching):
  - `lanes(beads)` — buckets **non-epic, non-molecule** beads into the
    `deferred / ready / in_progress / blocked / closed` lanes. Open lanes are
    sorted by priority asc then `updated_at` desc; closed by `closed_at` desc.
  - `epic_lane(beads)` — builds the epic strip: filters to active epics,
    topologically orders their dependency components, anchors the
    active/next-ready epic first, and enriches each with `status_key` /
    `status_icon` / `status_label`.
  - `activity(beads, limit=25)` — synthesizes a "current state as event" feed
    since bd exposes no cross-bead audit stream.
- **Epic dependency hydration:** `_hydrate_epic_dependencies` in `app.py` (~1223)
  grafts per-epic dependency arrays (via `bd show_long`) onto the snapshot before
  `epic_lane` runs, because `bd list` omits expanded deps.
- **Source of truth:** `await store.snapshot_active()` in `src/bdboard/store.py`
  (~84) — active issues from the in-memory Store cache (lazily loaded from the bd
  CLI, refreshed by the file watcher). The Closed lane uses
  `store.snapshot_closed()` (~94). Same cache, no separate source of truth.
- **Templates:**
  - `partials/lanes.html` — the real region: epic strip, the four open lanes
    (looping `["deferred", "blocked", "ready", "in_progress"]`), the Closed lane
    host (which itself lazy-loads `/api/lanes/closed`), and the Activity lane.
  - `partials/lanes_skeleton.html` — the load placeholder: mirrors the lane
    scaffold with shimmer cards so the board paints instantly and hydrates in
    place (`aria-hidden="true"` so AT waits for real content).
  - `partials/closed_lane.html` — the swapped-in Closed lane content.

## What changes its state

The region lives in `dashboard.html` (~54) as the `.lanes-region` host:

```html
<section class="lanes-region" aria-busy="true"
         hx-get="/api/lanes" hx-trigger="load, refresh from:body"
         hx-swap="innerHTML">
  {% include "partials/lanes_skeleton.html" %}
</section>
```

Two triggers drive it:

1. **`load`** — fires once when the board shell paints. The page shell returns
   instantly with the skeleton inside `.lanes-region`; HTMX then fetches
   `/api/lanes` and swaps the real region in (`hx-swap="innerHTML"`). This keeps
   time-to-first-paint from blocking on the bd-backed snapshot + epic-hydration
   subprocess calls.
2. **`refresh from:body`** — the SSE live-update hook. When the file watcher
   detects a `.beads/` change, the server broadcasts a `beads_changed` SSE event
   (`GET /api/events`, `sse_events` in `app.py` ~281). The `EventSource` in
   `base.html` (~439–454) listens for it and dispatches a synthetic `refresh`
   DOM event on `<body>`; every region wired with `hx-trigger="refresh
   from:body"` (lanes, closed lane, counts, …) re-fetches itself. So any board
   mutation — from anywhere, including another agent or terminal — re-renders the
   lanes within ~one watcher cycle, no page reload.

The lanes are **read-only** — they reflect state, they never mutate beads.
(Mutations happen elsewhere, e.g. inline edit / modal actions, which then
trigger the SSE refresh above.)

## Edge cases & notes

- **Grouping-node (molecule) display.** `lanes()` excludes both epics (they live
  in the strip) **and** `molecule`-typed wrappers via `_is_molecule`. A
  `bd mol pour` creates a `molecule` wrapper that parents the poured tree *plus*
  an `epic`-typed root step. Per the grouping-node display decision (Option A,
  see `notes/design/`), the human-readable `<formula> <id>` name is carried by the
  epic root step (which already surfaces in the epic strip), so the bare wrapper
  is redundant and is hidden from the swim lanes rather than rendered as a stray
  ready-lane card.
- **Swarm molecules surface (audit FB-5).** The `_is_molecule` exclusion above
  is split by `_is_swarm_molecule`: a `mol_type=swarm` molecule — the only object
  carrying a running swarm's existence + coordinator handle (`bd swarm create`,
  field guide ch7) — is NOT hidden. It earns its own **Swarms** lane (rendered
  only when non-empty, like Pinned/Gate) with a coordinator chip (the molecule's
  `assignee`). Formula-pour wrappers (also `molecule`-typed but WITHOUT
  `mol_type=swarm`) stay hidden — Option A is unchanged. A swarm has no stored
  status (bd computes it live from the children), so it is routed to the Swarms
  lane before status bucketing rather than falling through to Deferred.
- **Empty lanes stay visible.** The four open lanes are always rendered (the
  template loops a fixed key list), so an empty lane shows its title + a `(empty)`
  muted row rather than collapsing. The epic strip shows `(no active epics)` and
  the Activity lane shows `no activity yet` when empty. Layout stability over
  noise reduction.
- **aria-busy lifecycle.** `.lanes-region` ships with `aria-busy="true"` and the
  skeleton inside it (`aria-hidden="true"`) so assistive tech treats the
  placeholder as a loading affordance, not content. After the HTMX swap settles,
  the `htmx:afterSettle` handler in `base.html` (~228–232) flips the host's
  `aria-busy` to `"false"`. The `innerHTML` swap preserves the host element (and
  its `aria-busy` attribute) across refreshes, which is why the attribute-flip
  approach works. The Closed lane host hydrates the same way.
- **Conservative blocked detection on first paint.** `/api/lanes` fetches
  active-only issues, so a bead depending on a *closed* bead can't see that
  target and is conservatively shown as **blocked**. This is an accepted tradeoff
  for the ~100x payload reduction; the UI self-corrects on the next SSE refresh
  when the full snapshot is available. (`_has_unmet_blocking_dep` treats an
  unknown dependency target as unmet.)
- **Unmet-dep → blocked promotion.** An `open` bead with any unmet
  `blocks`/`blocked-by` dependency is routed to the **Blocked** lane, not Ready —
  so "Ready" genuinely means actionable.
- **Stable ordering.** Open lanes sort by `(priority asc, updated_at desc)`;
  epics use a topological order with a `created_at`-then-`id` stable tie-break,
  and degrade deterministically (append leftovers by stable key) if a dependency
  cycle exists.
- **Activity is synthesized, not a real audit log.** bd exposes no cross-bead
  event feed, so each bead becomes one entry from its most recent timestamp with
  a verb inferred from status. Capped at 25 entries, newest first.

## Source files

- `src/bdboard/app.py` — `api_lanes` route (~414) and `api_lanes_closed` (~443);
  `_hydrate_epic_dependencies` (~1223) for epic dep enrichment; `sse_events` SSE
  stream (~281) and `bus.broadcast("beads_changed")` calls that drive the
  `refresh` trigger.
- `src/bdboard/derive/lanes.py` — `lanes`, `epic_lane`, and `activity` pure
  derivations; `_is_molecule` grouping-node filter; `_has_unmet_blocking_dep`
  blocked detection.
- `src/bdboard/store.py` — `snapshot_active` (~84) and `snapshot_closed` (~94),
  the cached snapshot sources of truth.
- `src/bdboard/templates/partials/lanes.html` — the real lanes region (epic
  strip + open lanes + closed-lane host + activity).
- `src/bdboard/templates/partials/lanes_skeleton.html` — the shimmer load
  placeholder.
- `src/bdboard/templates/partials/closed_lane.html` — the swapped-in Closed lane.
- `src/bdboard/templates/dashboard.html` — the `.lanes-region` host with
  `hx-get="/api/lanes"` / `hx-trigger="load, refresh from:body"` (~54).
- `src/bdboard/templates/base.html` — the `EventSource` → `refresh` dispatch
  (~439) and the `htmx:afterSettle` `aria-busy` flip (~228).
- `tests/test_snappy_transitions.py` — board shell hydrates lanes lazily;
  asserts `lanes_skeleton.html` presence and `hx-get="/api/lanes"`.
