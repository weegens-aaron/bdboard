# Bead detail modal

Part of the **Board** page. See also [board-lanes.md](./board-lanes.md) (the
cards that open this modal), [bead-inline-edit.md](./bead-inline-edit.md) (the
per-row edit affordances hosted inside it), [bead-audit.md](./bead-audit.md)
(the audit-trail / lifecycle section it lazily loads),
[bead-raw.md](./bead-raw.md) (the raw-JSON escape hatch it links to), and
[store-cache.md](./store-cache.md) (the cache it falls back to when the live
read fails).

## What it shows

Clicking any bead card on the board opens a full-screen modal overlay
(`.modal-backdrop` + `.modal`) showing **everything bd knows about that one
bead**. It is read-first: the modal is a structured rendering of
`bd show <id> --long --json`, not a separate data model.

Top to bottom:

- **Header** — the bead id (`.bead-id`), the priority badge
  (`partials/bead_priority_badge.html`, e.g. `P2`), the status pill
  (`status-<status>`), and a close button (`✕`). Below that the bead title
  (`<h2 class="modal-title">`), an optional **⚠ warning** banner, and a
  **view-source line** reading `view: Live details` (or `Cached snapshot`)
  with a `raw JSON` link to `/api/bead/<id>/raw`.
- **Lifecycle slot** (`#lifecycle-slot`) — an empty placeholder at the top of
  the scroll region that gets filled by an out-of-band swap from the async
  audit response (status-transition timeline). One fetch, two render targets.
- **Bead details section** — a `<dl class="field-grid">` of **every non-hidden
  bd field** in a curated display order, each rendered as one
  `partials/field_row.html` row. The renderer dispatches on a per-field
  **kind** so each field type looks right:
  - **scalar** — plain value (`status`, `assignee`, timestamps…).
  - **empty** — a muted `—` for null/empty/`[]`/`{}` values.
  - **chips** — `labels` / `tags` as a chip list.
  - **markdown** — `description`, `notes`, `close_reason`,
    `acceptance_criteria` rendered through the `md` filter.
  - **deps** — `deps` / `dependencies` / `dependents` as a relationship list:
    each row shows a **direction-aware relationship label**, the linked bead
    id (itself an HTMX trigger that re-opens the modal on that bead), an
    optional status pill, and an optional title.
  - **comments** — author / timestamp / body cards.
  - **json** — any other dict/list value pretty-printed in a `<pre>`.
  Short scalar-ish metadata fields (`status`, `priority`, timestamps, counts…)
  render in a compact half-width layout (`field-short`) to cut vertical churn.
- **Inline-edit affordances** — editable fields on an **open** bead carry an
  "Edit `<field>`" disclosure; `notes` carries "+ Add a note". These are fully
  documented in [bead-inline-edit.md](./bead-inline-edit.md).
- **Audit trail section** — a lazily-loaded panel (`hx-trigger="load"`) that
  fetches `/api/bead/<id>/audit`. Documented in
  [bead-audit.md](./bead-audit.md).

## Where the data comes from

- **Route:** `GET /api/bead/{bead_id}` → `api_bead` in `src/bdboard/app.py`
  (~1144). It renders `partials/bead_modal.html`.
- **Primary read:** `bd.show_long(bead_id)` in `src/bdboard/bd.py` (~384)
  shells `bd show <id> --long --json`, unwraps the JSON array to a single bead
  dict, and serves through the per-bead show cache. This is the full-field
  payload (description, acceptance_criteria, dependencies, dependents,
  comments, timestamps — everything `--long` emits). `view: Live details`.
- **Field shaping:** `_ordered_fields(bead)` in `src/bdboard/app.py` (~1520)
  walks `_FIELD_ORDER` (identity → content → state/meta → bulk diagnostics),
  then appends any remaining keys alphabetically so a **new bd field is never
  silently hidden**. Each field becomes one row via `_field_row()` (~1491),
  which sets the render **kind** via `_classify_field()` (~1466), the
  half-width flag via `_is_short_meta_field()` (~1484), and editability hints
  from the field registry (see [bead-inline-edit.md](./bead-inline-edit.md)).
- **Dependency labels:** the `deps` kind passes each edge's type and the field
  key (`dependencies` vs `dependents`) through the `dep_label` Jinja filter,
  bound to `_dep_label(dep_type, direction)` in `src/bdboard/app.py` (~49).
- **Source of truth:** the bd workspace's local Dolt store. bdboard keeps no
  separate copy of bead detail beyond the short-lived show cache.

## What changes its state

- **Opening a card** → a board card carries
  `hx-get="/api/bead/<id>" hx-target="#bead-modal" hx-swap="innerHTML"`; the
  response (the whole `bead_modal.html`) is swapped into the `#bead-modal`
  container, which makes the overlay appear.
- **Clicking a dependency id inside the modal** → each `.dep-id` link is itself
  an `hx-get="/api/bead/<other-id>"` into `#bead-modal`, so the modal
  *re-renders in place* on the clicked bead — you can hop the dependency graph
  without closing it.
- **Closing** → the close button (and clicking the backdrop outside the
  `.modal`) sets `#bead-modal` innerHTML to empty, removing the overlay. No
  server round-trip.
- **Audit/lifecycle fill** → the audit section's `hx-trigger="load"` fires
  immediately after the modal swaps in, populating both the audit panel and
  (out-of-band) the `#lifecycle-slot` at the top.
- **Inline edits** → a saved field swaps just its own row in place; a priority
  edit additionally OOB-swaps the header badge. See
  [bead-inline-edit.md](./bead-inline-edit.md). The modal itself is otherwise
  static once rendered — it does **not** subscribe to SSE, so a background
  `beads_changed` event refreshes the board lanes but not an already-open
  modal (reopen to see external changes).

## Edge cases & notes

- **Dependency edge direction labelling (the big one).** A bd dependency edge
  reports `dependency_type` identically on *both* sides — `"blocks"` is the
  literal edge type, not a perspective. The correct human label therefore
  depends on BOTH the type AND the direction (which list the row is in).
  `_dep_label(dep_type, direction)` owns the full mapping; for `direction`,
  `"dependencies"` is **inbound** and `"dependents"` is **outbound**. Examples:
  - `blocks` + dependencies → **"blocked by"**; `blocks` + dependents →
    **"blocks"**.
  - `related` / `relates-to` → **"related"** in either direction.
  - `parent-child` + dependencies → **"child of"**; + dependents →
    **"parent of"**.
  - `discovered-from` → **"discovered from"** (inbound) / **"discovered"**
    (outbound); `validates` → **"validated by"** / **"validates"**;
    `caused-by`, `tracks`, `supersedes`, `until` map similarly.
  - **Unknown type** → the raw type string is shown verbatim (safe fallback).
  This function exists because of a real regression: the modal template once
  hardcoded "blocked by"/"blocks" by which list was rendering, *ignoring* the
  type, so every `related` edge was mislabeled "blocks" (see bdboard-fjk and
  the `dep-edge-direction` memory). The label logic now lives in Python, not
  the template — do **not** reintroduce a template-side hardcode.
- **dep-type field aliasing.** The template reads the type as
  `d.dependency_type or d.type or d.rel` and the target id as
  `d.depends_on_id or d.target or d.id`, tolerating bd payload shape variance.
  `_dep_label` lower-cases and defaults a missing type to `"related"`.
- **Live read fails → cached fallback.** If `bd.show_long` returns no bead
  (timeout / bd error), `api_bead` populates the store snapshot and falls back
  to `store.bead(bead_id)`. The modal still renders, the view line reads
  `view: Cached snapshot`, and a **⚠ warning** banner appears: "Showing cached
  details while live data is temporarily unavailable." The cached snapshot is
  the lighter list-shaped record, so some `--long`-only fields may be absent —
  but they degrade gracefully (see next point).
- **Missing / empty fields.** Only fields actually present on the bead dict are
  rendered (`if k in bead`), so a sparse cached fallback simply shows fewer
  rows rather than erroring. Present-but-empty values (`None`, `""`, `[]`,
  `{}`) classify as kind `empty` and render a muted `—` instead of a blank.
- **Bead not found.** If neither the live read nor the cached snapshot turns up
  the bead, the route returns **404** with a friendly `.modal-error` fragment
  ("We couldn't find that bead. Please refresh the board and try again.").
- **No silent field hiding.** Any bd field not in `_FIELD_ORDER` is appended
  alphabetically, and the only intentionally hidden key is `_type` (bd
  internal, in `_HIDDEN`). New bd fields therefore appear automatically.
- **Edit affordances are status-gated.** A bead that is `in_progress` or
  closed renders zero edit disclosures (`_bead_is_editable`); the modal is
  pure read-only for claimed / historical beads. Detail in
  [bead-inline-edit.md](./bead-inline-edit.md).
- **A11y (WCAG 2.2 AA).** The backdrop-click and close button both clear the
  modal; dependency links use real `<a>` semantics; the markdown renderer runs
  with `html=False` so bd-authored prose can't inject script.

## Source files

- `src/bdboard/app.py` — `api_bead` (route, ~1144), `_dep_label` (label
  mapping, ~49), `_ordered_fields` (~1520), `_field_row` (~1491),
  `_classify_field` (~1466), `_is_short_meta_field` (~1484), `_FIELD_ORDER`
  (~1265) / `_HIDDEN` (~1301) / `_KIND_*` sets, `_bead_is_editable` (~1454).
  The `dep_label` filter is registered on the Jinja env (~96).
- `src/bdboard/bd.py` — `BdClient.show_long` (`bd show --long --json`, ~384).
- `src/bdboard/templates/partials/bead_modal.html` — the modal shell: header,
  priority badge include, lifecycle slot, field grid, lazy audit section.
- `src/bdboard/templates/partials/field_row.html` — the per-field row markup,
  including the `deps` relationship list (the `dep_label` consumer) and the
  inline-edit affordances.
- `src/bdboard/templates/partials/bead_priority_badge.html` — the header
  priority badge (also OOB-swapped after a priority edit).
- `src/bdboard/static/` — modal / field-grid / dep-list styling.
