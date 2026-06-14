# Primary navigation

Part of the **Board** page masthead, but **shared verbatim across all three
top-level pages** — Board, History, and Memory. See also
[board-counts.md](./board-counts.md) (the counts strip that shares the same
masthead editorial kit), [theme-toggle.md](./theme-toggle.md) (the toggle that
was split out of this partial and now lives with the top-row actions), and
[board-time-filter.md](./board-time-filter.md) (the other control that shares
the second masthead row).

## What it shows

A small, left-aligned **"contents bar"** of three page links sitting on the
**second masthead row** (`.masthead-nav-row`), beneath the workspace title:

- **BOARD** → `/` (the dashboard / swim-lane view)
- **HISTORY** → `/history` (trends + paginated record list)
- **MEMORY** → `/memory` (persistent insights list/search/create/delete)

The links are rendered as a typographic strip — small-caps + letterspacing
(matching the counts-strip labels) separated by **hairline vertical rules**
(`border-left`, the first link dropping its leading rule). There are **no pills,
boxes, borders, or filled backgrounds** — by deliberate design the nav reuses
the masthead's own editorial kit rather than introducing a competing widget
style.

Exactly **one** link is marked as the **current page**. Inactive links read in
the muted ink colour; the active link is emphasized with **three non-colour
cues** stacked together (see Edge cases): ink colour + bold weight + an inset
baseline rule.

The nav is plain server-rendered `<a href>` markup wrapped in a
`<nav aria-label="Primary">` landmark — **not** HTMX-swapped. Clicking a link is
a full-page navigation to a fresh server route.

## Where the data comes from

There is **no dynamic data** behind this feature — it is static structural
markup. The only piece of state is *which link is active*, which comes from a
single template variable:

- **Partial:** `src/bdboard/templates/partials/nav.html` is the one shared
  source of the markup. All three pages `{% include "partials/nav.html" %}` it
  (`dashboard.html` ~22, `history.html` ~30, `memory.html` ~14), so the three
  links stay consistent and DRY — add/rename a page in exactly one place.
- **The `active` variable:** each page route passes a string literal naming the
  current page into the template context:
  - `GET /` → `page_index` in `src/bdboard/app.py` passes `"active": "board"`
    (~345).
  - `GET /memory` → `page_memory` passes `"active": "memory"` (~378).
  - `GET /history` → `page_history` passes `"active": "history"` (~409).
- **Source of truth:** the **route handler itself** — the active page is known
  at render time from *which route is serving the request*, so there is no
  client-side detection, no `location.pathname` matching, and no store/snapshot
  involved. The value is one of `"board" | "history" | "memory"`.

The partial then does a per-link comparison:

```jinja
<a href="/"
   class="mh-link{% if active == 'board' %} is-active{% endif %}"
   {% if active == 'board' %}aria-current="page"{% endif %}>Board</a>
```

So when `active == 'board'` the Board link gets both the `is-active` styling
hook **and** `aria-current="page"`; the other two links get neither. The same
pattern repeats for `history` and `memory`.

## What changes its state

The nav is **read-only structural chrome** — it never mutates beads and never
re-renders in place. Its "state" (which link is current) changes only by
**navigating to a different page**:

1. **Full-page navigation.** Clicking BOARD/HISTORY/MEMORY is an ordinary
   browser navigation to `/`, `/history`, or `/memory`. The destination route
   re-renders `nav.html` with its own `active` value, so the active cue moves
   to the new page. There is **no SSE refresh, no HTMX swap, no polling** wired to
   this partial — unlike the counts strip and swim lanes, the nav does not
   listen for `refresh from:body`.
2. **In-flight click damping (cosmetic).** A small JS handler in `base.html`
   (~310) listens for clicks on `a.mh-link`. On a real navigation it adds the
   `is-navigating` class (which dims the link via `opacity` and
   sets `pointer-events: none`) so a rapid double-click reads as "already going" and
   the second click is blocked. It deliberately **ignores**:
   - modified clicks (`metaKey`/`ctrlKey`/`shiftKey`/`altKey` → new tab/window),
     so open-in-new-tab still works, and
   - clicks on the link that already has `aria-current="page"` (the current
     page), so re-clicking the active link is a no-op.
   This class is purely a transient affordance; it does not change which link is
   "active" — that is still owned by the server-rendered `is-active`/
   `aria-current`.

## Edge cases & notes

- **Active state uses THREE non-colour cues (WCAG 1.4.1).** The active link is
  signalled by ink colour **+ bold weight (`font-weight: 800`) + an inset
  baseline rule (`box-shadow: inset 0 -2px 0 var(--brand-blue)`)** — not colour
  alone. This means a colour-blind or low-vision user can still tell which page
  is current from the weight and the underline rule. Defined in
  `src/bdboard/static/styles.css` `.mh-link.is-active` (~392).
  (Asserted by `tests/test_masthead_nav_contrast.py` — checks the active link
  declares a `font-weight` and a `box-shadow`, not just a colour.)
- **Inactive links still meet contrast.** Inactive links use `var(--muted)`
  (gray-100 on paper-3 ≈ 4.74:1 light / 5.79:1 dark); the active link uses
  `var(--ink)` (gray-160 ≈ 13.6:1 light). Both clear the 4.5:1 text minimum.
  (Asserted by `tests/test_masthead_nav_contrast.py`.)
- **Hover is colour-only by design.** `.mh-link:hover` shifts muted → ink and
  nothing else (~383), so hover doesn't double-signal with the active baseline
  rule (which would make a hovered inactive link look "current").
- **Uniform padding so the underline reads identically.** The first link drops
  only its leading hairline rule (`:first-child` ~378) but keeps **symmetric
  horizontal padding** with the others on purpose — the active baseline rule
  spans the padding box, so zeroing `padding-left` would make BOARD's underline
  a different width/offset than the others.
- **`aria-current="page"` is exactly-one.** The conditional emits
  `aria-current="page"` on only the active link, giving assistive tech an
  unambiguous "you are here". (Asserted by `tests/test_page_memory.py` and
  `tests/test_page_history.py`, which check the exact
  `class="mh-link is-active"` + `aria-current="page"` markup per page.)
- **Single shared partial (DRY).** Because the markup lives only in
  `nav.html`, the three pages can never drift apart. The two-row masthead
  invariant — nav must sit on `.masthead-nav-row`, not the top row — is enforced
  by `tests/test_masthead_two_row_layout.py`.
- **Theme toggle is NOT part of this nav.** The toggle used to be emitted here
  but was split into `partials/theme_toggle.html` so it could be grouped with
  the top-row actions (Pour Formula, counts). It still *borrows* `.mh-link`
  styling so it reads as a trailing cell of the same contents bar, but it is a
  `<button>` **outside** the `<nav>` landmark — an action, not navigation.
- **No HTMX / no live refresh on the nav.** Intentional: the nav is static
  chrome. Only data regions (counts, lanes, history, memory list) carry
  `hx-trigger="refresh from:body"`; the nav does not, so an SSE `beads_changed`
  event never touches it.
- **Wrapped in a landmark.** `<nav class="masthead-nav" aria-label="Primary">`
  gives screen-reader users a labelled "Primary" navigation landmark to jump to.

## Source files

- `src/bdboard/templates/partials/nav.html` — the shared nav partial: the three
  `mh-link` anchors with the `active`-driven `is-active` + `aria-current`
  conditionals.
- `src/bdboard/templates/dashboard.html` — includes the nav on the
  `.masthead-nav-row` (~22).
- `src/bdboard/templates/history.html` — includes the nav (~30).
- `src/bdboard/templates/memory.html` — includes the nav (~14).
- `src/bdboard/app.py` — the three page routes that set `active`:
  `page_index` (`"board"`, ~345), `page_memory` (`"memory"`, ~378),
  `page_history` (`"history"`, ~409).
- `src/bdboard/templates/base.html` — the `a.mh-link` click handler that adds
  the `is-navigating` in-flight class and respects modified clicks / current
  page (~310).
- `src/bdboard/static/styles.css` — `.masthead-nav`, `.mh-link`,
  `.mh-link:first-child`, `.mh-link:hover`, `.mh-link:focus-visible`,
  `.mh-link.is-active` (~349–397), and the `.mh-link.is-navigating` in-flight
  state (~2654).
- `tests/test_masthead_nav_contrast.py` — non-colour active cues (weight +
  box-shadow), inactive/active contrast, focus-visible outline, small-caps kit.
- `tests/test_page_memory.py`, `tests/test_page_history.py` — per-page active
  link markup (`is-active` + `aria-current="page"`).
- `tests/test_masthead_two_row_layout.py` — nav lives on the second
  `.masthead-nav-row`, not the top row, on every page.
