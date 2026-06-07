# Quality & Hygiene — Coverage Findings

> Seeded stub. Fill from `_template.md`. Owner bead: bdboard-rohn.
> Field-guide chapter: `field-guide-09-quality-and-hygiene.html` (chapter 9).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `quality-hygiene`                                       |
| Field-guide ref  | `field-guide-09-quality-and-hygiene.html` (chapter 9)                          |
| bdboard owner    | `bdboard-rohn`                                       |
| Primary sources  | `src/bdboard/bd.py`, `derive/lanes.py`; `templates/partials/counts.html`, `bead_audit.html`; `docs/catalog/board-counts.md`, `bead-audit.md`                                      |
| Status           | `not-started`                                  |

---

## 1. AVAILABLE — what the field guide documents

_TODO (bdboard-rohn): summarize the bd 1.0.4 feature surface for this area, citing
`field-guide-09-quality-and-hygiene.html` § "<section>"._

## 2. REFLECTED — what bdboard actually displays

_TODO (bdboard-rohn): what bdboard SHOWS the user, with `file:line` citations into
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
