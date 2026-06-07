#!/usr/bin/env python3
"""One-shot scaffolder: seed the 9 capability-area section stubs for bdboard.

Run once from the bdboard repo root. Idempotent: skips files that already have
findings (size grown past the seed). This script exists so the scaffold is
reproducible and the 9 stubs stay DRY-identical to the template's shape.

Mirrors the bead-chain precedent
(`../../../.code_puppy/plugins/bead_chain/notes/analysis/bead-chain-coverage/_scaffold.py`)
but reframes the LEVERAGED axis to REFLECTED: bdboard is a DISPLAY tool, so the
audit asks what each area's bead state bdboard SHOWS, citing src/bdboard/*.py,
templates/partials/*.html, and notes/catalog/*.md.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path("notes/analysis/bdboard-coverage")

# (num, slug, title, fg_chapter_file, fg_chapter_num, bead, sources)
AREAS = [
    (
        "01",
        "anatomy",
        "Anatomy of a Bead",
        "field-guide-01-anatomy-of-a-bead.html",
        1,
        "bdboard-cnzi",
        "`templates/partials/field_row.html`, `bead_modal.html`, "
        "`bead_card.html`; `src/bdboard/bd.py`; `notes/catalog/bead-modal.md`",
    ),
    (
        "02",
        "dependency-graph",
        "Dependency Graph",
        "field-guide-02-dependency-graph.html",
        2,
        "bdboard-vhke",
        "`src/bdboard/derive/lanes.py`; `templates/partials/field_row.html`, "
        "`bead_modal.html`; `notes/catalog/bead-modal.md`",
    ),
    (
        "03",
        "status-lifecycle",
        "Status Lifecycle",
        "field-guide-03-status-lifecycle.html",
        3,
        "bdboard-2w9b",
        "`src/bdboard/derive/lanes.py`; `templates/partials/lanes.html`, "
        "`closed_lane.html`, `counts.html`; `notes/catalog/board-lanes.md`",
    ),
    (
        "04",
        "memories-recall",
        "Memories & Recall",
        "field-guide-04-memories-and-recall.html",
        4,
        "bdboard-hdol",
        "`templates/memory.html`, `templates/partials/memory_list.html`; "
        "`src/bdboard/app.py`, `bd.py`; `notes/catalog/memory-list.md`",
    ),
    (
        "05",
        "formulas-molecules",
        "Formulas & Molecules",
        "field-guide-05-formulas-and-molecules.html",
        5,
        "bdboard-whjh",
        "`templates/partials/formula_form.html`, `formula_list.html`, "
        "`formula_pour_result.html`; `src/bdboard/app.py`, `bd.py`; "
        "`notes/catalog/pour-formula.md`",
    ),
    (
        "06",
        "gates-coordination",
        "Gates & Coordination",
        "field-guide-06-gates-and-coordination.html",
        6,
        "bdboard-6yvg",
        "`src/bdboard/derive/lanes.py`; `templates/partials/field_row.html`, "
        "`bead_card.html`; `notes/catalog/board-lanes.md`",
    ),
    (
        "07",
        "swarms",
        "Swarms",
        "field-guide-07-swarms.html",
        7,
        "bdboard-6ljg",
        "`templates/partials/field_row.html`, `bead_modal.html`; "
        "`src/bdboard/bd.py`; `notes/catalog/bead-modal.md`",
    ),
    (
        "08",
        "data-layer",
        "Data Layer (Dolt)",
        "field-guide-08-data-layer.html",
        8,
        "bdboard-svbo",
        "`src/bdboard/store.py`, `watcher.py`, `events.py`, `app.py`; "
        "`notes/catalog/sse-live-refresh.md`, `store-cache.md`",
    ),
    (
        "09",
        "quality-hygiene",
        "Quality & Hygiene",
        "field-guide-09-quality-and-hygiene.html",
        9,
        "bdboard-rohn",
        "`src/bdboard/bd.py`, `derive/lanes.py`; "
        "`templates/partials/counts.html`, `bead_audit.html`; "
        "`notes/catalog/board-counts.md`, `bead-audit.md`",
    ),
]

SEED = """# {title} — Coverage Findings

> Seeded stub. Fill from `_template.md`. Owner bead: {bead}.
> Field-guide chapter: `{fg}` (chapter {ch}).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `{slug}`                                       |
| Field-guide ref  | `{fg}` (chapter {ch})                          |
| bdboard owner    | `{bead}`                                       |
| Primary sources  | {sources}                                      |
| Status           | `not-started`                                  |

---

## 1. AVAILABLE — what the field guide documents

_TODO ({bead}): summarize the bd 1.0.4 feature surface for this area, citing
`{fg}` § "<section>"._

## 2. REFLECTED — what bdboard actually displays

_TODO ({bead}): what bdboard SHOWS the user, with `file:line` citations into
`src/bdboard/*.py`, `templates/partials/*.html`, and `notes/catalog/*.md`. State
explicitly anything that is NOT reflected._

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | _TODO_         | _Px_     | _TODO_                           |

### Severity rubric (DISPLAY tool)

| Sev | Meaning                                                                                                          |
| --- | -------------------------------------------------------------------------------------------------------------- |
| P0  | Display misrepresents bead state so a user decides wrong (e.g. blocked shown as Ready; reversed dependency direction — cf. `bdboard-fjk`). |
| P1  | A board-meaning concept is silently wrong or absent (e.g. a status that has no lane; a gate bead shown as plain work). |
| P2  | A capability is unsurfaced where showing it would materially improve fidelity.                                |
| P3  | Minor; narrow impact or workaround exists.                                                                    |
| P4  | Cosmetic / future-proofing only.                                                                             |

---

## Notes / open questions

_None yet._
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for num, slug, title, fg, ch, bead, sources in AREAS:
        path = OUT / f"{num}-{slug}.md"
        body = SEED.format(title=title, slug=slug, fg=fg, ch=ch, bead=bead, sources=sources)
        if path.exists() and len(path.read_text()) > len(body) + 200:
            print(f"skip (has findings): {path}")
            continue
        path.write_text(body)
        print(f"wrote: {path}")


if __name__ == "__main__":
    main()
