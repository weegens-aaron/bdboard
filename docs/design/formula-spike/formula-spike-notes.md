# Spike: bd formulas for repeatable maintenance activities

- **Bead:** bdboard-zda (spike)
- **Status:** spike / notes + recommendation only — **no shipped formulas**
- **Date:** 2026-05-29
- **Timebox:** ~240 min estimate

> Deliverable for bdboard-zda. Documents how `bd` formulas work end-to-end
> (verified empirically against the installed `bd`, not from docs alone),
> sketches two example formulas, assesses fit vs. plain recurring beads vs.
> CI, and recommends adoption + concrete follow-up beads. The two example
> `.formula.json` files live next to this doc as **sketches**, deliberately
> NOT under any `.beads/formulas/` search path — they are not shipped/active.

---

## 1. The Rig → Cook → Run lifecycle (verified)

Formulas are the **source layer** for molecule templates. A formula is a
YAML/JSON file (`<name>.formula.json`) that defines a workflow as a tree of
steps with variables and composition rules. The lifecycle:

| Phase | Command(s) | What happens |
|---|---|---|
| **Rig** | author / `extends` / `compose` / `bd mol bond` | Compose formulas together into a higher-order template. |
| **Cook** | `bd cook <name>` | Transform a formula into a **proto** (the "solid" template). Expands macros, applies aspects, optionally substitutes variables. |
| **Run** | `bd mol pour` / `bd mol wisp` | Instantiate the proto into real work: **pour** = persistent mol (liquid, git-synced); **wisp** = ephemeral mol (vapor, local-only). |

Chemistry metaphor: **formula (recipe) → cook → proto (solid) → pour → mol
(liquid)** or **→ wisp → (vapor)**. Reverse direction is **distill** (epic →
formula) and **squash** (mol execution → digest).

### Search paths (verified via `bd formula --help`)
Resolved in order; first writable wins for `distill` output:
1. `<resolved-beads-dir>/formulas/` (active project)
2. `<checkout-root>/.beads/formulas/` (repo-local)
3. `~/.beads/formulas/` (user)
4. `$GT_ROOT/.beads/formulas/` (orchestrator, if `GT_ROOT` set)

A file must sit in a search path to be referenced **by name**; `bd cook` also
accepts a direct **file path** for ephemeral use.

### Cook modes (verified via `bd cook --help` + live runs)
- **compile-time** (default, `--mode=compile`): keeps `{{variable}}`
  placeholders intact. For modeling / estimation / handoff / planning.
- **runtime** (`--mode=runtime`, or implied when `--var` is passed): fully
  substitutes variables. Requires every variable to resolve (via `--var` or
  a `default`).
- `--persist` writes the proto to the DB (legacy reuse path). Default is
  ephemeral: `pour`/`wisp` cook inline, so pre-cooked protos are usually
  unnecessary.

### Composition primitives (from `bd formula show` / `bd mol bond --help`)
- **`extends`** — inheritance from a base formula.
- **`compose` / bond points** — declare where external formulas can attach.
- **`bd mol bond`** — polymorphic combiner (formula+formula, formula+proto,
  formula+mol, proto+mol, mol+mol). Bond types: `sequential` (default),
  `parallel`, `conditional` (runs only if A fails). Supports a "Christmas
  Ornament" dynamic-bonding pattern for attaching work at runtime.
- **macros / aspects** — applied during cook (cross-cutting expansions).

### Phase hint
A formula may declare `phase: "vapor"`. Pouring a vapor formula prints a
warning recommending `wisp` instead. (Verified: the warning fires on
`bd mol pour` of our `phase:"vapor"` sketch.)

---

## 2. Empirical schema (learned by `bd mol distill` + `bd cook`)

Minimal verified shape:

```json
{
  "formula": "name",
  "description": "...",
  "version": 1,
  "type": "workflow",
  "phase": "vapor",                 // optional: recommends wisp
  "pour": true,                     // optional: see gotcha below
  "variables": {
    "repo": { "description": "...", "default": "bdboard" }
  },
  "steps": [
    { "id": "root", "title": "... {{repo}}", "description": "...",
      "type": "epic", "priority": 2, "labels": ["a","b"] },
    { "id": "child", "title": "...", "type": "task", "priority": 2,
      "labels": ["a"], "depends_on": ["root"] }
  ]
}
```

Verified facts from live cooking of the two sketches:
- `{{var}}` substitution works in `title` and `description` at runtime mode.
- `depends_on` between step `id`s is honored and shows up in the proto.
- `bd cook` rewrites `version` → `schema_version` and injects `source`.
- `bd mol seed <name>` confirms a formula is resolvable from a search path.

### ⚠️ Gotcha (verified, worth a memory): vapor + wisp only pours the root
For a `phase: "vapor"` formula, `bd mol wisp <name> --dry-run` creates **only
the root issue** and prints:
`"N child step(s) skipped — set pour=true in formula to materialize them"`.

- Setting **`pour: true` at the top level** of the formula → wisp materializes
  the **full child tree** (verified: 6 issues vs 1).
- Setting `pour: true` at the **step level** → **ignored** (still root-only).

So a recurring maintenance formula intended to run as a wisp must declare
top-level `pour: true`, or be poured (persistent) instead. This is the single
most surprising behavior found and would silently produce empty audit runs.

---

## 3. Example formula sketches (in this folder, not shipped)

- `code-health-audit.formula.json` — epic root + 4 task children:
  **DRY scan, SOLID review, dead-code sweep, dependency hygiene**. Vars:
  `repo`, `quarter`. Each child carries tool hints (jscpd/rg, vulture/ruff,
  `uv pip list --outdated`/pip-audit) and an expected output line.
- `docs-validation.formula.json` — epic root + 4 task children:
  **README accuracy, stale setup steps, broken-link sweep, ADR coverage**.
  Var: `repo`.

Both were cooked (compile + runtime) and dry-run poured/wisped successfully.

---

## 4. Fit assessment: formula vs. recurring bead vs. CI

| Need | Best tool | Why |
|---|---|---|
| Multi-step human/agent judgment workflow, repeated each cycle | **Formula** | Encodes the whole tree once; one `pour`/`wisp` spawns it with audit-trail beads per finding. |
| A single periodic reminder ("review deps Q2") | **Plain recurring bead** | A formula is overkill for one bead; no tree to template. |
| Deterministic, fast, pass/fail checks (lint, broken links, link check) | **CI** | Should gate every PR, not wait for a cycle. Formulas don't run anything — they only **spawn work**. |

Key limitation: **formulas spawn beads; they do not execute checks.** They are
a *work-templating* mechanism, not a runner. The value is consistency +
audit trail (one bead per finding) for **judgment-heavy** audits. The purely
mechanical sub-checks (broken links, ruff F401 dead imports) belong in CI;
the formula child should be "*review the CI report and triage*," not "*run the
checker*."

Other limitations:
- No scheduling. Something external (cron, a human, an orchestrator) must
  invoke `pour`/`wisp` on a cadence.
- The vapor/`pour:true` gotcha (§2) is a sharp edge.
- Sketches must stay OUT of search paths until intentionally shipped, or
  they pollute `bd formula list` for everyone.

---

## 5. Recommendation

**Adopt formulas — narrowly — for the two judgment-heavy audits**, with the
mechanical sub-checks pushed into CI.

Concrete plan:
1. **Ship `docs-validation` first** (lowest risk, highest signal; docs drift
   is real here). Pour it persistent (audit value), one bead per defect.
2. **Ship `code-health-audit` second**, after wiring the mechanical bits
   (ruff/vulture/jscpd/pip-audit) into CI so the formula children triage CI
   output rather than re-running tools.
3. **Decide a cadence + invoker** (manual quarterly `bd mol pour` to start;
   revisit automation later — do NOT block adoption on a scheduler).
4. **Record the vapor/`pour:true` gotcha as a `bd remember`** so nobody ships
   an empty-root recurring formula.

Where they live: `<repo>/.beads/formulas/` (repo-local, git-synced) once
promoted from these sketches.

---

## 6. Follow-up beads (proposed; link via discovered-from)

1. **Author & ship `docs-validation` formula** into `.beads/formulas/`,
   verify pour, document cadence. (task, P2)
2. **Wire code-health mechanical checks into CI** (ruff F401/dead-code,
   jscpd duplication, pip-audit) before shipping the audit formula. (task, P2)
3. **Author & ship `code-health-audit` formula** once CI checks exist;
   children triage CI output. (task, P2, depends on #2)
4. **Decide cadence + invoker** for recurring audits (manual vs. automated).
   (task, P3)
