# bdboard Display-Fidelity Coverage Analysis

**Epic:** `bdboard-gnhi` — Audit bdboard fidelity to the bd feature surface.

**The question:** bdboard is a general-purpose, read-mostly FastAPI + HTMX
dashboard that any developer can point at **any** bd workspace. The beads
**field guide** (`../../../training/beads/docs`, 9 chapters) documents the full
bd 1.0.4 feature surface. For each capability area we ask:

1. **AVAILABLE** — what does the field guide say bd offers? *(chapter ref)*
2. **REFLECTED** — what does bdboard actually **display**? *(source `file:line`
   into `src/bdboard/*.py`, `templates/partials/*.html`, `docs/catalog/*.md`)*
3. **GAPS** — what's misrepresented or unshown, with a P0–P4 severity and a
   one-line follow-up.

> **REFLECTED replaces the precedent's LEVERAGED.** bead-chain is a *driver* —
> it asked what bd features it *consumes*. bdboard is a *display* — it asks what
> bd state it *shows the user*. The axis name reflects that: fidelity is about
> accurate reflection of bead state, not feature consumption.

Every section is filled from [`_template.md`](./_template.md). The final
synthesis (`bdboard-bk1r`) is a **mechanical merge** of the GAPS tables plus the
matrix below — no new analysis, just consolidation. The prioritized, deduped
issues-and-gaps breakdown will live in **`GAPS.md`** (produced by the synthesis
bead).

## Where findings live

```
notes/analysis/bdboard-coverage/
├── README.md          ← you are here (index + matrix skeleton)
├── _template.md       ← the per-section shape (underscore = not a finding)
├── _scaffold.py       ← one-shot idempotent seeder for the 9 stubs
├── 01-anatomy.md
├── 02-dependency-graph.md
├── 03-status-lifecycle.md
├── 04-memories-recall.md
├── 05-formulas-molecules.md
├── 06-gates-coordination.md
├── 07-swarms.md
├── 08-data-layer.md
└── 09-quality-hygiene.md
```

## The 9 capability areas

| #   | Capability area      | Section file                                             | Field-guide chapter                              | Audit bead     |
| --- | -------------------- | ------------------------------------------------------- | ------------------------------------------------ | -------------- |
| 1   | Anatomy of a bead    | [`01-anatomy.md`](./01-anatomy.md)                      | `field-guide-01-anatomy-of-a-bead.html`          | `bdboard-cnzi` |
| 2   | Dependency graph     | [`02-dependency-graph.md`](./02-dependency-graph.md)    | `field-guide-02-dependency-graph.html`           | `bdboard-vhke` |
| 3   | Status lifecycle     | [`03-status-lifecycle.md`](./03-status-lifecycle.md)    | `field-guide-03-status-lifecycle.html`           | `bdboard-2w9b` |
| 4   | Memories & recall    | [`04-memories-recall.md`](./04-memories-recall.md)      | `field-guide-04-memories-and-recall.html`        | `bdboard-hdol` |
| 5   | Formulas & molecules | [`05-formulas-molecules.md`](./05-formulas-molecules.md)| `field-guide-05-formulas-and-molecules.html`     | `bdboard-whjh` |
| 6   | Gates & coordination | [`06-gates-coordination.md`](./06-gates-coordination.md)| `field-guide-06-gates-and-coordination.html`     | `bdboard-6yvg` |
| 7   | Swarms               | [`07-swarms.md`](./07-swarms.md)                        | `field-guide-07-swarms.html`                     | `bdboard-6ljg` |
| 8   | Data layer (Dolt)    | [`08-data-layer.md`](./08-data-layer.md)                | `field-guide-08-data-layer.html`                 | `bdboard-svbo` |
| 9   | Quality & hygiene    | [`09-quality-hygiene.md`](./09-quality-hygiene.md)      | `field-guide-09-quality-and-hygiene.html`        | `bdboard-rohn` |

## Capability matrix (filled by the synthesis bead `bdboard-bk1r`)

`Reflected?` = Full / Partial / None. `Top gap sev` = highest P0–P4 in section.
`Gap count` = actionable gaps recorded in that section (cross-ref/disproven rows
noted in parentheses). The prioritized, deduped breakdown lives in `GAPS.md`.

| #   | Capability area      | Available? | Reflected? | Top gap sev | Gap count | One-line headline |
| --- | -------------------- | ---------- | ---------- | ----------- | --------- | ----------------- |
| 1   | Anatomy of a bead    | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 2   | Dependency graph     | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 3   | Status lifecycle     | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 4   | Memories & recall    | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 5   | Formulas & molecules | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 6   | Gates & coordination | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 7   | Swarms               | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 8   | Data layer (Dolt)    | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |
| 9   | Quality & hygiene    | _TODO_     | _TODO_     | _Px_        | _N_       | _TODO_            |

## Severity rubric (reframed for a DISPLAY tool)

bead-chain's rubric judged correctness in a *drain loop*. bdboard never drives
work — its failure mode is **misleading the human reading the board**. So the
severity scale is reframed around what a wrong/absent display causes:

| Sev | Meaning                                                                                                          |
| --- | -------------------------------------------------------------------------------------------------------------- |
| P0  | Display **misrepresents** bead state so a user decides wrong (e.g. a blocked bead shown as Ready; a reversed dependency direction — cf. `bdboard-fjk`). |
| P1  | A board-meaning concept is **silently wrong or absent** (e.g. a status that has no lane; a gate bead shown as plain work). |
| P2  | A capability is **unsurfaced** where showing it would materially improve fidelity.                            |
| P3  | Minor; narrow impact or a workaround exists.                                                                  |
| P4  | Cosmetic / future-proofing only.                                                                             |

## How to fill a section (for audit beads)

1. Open the matching `NN-<area>.md` stub (already seeded from the template).
2. Read your field-guide chapter (the HTML files in `../../../training/beads/docs`)
   for **AVAILABLE**.
3. Read the listed bdboard sources for **REFLECTED** — cite `file:line` into
   `src/bdboard/*.py`, `templates/partials/*.html`, and `docs/catalog/*.md`.
4. Record every **GAP** with a P0–P4 severity and a one-line follow-up.
5. Flip the section's `Status` to `done`. Do **not** touch other sections.

## Source map (bdboard sources per area)

These are starting points, not an exhaustive list — follow the code. Paths are
relative to the repo root unless noted. Catalog docs (`docs/catalog/*.md`) are
the existing feature documentation the audit reads from.

| Area                 | bdboard sources (display surface)                                                                                                            |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Anatomy              | `templates/partials/field_row.html`, `bead_modal.html`, `bead_card.html`, `bead_priority_badge.html`; `src/bdboard/bd.py`; `docs/catalog/bead-modal.md`, `bead-inline-edit.md`, `bead-raw.md` |
| Dependency graph     | `src/bdboard/derive/lanes.py`; `templates/partials/field_row.html`, `bead_modal.html`; `docs/catalog/bead-modal.md`, `board-lanes.md`       |
| Status lifecycle     | `src/bdboard/derive/lanes.py`; `templates/partials/lanes.html`, `closed_lane.html`, `counts.html`; `docs/catalog/board-lanes.md`, `board-closed-lane.md`, `board-counts.md` |
| Memories & recall    | `templates/memory.html`, `templates/partials/memory_list.html`; `src/bdboard/app.py`, `bd.py`; `docs/catalog/memory-list.md`, `memory-create.md`, `memory-delete.md` |
| Formulas & molecules | `templates/partials/formula_form.html`, `formula_list.html`, `formula_pour_result.html`; `src/bdboard/app.py`, `bd.py`; `docs/catalog/pour-formula.md` |
| Gates & coordination | `src/bdboard/derive/lanes.py`; `templates/partials/field_row.html`, `bead_card.html`; `docs/catalog/board-lanes.md`                         |
| Swarms               | `templates/partials/field_row.html`, `bead_modal.html`; `src/bdboard/bd.py`; `docs/catalog/bead-modal.md`                                   |
| Data layer (Dolt)    | `src/bdboard/store.py`, `watcher.py`, `events.py`, `app.py`; `docs/catalog/sse-live-refresh.md`, `store-cache.md`                           |
| Quality & hygiene    | `src/bdboard/bd.py`, `derive/lanes.py`; `templates/partials/counts.html`, `bead_audit.html`; `docs/catalog/board-counts.md`, `bead-audit.md` |
