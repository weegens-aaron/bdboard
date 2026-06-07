# Gates & Coordination — Coverage Findings

> Seeded stub. Fill from `_template.md`. Owner bead: bdboard-6yvg.
> Field-guide chapter: `field-guide-06-gates-and-coordination.html` (chapter 6).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `gates-coordination`                                       |
| Field-guide ref  | `field-guide-06-gates-and-coordination.html` (chapter 6)                          |
| bdboard owner    | `bdboard-6yvg`                                       |
| Primary sources  | `src/bdboard/derive/lanes.py`; `templates/partials/field_row.html`, `bead_card.html`; `docs/catalog/board-lanes.md`                                      |
| Status           | `not-started`                                  |

---

## 1. AVAILABLE — what the field guide documents

_TODO (bdboard-6yvg): summarize the bd 1.0.4 feature surface for this area, citing
`field-guide-06-gates-and-coordination.html` § "<section>"._

## 2. REFLECTED — what bdboard actually displays

_TODO (bdboard-6yvg): what bdboard SHOWS the user, with `file:line` citations into
`src/bdboard/*.py`, `templates/partials/*.html`, and `docs/catalog/*.md`. State
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
