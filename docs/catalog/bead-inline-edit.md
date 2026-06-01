# Inline field editing

Part of the **Board** page. See also [bead-modal.md](./bead-modal.md) (the
detail modal that hosts these rows), [bead-audit.md](./bead-audit.md) (the
history view that records the edits), and [store-cache.md](./store-cache.md)
(the cache that field edits invalidate).

## What it shows

Inside the bead detail modal, each field is rendered as a row in the field
grid (`partials/field_row.html`). For **editable** fields on an **open** bead,
the row carries a small inline-edit affordance: a collapsed `<details>` whose
`<summary>` reads **"Edit `<field>`"**. Expanding it reveals a real form with a
labelled control whose editor kind is chosen server-side from the field
registry:

- **text** — single-line input (`title`, `assignee`, `external_ref`).
- **md / textarea** — multi-line textarea (`description`, `acceptance_criteria`,
  `design`).
- **select** — a dropdown built from the registry's `enum_options`
  (`priority` → P0..P4, `issue_type` → bug/feature/task/…).
- **number** — numeric input (`estimate`).

Each editor has **Cancel** and **Save** buttons plus a per-row polite
`aria-live` feedback region (`[data-edit-feedback]`) that announces save/error
status without stealing focus. On open, focus moves into the first control
(`ontoggle`). The **priority** field also drives the modal-header priority
badge (`partials/bead_priority_badge.html`), which stays in sync after an edit.

Two affordances are deliberately different:

- **Append-only `notes`** render an **"+ Add a note"** disclosure instead of an
  editable replace box. The textarea starts empty and your note is *appended*
  below the existing history — never a prefilled replace.
- **Non-editable fields** (and *all* fields on a non-open bead) render no edit
  affordance at all — read-only is the default.

## Where the data comes from

The display rows and the write path share a single source of truth so a saved
row re-renders byte-identical to its original:

- **Render hints:** `_ordered_fields(bead)` in `src/bdboard/app.py` (~1294)
  walks every non-hidden bd field and calls `_field_row()` (~1294), which pulls
  editability hints (`editable` / `editor` / `flag` / `enum_options` /
  `append_only`) from the **field registry** `_FIELD_REGISTRY` (~1398). The
  registry is the *one* place that decides which fields are ever editable and
  with which exact `bd update` flag.
- **Write route:** `POST /api/bead/{bead_id}/field` →
  `api_bead_field_update` in `src/bdboard/app.py` (~966). It accepts form
  fields `field`, `value`, `expected_updated_at`, and `csrf_token` (plus the
  `X-CSRF-Token` header). On success it returns **just the re-rendered field
  row** (`partials/field_row.html`) for an in-place HTMX swap of
  `#field-row-<field>`.
- **Mutation layer:** `BdClient.update_field(bead_id, flag, value, actor)` in
  `src/bdboard/bd.py` (~662) shells `bd update <id> <flag> <value>` on the
  serialized `_subprocess_gate`. Long markdown flags
  (description/design) stream the value on stdin via a file-flag alias rather
  than a positional arg. The human `actor` is forwarded as `--actor` so the
  audit trail attributes the edit correctly. After the write it clears the
  per-bead show cache and invalidates sibling caches.
- **Source of truth:** the bd workspace's local Dolt store. bdboard holds no
  separate copy beyond the short-lived caches.

The form's wire contract is centralized in the `field_form` Jinja macro inside
`field_row.html` — both the edit-field form and the add-note form POST to the
same endpoint with the same swap target and the same CSRF/`field` hidden
inputs, so the two write paths can never drift.

## What changes its state

- **User saves an edit** → the inline `<form>` fires its `hx-post` to
  `/api/bead/<id>/field`, carrying the CSRF token via `hx-headers` and the
  `expected_updated_at` optimistic-lock token (replace forms only). On a 2xx
  the response swaps the re-rendered row into `#field-row-<field>`; the
  `<details>` collapses and `htmx:afterSwap` announces "Saved." and moves focus
  to the updated row.
- **Priority change** → the route additionally appends an **out-of-band** copy
  of `bead_priority_badge.html` (`oob=True`) so HTMX swaps the modal-header
  badge in the *same* response — no modal close/reopen needed.
- **Server broadcasts SSE** → after a successful write the route calls
  `bus.broadcast("beads_changed")` so other tabs/clients refresh too (the
  acting tab already got its row swap from the response).
- **Cache invalidation** → `update_field` clears the show cache and invalidates
  list caches so the route's follow-up `show_long` returns post-edit state
  instead of an up-to-10s-stale snapshot.

## Edge cases & notes

- **CSRF required.** The route calls `_check_csrf(x_csrf_token, csrf)`
  (`src/bdboard/app.py` ~604) and accepts **either** the `X-CSRF-Token` header
  (HTMX `hx-headers`) **or** the `csrf_token` form field (non-JS fallback). A
  missing/incorrect token raises `HTTPException(403)`. (Covered by
  `test_field_update_requires_csrf_token`.)
- **Registry is the only authority.** The `field` name is validated against
  `_FIELD_REGISTRY`; a field that is not whitelisted (or whitelisted but
  missing a flag) returns **400** "Field is not editable." The client never
  chooses the `bd update` flag — only the registry's pinned `flag` is used, so
  a crafted POST can't write a non-editable / shape / lifecycle / immutable
  field (status, parent, id, story_points, timestamps, …). (Covered by
  `test_field_update_rejects_non_editable_field`,
  `test_field_update_rejects_unknown_field`,
  `test_field_update_uses_registry_flag_not_client_input`.)
- **Optimistic lock / live re-read rejection.** Before writing a replace-edit
  the route re-reads the bead **LIVE** (`bd.show_long(id, fresh=True)`,
  cache-bypassing). If the live `updated_at` differs from the form's
  `expected_updated_at`, the stale submit is rejected with **409** "This bead
  changed since you opened it — please refresh…" and **never reaches bd** (no
  silent clobber). A missing/empty token (older form) degrades to
  last-write-wins rather than blocking. (Covered by
  `tests/test_field_edit_concurrency.py`:
  `test_stale_form_rejected_without_clobber`.)
- **Status gate.** Manual editing only applies to **open** beads. A LIVE read
  feeds `_bead_is_editable()` (~1456): once a bead is `in_progress` (claimed)
  or closed/resolved/done (historical), all field writes are rejected with
  **403**, even though the UI already hides the affordances. `_LOCKED_EDIT_STATUSES`
  reuses `derive.CLOSED_STATUSES` plus `in_progress` (DRY). The same status
  gate also drives the UI hint pass so server and template never disagree.
  (Covered by `tests/test_field_edit_status_gate.py`.)
- **Append-only notes skip the lock.** `notes` is editable but `append_only`
  (flag pinned to `--append-notes`, never `--notes`, which would REPLACE and
  nuke agent verification history). An append never clobbers, so the
  optimistic-lock check is skipped even with a stale token. An empty append is
  rejected with **400** "Nothing to add." (Covered by
  `test_notes_append_skips_lock_even_if_stale`.)
- **Error routing to inline message.** HTMX does not swap non-2xx responses by
  default; the `htmx:beforeSwap` handler in `templates/base.html` (~277)
  detects a 4xx/5xx from a field-edit form, cancels the row swap
  (`shouldSwap = false`), and renders the server's small `<p class="field-error">`
  fragment into the row's `[data-edit-feedback]` polite live region — so a
  failed save **never wipes the row**; the editor stays open with the error
  announced in place.
- **bd write failure.** If `update_field` raises `RuntimeError`, the route
  returns **500** "Could not save: …" routed to the inline feedback region.
- **Save-but-can't-refresh fallbacks.** After a successful write the route
  re-reads the bead to re-render the row. If the live read fails it falls back
  to the cached snapshot; if the bead can't be re-read at all it returns a
  200 nudge to reopen the modal; if the saved field is no longer in the
  rendered set (e.g. cleared to empty) it returns a 200 "Saved." status.
- **A11y (WCAG 2.2 AA).** Native `<summary>` (keyboard operable), real
  `<label>` bound to each control, focus moved into the first control on open,
  a per-row polite aria-live feedback region, and a global `#a11y-announce`
  "Saved." announcement on success.

## Source files

- `src/bdboard/app.py` — `api_bead_field_update` (route, ~966), `_check_csrf`
  (~604), `_FIELD_REGISTRY` + `FieldSpec` (~1372), `_field_spec` (~1435),
  `_bead_is_editable` / `_LOCKED_EDIT_STATUSES` (~1448), `_field_row` /
  `_ordered_fields` (~1490).
- `src/bdboard/bd.py` — `BdClient.update_field` (~662), `show_long` (~384),
  `_run_mutate` (~704).
- `src/bdboard/templates/partials/field_row.html` — the row markup, the
  `field_form` macro (shared wire contract), the inline edit-field form, and
  the append-only add-note form.
- `src/bdboard/templates/partials/bead_priority_badge.html` — the
  modal-header priority badge, swapped out-of-band after a priority edit.
- `src/bdboard/templates/base.html` — `htmx:beforeSwap` error routing into
  `[data-edit-feedback]` (~277) and `htmx:afterSwap` "Saved." announce + focus.
- `tests/test_field_edit.py` — CSRF, registry validation, flag selection,
  notes append flag.
- `tests/test_field_edit_concurrency.py` — optimistic-lock / stale-form
  rejection, notes-append exemption, token presence in the rendered form.
- `tests/test_field_edit_status_gate.py` — open-only editing (in_progress /
  closed rejection).
