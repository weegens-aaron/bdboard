# Time-window filter (12h/1d/3d)

Part of the **Board** page — a small three-button strip in the masthead's second
row that narrows which time-stamped cards are visible across the board. It is a
purely **client-side** control: it shows/hides already-fetched cards rather than
re-querying the server. See also
[board-closed-lane.md](./board-closed-lane.md) (the only lane with timestamped
cards, so the only lane this filter currently affects),
[board-counts.md](./board-counts.md) (the masthead CLOSED KPI, which counts the
server's date-bounded set rather than the client-filtered subset),
[history-list.md](./history-list.md) (where longer time windows live —
7d/30d/90d/All — once work falls outside this filter's 3d max),
[theme-toggle.md](./theme-toggle.md) and [nav.md](./nav.md) (the sibling
controls that share the masthead nav row), and
[sse-live-refresh.md](./sse-live-refresh.md) (the refresh pipeline after which
the saved filter is re-applied).

## What it shows

A horizontal `radiogroup` of three "badge" buttons labelled **12h**, **1d**, and
**3d**, sitting at the right end of the masthead nav row.

- **Radio semantics** — the strip is a `<div role="radiogroup"
  aria-label="Time window filter" id="board-time-filter">` containing three
  `<button role="radio">` badges. Exactly one is selected at a time; the active
  badge carries `aria-checked="true"` plus the `.filter-badge-active` class, the
  other two carry `aria-checked="false"`.
- **Default selection** — **1d** is the default. It ships marked active in the
  template (`aria-checked="true"` + `filter-badge-active`), and on load the saved
  selection falls back to `'1d'` if nothing is stored.
- **Per-button accessible labels** — each badge has an explicit `aria-label`
  ("Show beads from the last 12 hours" / "…last 24 hours" / "…last 3 days") so
  the terse visible text (`12h`/`1d`/`3d`) doesn't strand screen-reader users.
- **Active state is more than colour** — `.filter-badge-active` swaps in the
  brand-blue fill *and* bumps font weight (700 → 800) and adds an inset shadow,
  so the selection is distinguishable without relying on colour alone (WCAG —
  the CSS comment calls this out explicitly).
- **What it actually controls** — selecting a window hides any timestamped card
  older than that window and rewrites the affected lane's count badge to the
  visible total. Today only the **Closed** lane has timestamped cards
  (`data-closed-at`), so in practice this is a "how recent must a closed bead be
  to show on the board" control. Non-timestamped lanes are unaffected.

## Where the data comes from

This feature has **no route of its own** — it never fetches. It operates entirely
on cards that other parts of the board already rendered.

- **The cards it filters** come from `GET /api/lanes/closed`
  (`api_lanes_closed` in `src/bdboard/app.py` ~443), which renders
  `partials/closed_lane.html`. Each closed card emits a
  `data-closed-at="<timestamp>"` attribute — the only timestamped cards on the
  board — and that attribute is the sole input to the filter's age comparison.
  See [board-closed-lane.md](./board-closed-lane.md) for that data path.
- **Source of truth for the cards** is the in-memory Store cache
  (`store.snapshot_closed()` in `src/bdboard/store.py`), bounded at fetch time to
  the last `BOARD_CLOSED_WINDOW_DAYS = 3` (`src/bdboard/derive/lanes.py` ~40,
  applied in `BdClient.list_closed`, `src/bdboard/bd.py` ~175). So the server
  hands the browser at most 3 days of closed cards; the filter can narrow that
  set in-browser but can never widen it.
- **Source of truth for the selection** is `sessionStorage` under the key
  `bdboard-time-filter` (`BOARD_FILTER_STORAGE_KEY` in `base.html` ~335). On load
  the strip restores from there, defaulting to `'1d'`. (sessionStorage, not
  localStorage — the selection lasts for the tab/session, not forever.)
- **The window definitions** live in the `BOARD_TIME_WINDOWS` map in `base.html`
  (~330): `{ '12h': 12h, '1d': 24h, '3d': 72h }` in milliseconds. The age check
  is `now - new Date(closedAt) <= filterMs`.

## What changes its state

All state lives in `base.html`'s inline script (`applyBoardFilter` and
`wireFilterBadges`, ~340–415).

1. **Badge click** — `wireFilterBadges()` binds a `click` listener to each badge
   (with `preventDefault` + `stopPropagation` so the click doesn't bubble into
   card/nav handlers). The handler calls `applyBoardFilter(badge.dataset.filter)`,
   which:
   - walks `.bead-card[data-closed-at]` in the closed lane, setting
     `style.display` to `''` (show) or `'none'` (hide) based on the age check;
   - tallies the visible count and writes it into the lane's
     `[data-closed-count]` badge;
   - updates the strip styling — toggles `.filter-badge-active` and sets
     `aria-checked` to `'true'`/`'false'` across all three badges;
   - persists the new selection to `sessionStorage`.
2. **Initial page load** — `DOMContentLoaded` calls `wireFilterBadges()`, which
   binds the listeners (once — guarded by a `data-wired` attribute) and applies
   the saved/default filter so the board opens already narrowed to 1d.
3. **SSE-triggered lane refresh** — when the live-refresh pipeline re-fetches the
   lanes (`htmx:afterSettle` on the `.lanes-region` or the `[data-lane="closed"]`
   element), `wireFilterBadges()` runs again. The masthead strip persists across
   these refreshes so it is *not* re-bound (the `data-wired` guard short-circuits),
   but the saved filter is **re-applied** to the freshly-swapped card content —
   otherwise a refresh would dump the full 3-day set back into view regardless of
   the user's selection. See [sse-live-refresh.md](./sse-live-refresh.md).

It never mutates beads, never hits the network, and never touches server state —
it is pure DOM show/hide plus a sessionStorage write.

## Edge cases & notes

- **3d max mirrors the closed-lane fetch window — by design.** The largest button
  is 3d because the server only ever fetches closed beads from the last
  `BOARD_CLOSED_WINDOW_DAYS = 3`. Offering a wider board filter would be a lie:
  there is no data behind it. Longer windows are deliberately deferred to the
  History page (7d/30d/90d/All), which uses a separate count-capped path
  (`list_closed_history`, `HISTORY_CLOSED_LIMIT = 50`). The template and the JS
  both carry comments restating this contract.
- **Filter narrows, never widens.** Because the fetch is already bounded to 3d,
  picking 3d shows everything the board has; 12h/1d only ever hide a subset. You
  cannot use this control to surface older closed work — that's History's job.
- **Count badge tracks the *filter*, not the *fetch*.** `applyBoardFilter`
  overwrites `[data-closed-count]` with the count of *visible* cards. So the
  Closed lane badge can legitimately read fewer than the number of cards in the
  DOM — the hidden ones are `display:none`, not removed. (The masthead CLOSED KPI
  in [board-counts.md](./board-counts.md) counts the server's date-bounded set
  and is **not** rewritten by this filter, so the two numbers can legitimately
  diverge when a sub-3d window is active.)
- **Cards without `data-closed-at` are always shown.** The template only emits
  the attribute when `closed_at` is present. `applyBoardFilter` short-circuits a
  missing/empty timestamp to "show" and still counts it — defensive handling for
  malformed/legacy beads.
- **Only the Closed lane is affected today.** Open lanes (ready/in-progress/
  blocked/deferred) carry no `data-closed-at`, so the filter is a no-op for them
  — they show every card regardless of window. The code comment notes this is the
  current reality, not a structural limit: any future lane that emits
  `data-closed-at` cards would be filtered automatically.
- **Selection survives refreshes, not reloads-to-default.** It persists in
  sessionStorage, so a tab refresh keeps the chosen window; closing the tab
  resets to the `1d` default on next open.
- **Idempotent wiring.** `wireFilterBadges` guards with a `data-wired` attribute
  so SSE refreshes don't stack duplicate click listeners on the persistent
  masthead strip — they only re-apply the filter to new lane content.
- **Timestamp parsing.** The age check does
  `new Date(timestamp.replace('Z', '+00:00'))` to coerce bd's `Z`-suffixed UTC
  timestamps into a form `Date` parses consistently across browsers before
  comparing against `Date.now()`.

## Source files

- `src/bdboard/templates/dashboard.html` — the `#board-time-filter` strip (~26):
  the `role="radiogroup"` container and three `role="radio"` badges with their
  default-active `1d` markup and per-button `aria-label`s. The surrounding
  template comment documents the 3d-max / History-page contract.
- `src/bdboard/templates/base.html` — `BOARD_TIME_WINDOWS` (~330),
  `BOARD_FILTER_STORAGE_KEY = 'bdboard-time-filter'` (~335),
  `applyBoardFilter()` (~340, the show/hide + count rewrite + aria/class +
  persist logic), `wireFilterBadges()` (~388, click binding + restore + idempotent
  guard), and the `htmx:afterSettle` / `DOMContentLoaded` hooks (~412) that wire
  and re-apply the filter.
- `src/bdboard/static/styles.css` — `.board-filters` (~655),
  `.filter-badge` / `:hover` / `.filter-badge-active` (~661): the strip layout
  and the colour-plus-weight-plus-shadow active treatment.
- `src/bdboard/templates/partials/closed_lane.html` — emits the
  `data-closed-at` cards and the `[data-closed-count]` badge this filter reads
  and rewrites (see [board-closed-lane.md](./board-closed-lane.md)).
- `src/bdboard/derive/lanes.py` — `BOARD_CLOSED_WINDOW_DAYS = 3` (~40), the fetch
  bound that the 3d max mirrors; `src/bdboard/bd.py` `list_closed` (~175) applies
  it at fetch time.
