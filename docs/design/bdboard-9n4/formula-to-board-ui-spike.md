# Spike: UI for adding formula beads to the board (mechanism + epic naming)

- **Bead:** bdboard-9n4 (spike)
- **Epic:** bdboard-ain — Add beads to the board from a formula via a UI element
- **Status:** spike / recommendation only — **no shipped UI under this bead**
- **Date:** 2026-05-29

> Deliverable for bdboard-9n4. De-risks the formula-to-board capability by
> determining, **empirically against the installed bd**, exactly how bdboard
> should (a) enumerate formulas + their variables, (b) pour a formula and land
> its beads on the board live, and (c) create/name the grouping epic
> `<formula name> <short unique id>`. All findings below were verified in a
> throwaway `bd init` workspace (`/tmp/bd-spike-9n4`, since deleted) so the real
> board was never polluted.

---

## TL;DR recommendation

1. **Pour mechanism:** shell out to `bd mol pour <formula> --var k=v ... --json`
   (pour cooks inline — no separate `bd cook` step needed). Parse the JSON
   result (`new_epic_id`, `id_mapping`, `created`). Serialize on the existing
   `BdClient._subprocess_gate`. New beads reach the board via the **existing**
   watchfiles → `Store.refresh` → SSE `beads_changed` pipeline; additionally
   fire an optimistic `bus.broadcast("beads_changed")` like the memory route so
   the acting user sees the result without waiting for the file-watch debounce.
2. **Variable enumeration:** read the formula's `variables` map by **parsing
   the `*.formula.json` file directly** (path comes from `bd formula list
   --json` → `source`). Do **not** rely on `bd formula show --json` (it omits
   `variables` entirely) or on the `vars` count in `bd formula list --json`
   (it is wrong — reports `0` even when variables exist). Render an HTMX form:
   one field per variable, `description` as the label/help, `default` as the
   prefilled value/placeholder.
3. **Epic naming:** `bd mol pour` auto-creates a `molecule`-typed **wrapper**
   node titled with the bare formula name; its id is the returned
   `new_epic_id`. bdboard generates a short unique id and renames the wrapper
   via `bd update <new_epic_id> --title "<formula> <id>"`. The unique id is
   generated **by bdboard wrapping the pour**, not by the formula (formulas are
   static templates; re-pours must yield distinct epics).
4. **Sharp edges found** (details below): the vapor/`pour:true` gotcha (already
   handled by both shipped formulas); a **real pour-blocking bug in both
   shipped formulas** that `--dry-run` does NOT catch (filed separately); the
   grouping node is type `molecule`, not `epic`, so it will NOT appear in the
   epic strip without a derive change; pour is atomic (failed pour rolls back
   to zero issues — safe for the UI); missing required vars fail fast with a
   clear message.

---

## 1. Pour mechanism (verified)

### 1.1 Command
`bd mol pour <formula-name> --var key=value [--var ...] --json`

Pour **cooks the formula inline**, so there is no need to `bd cook` first or
to pre-persist a proto. With `--json` the command prints a machine-readable
result:

```json
{
  "attached": 0,
  "created": 4,
  "id_mapping": {
    "spike-min":         "bd-...-mol-u72",   // molecule wrapper
    "spike-min.root":    "bd-...-mol-8pz",   // epic root step
    "spike-min.child-a": "bd-...-mol-5x2",
    "spike-min.child-b": "bd-...-mol-dml"
  },
  "new_epic_id": "bd-...-mol-u72",            // == the molecule wrapper id
  "phase": "liquid",
  "schema_version": 1
}
```

Key facts:
- `new_epic_id` is the **molecule wrapper** node (the `<formula>` key in
  `id_mapping`), which is the single parent of everything the pour created.
- `id_mapping` maps `formula.stepId` → real bead id, so bdboard can locate any
  individual node (e.g. the epic-typed root step) deterministically.
- `created` is the total node count (wrapper + steps).

### 1.2 Where it fits in bdboard
`src/bdboard/bd.py` already has the right shapes:
- `_run_mutate(...)` for fire-and-check mutations (remember/forget/update).
- `_run_json(...)` for JSON reads.

Pour needs a **hybrid**: a mutation that ALSO returns parsed JSON. Recommended
new method `BdClient.pour_formula(name, variables) -> dict`:
- build `["mol", "pour", name, *("--var", f"{k}={v}") ..., "--json"]`
- run under `_subprocess_gate` (bd's embedded dolt is single-writer)
- on non-zero exit, surface bd's stderr (same pattern as `_run_mutate`)
- parse stdout JSON, return it
- then `invalidate_caches()` and let the route broadcast SSE.

### 1.3 Live board update
No new plumbing required. The pour writes to `.beads/`, the existing
`watchfiles` recursive watch on `.beads/` fires, `Store.refresh` re-runs
`bd list --all`, and SSE broadcasts `beads_changed`. The route should ALSO
do an optimistic `await bus.broadcast("beads_changed")` (mirrors
`api_memory_create`) so the acting tab refreshes immediately rather than
waiting on the file-watch debounce.

---

## 2. Variable enumeration for the UI (verified — with caveats)

### 2.1 Listing formulas
`bd formula list --json` →
```json
[{ "name": "...", "type": "workflow", "description": "...",
   "source": "/abs/path/....formula.json", "steps": 5, "vars": 0 }]
```
Use this for the **picker** (name + description). `source` is the absolute path
to the formula file — this is the reliable hook for step 2.2.

> ⚠️ **`vars` is unreliable.** It reported `0` for `code-health-audit` and
> `docs-validation` even though both declare `variables` (`repo`, `quarter`).
> Do NOT use it to decide whether to show a variable form.

### 2.2 Getting variables + defaults + help text
**`bd formula show <name> --json` does NOT include the `variables` block.**
Verified keys: `description, formula, pour, schema_version, source, steps,
type, version` — no `variables`. The non-JSON `bd formula show` help claims it
displays variables, but the JSON payload omits them.

➡️ **Recommendation: parse the formula JSON file directly** (path from
`source` in §2.1). The on-disk schema is:
```json
"variables": {
  "repo":    { "description": "Repo or package under audit", "default": "bdboard" },
  "quarter": { "description": "Audit period label",          "default": "this-cycle" }
}
```
Render one form field per key: `description` → label/help, `default` →
prefilled value (and mark "required" when there is no `default`, see §4.4).

> bdboard already treats the bd CLI JSON as the runtime source of truth and
> avoids reading `.beads/issues.jsonl`. Reading `*.formula.json` is a *different*
> file (a static template, not the issue store), and bd itself exposes its
> absolute path via the CLI, so this stays consistent with the architecture: we
> still discover *via the CLI*, we just read the template file the CLI points us
> to. If a future bd release adds `variables` to `formula show --json`, switch
> to that and drop the file read.

---

## 3. Epic naming: `<formula name> <short unique id>` (verified)

### 3.1 What pour actually creates
A single pour of a formula whose root step is `type: epic` creates **three
kinds of node**:

| Node            | issue_type | title source            | role                         |
|-----------------|------------|-------------------------|------------------------------|
| wrapper         | `molecule` | bare formula name       | `new_epic_id`; parent of all |
| root step       | `epic`     | the root step's `title` | the formula's own epic       |
| children        | `task`     | each step's `title`     | the work                     |

All non-wrapper nodes hang off the wrapper via a **`parent-child`** dependency
(`depends_on_id = new_epic_id`).

### 3.2 Where the unique id comes from
- bd's pour already mints **globally unique** bead ids (e.g. `...-mol-u72`), so
  collisions are not a real risk — but the *title* still needs a human-readable
  disambiguator so two pours of the same formula are distinguishable on the
  board.
- **Recommendation: bdboard generates the short id and renames the wrapper.**
  After pour, `bd update <new_epic_id> --title "<formula> <id>"`. Verified that
  renaming the `molecule` wrapper works.
- Suggested id scheme: a short, URL/title-safe token — e.g. 6 chars of
  Crockford base32 from `secrets.token_bytes`, or simply reuse the unique
  suffix bd already assigned to `new_epic_id` (e.g. take the segment after the
  last `-`). Reusing bd's own suffix is the **lowest-risk, zero-new-entropy**
  option and is already collision-free; a freshly generated token is fine too.
  Either way the id is generated by **bdboard wrapping the pour**, never baked
  into the formula (formulas are reusable templates).

### 3.3 ⚠️ The grouping node is a `molecule`, not an `epic`
`src/bdboard/derive/lanes.py::_is_epic` matches only
`issue_type == "epic"`. The pour's grouping wrapper (`new_epic_id`) is
`issue_type == "molecule"`, so **it will not appear in the epic strip** — it
will fall through `lanes()` and render as a normal card in the `ready` lane.
Meanwhile the formula's *root step* IS an `epic` and DOES show in the strip,
but its title is the step title (e.g. "Code-health audit: bdboard (Q2-2026)"),
not `<formula> <id>`.

This is the single most important UI design decision the implementation must
resolve. Two viable options (defer the choice to the impl bead):
- **A)** Rename the **epic root step** (locate via `id_mapping["<formula>.<rootStep>"]`,
  or find the lone `issue_type==epic` child of the wrapper) to `<formula> <id>`.
  Pro: shows in the epic strip with zero derive changes. Con: a redundant
  `molecule` wrapper card still floats in the ready lane.
- **B)** Teach `_is_epic` (and the epic strip) to also surface `molecule`
  wrapper nodes, and rename the wrapper. Pro: the wrapper is the true single
  parent. Con: touches derive + templates + their contrast/derive tests.

Recommended starting point: **Option A** (smallest, test-light change), and
file a follow-up to consider hiding the bare molecule wrapper from the lanes.

---

## 4. Sharp edges & error handling (all verified)

### 4.1 vapor / `pour:true` (known memory: formula-vapor-pour-gotcha)
A `phase:"vapor"` formula materializes only the root unless **top-level**
`pour:true` is set (step-level `pour:` is ignored). Both shipped formulas
already set top-level `pour:true`, so the full tree materializes. No action for
this spike beyond surfacing it.

### 4.2 🐛 REAL BUG: both shipped formulas fail to pour (dry-run lies)
`bd mol pour code-health-audit --var repo=x --var quarter=y --dry-run` happily
reports *"would pour 6 issues"*, but the **real** pour fails:
```
Error: pouring proto: failed to create dependency: tasks can only block other tasks, not epics
```
Root cause: the children declare `depends_on: ["audit-root"]` where
`audit-root` is `type: epic`. bd materializes `depends_on` as a **blocks**
edge, and bd rejects a task→epic blocks edge. `docs-validation` has the
identical shape and the identical failure. A minimal formula using
`parent: "root"` (parent-child) instead of `depends_on: ["root"]` poured
cleanly (4 issues). **`--dry-run` does not exercise dependency creation, so it
cannot catch this** — the UI must surface the real pour's stderr, not trust a
dry-run preview. Filed as a separate (non-blocking) bug; both formulas need
`depends_on:[root-epic]` → `parent:root`.

### 4.3 Pour is atomic (good for the UI)
After the failed pour in §4.2, `bd list --all` returned **0 issues** — the
partial tree was rolled back. So a failed pour will not leave orphan beads on
the board. The UI can treat pour as all-or-nothing.

### 4.4 Variable validation
- Missing a variable that has **no default** → pour exits non-zero:
  `Error: missing required variables: <name>` + a hint. bdboard should
  pre-validate (mark no-default vars required in the form) AND still surface
  bd's stderr as a fallback.
- An **unknown** `--var` is silently ignored (no error). Harmless; bdboard
  should only send vars it parsed from the formula anyway.

### 4.5 Error surfacing pattern
Reuse the memory route's pattern: catch `RuntimeError`, return an HTMX partial
with `role="alert"` and bd's stderr, non-2xx status. Never let a pour failure
corrupt or blank the board (the existing Store cache-fallback already guards
the list render).

---

## 5. Concrete recommendation (for epic bdboard-ain)

A minimal, test-light first cut:
1. **`BdClient.pour_formula(name, vars)`** — JSON-returning mutation under the
   subprocess gate; surfaces stderr; invalidates caches (§1.2).
2. **`BdClient.list_formulas()` + `read_formula_variables(source)`** — list via
   `bd formula list --json`; variables by parsing the `source` file (§2).
3. **Routes** — `GET /api/formulas` (picker), `GET /api/formulas/{name}/form`
   (variable form from parsed file), `POST /api/formulas/{name}/pour` (CSRF-
   checked; pour → rename wrapper/epic to `<formula> <id>` → optimistic SSE).
4. **Epic naming** — generate short id in bdboard, `bd update <id> --title`
   (§3.2); pick Option A vs B for which node carries the name (§3.3).
5. **Pre-flight** — block the pour button until required (no-default) vars are
   filled; still surface bd stderr on failure (§4.4/4.5).

Out of scope here (filed as follow-ups): the actual UI build, the
`molecule`-vs-`epic` strip decision, and fixing the two broken formulas.

---

## 6. Follow-up beads (filed, wired discovered-from this spike)

See the bead's notes for the exact ids. In summary:
1. **(impl, under bdboard-ain)** Build the formula-pour UI per §5 (picker +
   variable form + pour route + epic rename + live refresh).
2. **(impl, under bdboard-ain)** Decide & implement how the grouping node shows
   on the board (Option A rename epic step vs Option B surface molecule
   wrappers) — §3.3.
3. **(bug, non-blocking)** Both shipped formulas fail to pour due to
   `depends_on:[root-epic]`; switch to `parent:root`. `--dry-run` does not
   catch it — §4.2.