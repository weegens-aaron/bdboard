# Theme toggle (light/dark)

Part of the **Board** page masthead, but — like the nav and Pour Formula
button — **shared verbatim across all three top-level pages** (Board, History,
Memory). See also [nav.md](./nav.md) (the toggle was split out of the nav
partial and now lives with the top-row actions), [board-counts.md](./board-counts.md)
(the counts strip it sits beside in the actions group), and
[board-time-filter.md](./board-time-filter.md) (the other control sharing the
second masthead row).

## What it shows

A single **light/dark control** rendered as the trailing cell of the right-aligned
**actions group** in the masthead. It is a `<button id="theme-toggle">` that borrows
the `.mh-link` "contents bar" styling (small-caps label, hairline `border-left`
separator) so it reads as a cell of the same editorial strip as the counts and
the Pour Formula button — **but it is a `<button>`, not an `<a>`, and it sits
OUTSIDE the `<nav>` landmark**, because switching themes is an *action*, not
navigation.

The button carries **two label spans**, only one visible at a time:

- **☽ Dark** — shown when the **light** theme is active (the prompt tells you
  what you'll switch *to*).
- **☀ Light** — shown when the **dark** theme is active.

Which span shows is driven purely by CSS attribute selectors keyed off
`<html data-theme>` (see "What changes its state"), so the label always matches
the *action you'll take*, never the current state. The button also exposes
`aria-label="Toggle dark mode"` and a live `aria-pressed` state (`"true"` when
dark is active) for assistive tech.

## Where the data comes from

There is **no server-side or store data** behind this feature — the toggle is
pure client-side chrome whose only state is the current theme, and **the single
source of truth is the `data-theme` attribute on the `<html>` element**.

- **Partial:** `src/bdboard/templates/partials/theme_toggle.html` is the one
  shared source of the button markup. All three pages
  `{% include "partials/theme_toggle.html" %}` it inside their
  `.masthead-actions` group (`dashboard.html` ~32, `history.html` ~32,
  `memory.html` ~16), so the control stays consistent and DRY.
- **Initial theme resolution:** an **inline anti-FOUC script in the `<head>`**
  of `src/bdboard/templates/base.html` (~14–27) runs *before* the stylesheet/body
  paints and decides the theme in priority order:
  1. An explicit persisted choice in `localStorage['bdboard-theme']`
     (`'dark'` or `'light'`) wins.
  2. Otherwise it falls back to the OS preference via
     `window.matchMedia('(prefers-color-scheme: dark)')`.
  3. On any error (e.g. storage blocked) it defaults to `'light'`.
  It then **always sets an explicit `data-theme` attribute** on `<html>`, so the
  CSS has exactly one code path.
- **CSS source of truth:** `src/bdboard/static/styles.css` re-points the semantic
  colour tokens under `:root[data-theme="dark"]` (~139) and maps
  `color-scheme` to match (~239–240). Because every component references those
  aliases (no raw hex outside `:root`), flipping `data-theme` recolours the whole
  surface. The label/icon swap rules live at ~417–419, and the `.mh-toggle`
  layout at ~404–414.

## What changes its state

The toggle's state changes only through client-side JS — there is **no route,
no HTMX swap, no SSE push** involved.

1. **Click to flip.** A small JS handler in `base.html` (~456–480) wires the
   button's `click` to `applyTheme()`, which:
   - reads the current theme from `<html data-theme>`,
   - sets `data-theme` to the opposite value (this single attribute flip
     recolours everything via the CSS token re-point),
   - updates `aria-pressed` on the button, and
   - **persists** the new value to `localStorage['bdboard-theme']` (wrapped in
     `try/catch` so a storage-disabled browser still toggles, just without
     persistence).
2. **Live OS preference changes.** The same script subscribes to
   `matchMedia('(prefers-color-scheme: dark)')` `change` events (~485–495). If
   (and only if) the user has **not** made an explicit choice (no valid value in
   `localStorage`), it follows the OS — so when the OS flips to dark at sunset,
   the page follows. An explicit user choice always overrides the OS.
3. **CSS-only label swap.** The visible label (`☽ Dark` vs `☀ Light`) is **not**
   touched by JS — it flips automatically via
   `:root[data-theme="dark"] .mh-toggle .mh-toggle-to-light { display: inline; }`
   (and the inverse) the instant `data-theme` changes.

## Edge cases & notes

- **No-flash (anti-FOUC) is load-bearing.** The theme is resolved by an inline
  `<head>` script that runs **synchronously before first paint**, so the page
  never flashes the wrong theme. It deliberately is *not* deferred and *not* in
  an external file — both would run after paint. Don't "tidy" it into an external
  script.
- **Single attribute = single source of truth.** Everything (CSS token recolour,
  `color-scheme`, label swap, `aria-pressed`) keys off `<html data-theme>`. The
  JS only ever flips that one attribute; never set theme state in two places.
- **Initial resolution precedence:** explicit `localStorage` choice → OS
  `prefers-color-scheme` → `'light'` fallback. Only the literal strings
  `'dark'` / `'light'` count as an explicit choice; anything else is treated as
  "no choice" and the OS is followed live.
- **Storage-disabled browsers still work.** All `localStorage` reads/writes are
  wrapped in `try/catch`. With storage blocked the toggle still flips the theme
  for the session and falls back to the OS/`'light'` default on the next load —
  it just can't remember the choice across loads.
- **No `@media (prefers-color-scheme)` duplication (DRY).** Because the OS
  preference is resolved once in JS into an explicit `data-theme`, the dark
  recipe lives in exactly one place (`:root[data-theme="dark"]`) instead of being
  duplicated inside an `@media` block the attribute selector couldn't share.
- **`color-scheme` is set per theme** (`:root[data-theme="dark"] { color-scheme: dark }`),
  so native controls (scrollbars, form widgets, `<dialog>`) render in the matching
  scheme rather than the OS default.
- **Label describes the action, not the state.** Showing "☽ Dark" while in light
  mode is intentional — it tells the user what clicking will *do*. `aria-pressed`
  carries the actual on/off state for assistive tech so the two together are
  unambiguous.
- **It is an action, not navigation.** The button borrows `.mh-link` styling but
  lives **outside** the `<nav aria-label="Primary">` landmark; it must stay a
  `<button>`. (`tests/test_masthead_two_row_layout.py` asserts each page includes
  the toggle in its `.masthead-actions` group.)
- **Top row, not the nav row.** Although it shares the second masthead row's
  actions group, the toggle is part of `.masthead-actions` (opposite the page
  nav), not the `<nav>` itself — it was split out of `nav.html` precisely so the
  nav can sit alone while the toggle groups with the other actions.
- **Dark palette is WCAG-certified.** The dark token re-point keeps every
  text/background pair at AA; covered by `tests/test_dark_theme_contrast.py`
  (and per-component dark checks in `test_priority_badge_contrast.py`,
  `test_created_bar_contrast.py`).

## Source files

- `src/bdboard/templates/partials/theme_toggle.html` — the shared button markup:
  the `#theme-toggle` `.mh-link.mh-toggle` button with `aria-label`,
  `aria-pressed`, and the two `mh-toggle-to-dark` / `mh-toggle-to-light` label
  spans.
- `src/bdboard/templates/base.html` — the inline `<head>` anti-FOUC theme
  resolver (~14–27) and the footer toggle-wiring script: `currentTheme()`,
  `applyTheme()`, the click handler, and the live OS-preference subscription
  (~456–495).
- `src/bdboard/static/styles.css` — `.mh-toggle` layout (~404–414), the
  `data-theme`-keyed label/icon swap (~417–419), `color-scheme` mapping
  (~239–240), the dark token re-point block `:root[data-theme="dark"]` (~139),
  and the actions-group margin reset `.masthead-actions .mh-toggle` (~442).
- `src/bdboard/templates/dashboard.html` — includes the toggle in
  `.masthead-actions` (~32).
- `src/bdboard/templates/history.html` — includes the toggle (~32).
- `src/bdboard/templates/memory.html` — includes the toggle (~16).
- `tests/test_masthead_two_row_layout.py` — asserts the toggle sits in the
  second-row actions group on every page.
- `tests/test_dark_theme_contrast.py`, `tests/test_priority_badge_contrast.py`,
  `tests/test_created_bar_contrast.py` — certify the dark-theme palette this
  toggle activates meets WCAG AA.
