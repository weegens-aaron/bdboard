# Pour Formula dialog

Part of the **Board** page. The "+ Pour Formula" button in the masthead opens a
modal that turns a bd *formula* (a reusable template of beads) into real,
live beads on the board — without leaving the dashboard or touching the CLI.

> **Architecture decision:** the formula-pour write surface is recorded in
> [ADR 0007](../decisions/0007-formula-pour-ui-write-surface.md).

## What it shows

A native `<dialog>` (`#formula-dialog`, title **"Pour a Formula"**) launched by
the **+ Pour Formula** button in the masthead actions. The button carries
`aria-haspopup="dialog"`; the `<dialog>` is opened with `showModal()`, so the
browser traps keyboard focus and handles Esc-to-close for free.

Inside, it is a deliberate **two-step flow** within one dialog:

1. **Formula picker** (`#formula-list`) — a list of every available formula,
   each rendered as a clickable card showing the formula **name** and (if
   present) a one-line **description**. Each card is a `<button>` labelled
   `Configure and pour <name>` for screen readers. Loading state shows
   "Loading formulas…"; an empty workspace shows a hint to add a formula under
   `.beads/formulas/`.
2. **Variable form** (`#formula-form`) — picking a formula swaps its variable
   form into this region (the picker stays visible above it). The form renders
   one text field per declared variable:
   - the variable **name** as the label,
   - the variable **description** as inline help text (`aria-describedby`),
   - the variable **default** pre-filled into the input,
   - a red `*` plus an `(required)` screen-reader hint on any variable that has
     **no default** (those inputs also get the HTML `required` attribute).
   A formula with no variables shows "This formula takes no variables." instead
   of fields. A **"Pour onto board"** submit button sits at the bottom.

After submit, a **pour result** region (`#formula-pour-result`, `aria-live`)
shows the outcome: a success line ("Poured `<name>` — N beads added to the
board.") or an error/warning. The board itself updates separately via SSE.

## Where the data comes from

Three routes back the three stages, all returning HTML partials for HTMX to
swap (never JSON to the browser):

| Stage | Route | Handler | bd call |
| --- | --- | --- | --- |
| Picker list | `GET /api/formulas` | `api_formulas` | `bd formula list --json` |
| Variable form | `GET /api/formulas/{name}/form` | `api_formula_form` | `bd formula list --json` + file read |
| Pour | `POST /api/formulas/{name}/pour` | `api_formula_pour` | `bd mol pour <name> --var k=v … --json` |

- **Formula list** comes from `BdClient.list_formulas()` (`src/bdboard/bd.py`
  ~493), which shells `bd formula list --json` (8s `FORMULA_LIST_TIMEOUT_S`).
  Each entry carries `name`, `description`, and **`source`** — the absolute
  path to the on-disk `*.formula.json` template.
- **Variables** are **not** available from any bd JSON command, so
  `BdClient.read_formula_variables(source)` (`src/bdboard/bd.py` ~519) **parses
  the `*.formula.json` file directly** off the `source` path. This is a
  documented bd CLI gotcha: `bd formula show --json` *omits* the `variables`
  block entirely, and the `vars` count in `formula list --json` is always `0`.
  Each parsed variable becomes `{name, description, default, required}` where
  `required = (default is None)`.
- **The pour** runs through `BdClient.pour_formula(name, variables)`
  (`src/bdboard/bd.py` ~570), which shells `bd mol pour <name> --var k=v … --json`
  (30s `POUR_TIMEOUT_S`, serialized on the subprocess gate because bd's
  embedded Dolt is single-writer). The returned JSON carries `new_epic_id` (the
  molecule wrapper node parenting the whole tree), `id_mapping` (stepId → real
  bead id), and `created` (raw node count).

**Source of truth:** the bd workspace's local Dolt store, plus the on-disk
`*.formula.json` template files for variable metadata. bdboard holds no copy of
either beyond bd's short-lived caches.

## What changes its state

- **Opening the dialog** → the masthead button's `onclick="openFormulaDialog()"`
  (`dashboard.html`) clears any leftover `#formula-form`, calls
  `dialog.showModal()`, then fires a custom `load-formulas` HTMX trigger on
  `#formula-list`. The picker uses `hx-trigger="load-formulas"` (a *custom*
  event, not `load`) so it fetches **fresh on every open** — a newly-added
  formula appears without a page reload, and it does not fetch on initial page
  load while the dialog is hidden.
- **Picking a formula** → the card button's `hx-get="/api/formulas/{name}/form"`
  with `hx-target="#formula-form"` swaps that formula's variable form into the
  form region. Picking a different formula simply re-swaps it.
- **Submitting the form** → the form's `hx-post="/api/formulas/{name}/pour"`
  (target `#formula-pour-result`) pours the beads and swaps the result
  acknowledgement into that region. The CSRF token rides along via both an
  `hx-headers='{"X-CSRF-Token": "…"}'` header **and** a hidden `csrf_token`
  form field.
- **New beads appearing on the board** → two paths, by design:
  1. The pour route calls `await store.refresh()` **then**
     `await bus.broadcast("beads_changed")`. The refresh-before-broadcast order
     is critical (bdboard-dfl): the optimistic broadcast must not race ahead of
     the cache refresh, or clients would re-fetch stale data missing the new
     beads. SSE then nudges every open tab to re-render the lanes.
  2. Independently, the file write also trips the existing
     `watchfiles → Store.refresh → SSE` pipeline, so the board stays correct
     even if the optimistic broadcast is missed.
- **Post-pour rename** → on success the route renames the wrapper node
  (`new_epic_id`) to `"<formula> <short-id>"` via `BdClient.rename_bead()` so
  two pours of the same formula are distinguishable on the board. The short id
  is just the suffix bd already minted (`_short_pour_id`, app.py ~708) — zero
  new entropy, already collision-free.

## Edge cases & notes

- **Required (no-default) variables — double-guarded.** A variable with no
  `default` is marked `required` in the form (browser blocks submit) **and**
  re-checked server-side: `api_formula_pour` re-reads the declared variables,
  collects submitted values (falling back to each variable's default when the
  field is blank), and if any required var is still empty returns HTTP **400**
  with "Please fill required variable(s): …" before any pour runs. The
  client-side `required` attribute is convenience; the server check is the real
  gate, so a crafted POST cannot skip it. (Covered by
  `test_pour_blocks_missing_required_var`,
  `test_pour_uses_default_when_field_blank`.)
- **CSRF required.** `api_formula_pour` calls `_check_csrf(x_csrf_token, csrf)`
  (app.py ~604) accepting **either** the `X-CSRF-Token` header **or** the
  `csrf_token` form field. A missing/incorrect token raises `HTTPException(403)`.
  (Covered by `test_pour_requires_csrf`.)
- **`--dry-run` is not enough — real stderr is surfaced.** Server-side
  pre-flight catches *missing variables* but not every pour-blocker (e.g. a
  formula whose dependency graph is broken, or one that lost its top-level
  `pour: true`). So `pour_formula` runs the real `bd mol pour` and, on non-zero
  exit, surfaces bd's **verbatim stderr** as "Pour failed: …" (HTTP 500). Pours
  are atomic at the bd layer — a failed pour rolls back to zero new beads, so
  the board is never left with orphans. (Covered by
  `test_pour_surfaces_bd_stderr_on_failure`.)
- **Hidden molecule wrapper / count honesty.** bd's raw `created` count
  includes the molecule wrapper node that bdboard deliberately hides from the
  board (Option A). The result reports `visible_count = created - 1` (floored at
  0) via `_pour_counts` (app.py ~722) so "N beads added" matches what the user
  actually sees.
- **Partial materialization.** If `len(id_mapping) != created`, not every node
  landed — a vapor-pour regression or a formula missing top-level
  `pour: true`. `_pour_counts` returns `fully_materialized=False`, and
  `formula_pour_result.html` renders a warning ("Partial pour … some steps
  did not land … remove the incomplete epic before retrying") instead of
  dressing it up as success. A warning is also logged.
- **Rename failure is non-fatal.** The pour is already atomic and complete; if
  the wrapper rename fails it must not lose the poured beads. The route catches
  it, leaves the beads under the bare formula name, and appends a soft
  parenthetical warning to the success message rather than erroring. (Covered by
  `test_pour_soft_warns_when_rename_fails`.)
- **Graceful degradation on read failures.** `GET /api/formulas` and
  `GET /api/formulas/{name}/form` degrade to friendly inline messages (HTTP 200)
  on a `bd formula list` failure rather than 500-ing the swap — symmetric with
  `/api/memory`. An unknown formula name yields HTTP **404** "No such formula."
  (Covered by `test_api_formulas_degrades_on_bd_failure`,
  `test_api_formula_form_404_for_unknown`.)
- **Formula with no variables** is a valid "pour with no inputs" case, not an
  error: `read_formula_variables` returns `[]` when the `variables` block is
  absent/malformed, and the form shows "This formula takes no variables."
- **Names are URL-encoded** (`name | urlencode` in the templates,
  `name.strip()` server-side) so formula names with spaces survive the round
  trip.
- **Timeouts.** List/form: 8s (`FORMULA_LIST_TIMEOUT_S`). Pour: 30s
  (`POUR_TIMEOUT_S`) — a pour cooks the formula inline and materializes a whole
  bead tree; a timeout returns a "may still be materializing — refresh in a
  moment" message.

## Source files

- `src/bdboard/app.py` — `api_formulas` (~756), `api_formula_form` (~784),
  `api_formula_pour` (~833), `_short_pour_id` (~708), `_pour_counts` (~722),
  `_check_csrf` (~604), `_CSRF_TOKEN` global (~112).
- `src/bdboard/bd.py` — `list_formulas` (~493), `read_formula_variables` (~519),
  `pour_formula` (~570), `rename_bead` (~637); timeouts
  `FORMULA_LIST_TIMEOUT_S` / `POUR_TIMEOUT_S` / `UPDATE_TIMEOUT_S` (~43).
- `src/bdboard/templates/dashboard.html` — the masthead "+ Pour Formula" button,
  the `#formula-dialog` `<dialog>` (picker + form regions), and the
  `openFormulaDialog()` script.
- `src/bdboard/templates/partials/formula_list.html` — the picker cards
  (`hx-get` per formula → swaps the form).
- `src/bdboard/templates/partials/formula_form.html` — the variable form
  (per-variable fields, required markers, CSRF, `hx-post` to pour) and the
  `#formula-pour-result` region.
- `src/bdboard/templates/partials/formula_pour_result.html` — the success /
  partial-pour acknowledgement.
- `tests/test_formula_pour.py` — route coverage (picker, form, CSRF, required
  pre-flight, default fallback, success+rename+broadcast, stderr surfacing,
  rename soft-warn).
- `tests/test_bd_formulas.py` — client coverage (`list_formulas`,
  `read_formula_variables`, `pour_formula` arg-building + error paths).
