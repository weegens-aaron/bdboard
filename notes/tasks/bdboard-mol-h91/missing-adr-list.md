# bdboard-mol-h91 — ADR / decision-coverage check

Date: 2026-06-02
Pass: **5th** docs-validation ADR-coverage check.
Molecule: bdboard-mol-gy6 (`docs-validation gy6`).
Scope: significant architectural/process decisions made in **code + beads**,
cross-referenced against written records in `notes/decisions/` (ADRs) and
`notes/design/<bead-id>/` (design docs + `*-decision.md` files).

> **Lineage.** This re-runs the ADR-coverage check first done in
> `notes/tasks/bdboard-mol-c09/` (2026-05-29), then `bdboard-mol-7up/`
> (2026-05-31), `bdboard-mol-29b/` (2026-06-01), and `bdboard-mol-lon/`
> (2026-06-02). The c09/7up audits found a large missing-ADR backlog
> (written by `bdboard-jdd` → ADRs 0001–0006 + template + index). The 29b
> audit found D1 (ADR 0004 stale). The lon (4th) audit re-found D1 (still
> unfixed) **and** D2 (ADR 0005 stale) and filed both as beads. This pass
> verifies D1/D2 are fixed and diffs the commits since the lon audit
> (`HEAD=7a8bdf5` → current `HEAD=ed74e72`) for new architectural decisions.

## Method

1. Re-inventoried both decision homes:
   - `notes/decisions/` — ADRs 0001–0006 + `0000-template.md` + README index.
   - `notes/design/<bead-id>/` — spikes + `*-decision.md` deliverables.
2. Verified the lon-pass defects (D1/D2) against the **current** ADR text.
3. Diffed every commit since the lon audit and read the bead notes / code
   behind the architecturally significant ones (notably the bdboard-ain
   formula-pour epic shipped via fh8p/ksny/078p/obv + spike 9n4).
4. Verified each ADR against the **current code** it claims to describe
   (`src/bdboard/bd.py`) rather than trusting the ADR's own prose.

## Legend

- **MISSING** — a significant decision with no durable written record at all
  (no ADR; only spike/design/catalog/code/bead notes).
- **STALE** — a written ADR exists but no longer matches the code.
- **COVERED** — verified accurate against the current code, no action.

---

## Headline result

**One new MISSING defect this pass — and it was fixed inline (ADR 0007
written).** The two STALE defects the prior (lon) pass filed are now verified
**COVERED**.

### Verification of prior-pass defects (now fixed)

| Prior defect | Fix commit | Verified |
|---|---|---|
| **D1** — ADR 0004 stale (single unbounded read documented; code is a three-way split) | `7fbd2d6` (bdboard-e3rw) | **COVERED** — ADR 0004 now documents `list_active` / `list_closed` (date-bounded) / `list_closed_history` (count-uncapped). |
| **D2** — ADR 0005 stale (omitted the revision-signature self-feedback-loop guard) | `b8704bf` (bdboard-lvpn) | **COVERED** — ADR 0005 now records the dolt-manifest root-hash skip + the loop it prevents. |

### New defect this pass

**M1 — MISSING ADR: the formula-pour write surface.   [FIXED INLINE → ADR 0007]**

- **The decision (made in code + spike + beads, never in an ADR):** bdboard
  exposes a UI action that **mutates the workspace by creating whole bead
  trees** — it shells out to `bd mol pour <formula> --var k=v … --json`
  (`BdClient.pour_formula`, `src/bdboard/bd.py` ~772), renames the molecule
  wrapper to `<formula> <short-id>`, and lands the tree live via ADR 0005's
  pipeline plus an optimistic broadcast.
- **Why it is ADR-worthy (durable + cross-cutting + non-obvious):** this is the
  **second** write class bdboard allows, and a *categorically larger* one than
  ADR 0006's field-value edits — ADR 0006 explicitly scopes itself to "the
  values of fields that already exist" and **defers** creating beads / shape
  edits. Worse, the pour write path appears to **contradict** ADRs 0004
  ("bdboard never writes to `.beads/`") and 0005 ("one-way observer chain"). A
  contributor reading only the code + those ADRs would find the pour path an
  inconsistency and might "simplify it away." The boundary that makes pour safe
  (goes through the `bd` CLI, never direct file writes; atomic rollback; stderr
  surfaced because `--dry-run` can't catch dependency-graph failures) lived
  **only** in: spike bdboard-9n4
  (`notes/design/bdboard-9n4/formula-to-board-ui-spike.md`), the feature catalog
  `notes/catalog/pour-formula.md`, and code/bead notes (bdboard-ain epic). No
  ADR.
- **Fix (inline, this pass):** wrote
  [`notes/decisions/0007-formula-pour-ui-write-surface.md`](../../decisions/0007-formula-pour-ui-write-surface.md)
  — status accepted — distilling the decision, the rejected alternatives
  (terminal-only / cook-then-pour / `formula show --json` for variables /
  direct `.beads/` writes), and the consequences (bdboard now has **two**
  documented write surfaces; the "read-only observer" framing of 0004/0005 must
  be read as "no direct file writes / no read-loop origination," not "no
  mutation"). Added it to the `notes/decisions/README.md` index, pointed the
  spike and the feature catalog at it (per the design-doc-→-ADR rule). This is
  the same "when in doubt, write the ADR" remedy the `bdboard-jdd` backfill
  applied to the original c09/7up backlog.

---

## COVERED — verified accurate this pass (no action)

| Area (commit / bead) | ADR / record | Verdict |
|---|---|---|
| Runtime three-way split read | ADR 0004 (amended `7fbd2d6`) | **COVERED** (was D1) |
| Live-refresh revision-signature guard | ADR 0005 (amended `b8704bf`) | **COVERED** (was D2) |
| Manual field-value editing (`update_field`) | ADR 0006 | **COVERED** — registry/whitelist/append-only matches code. |
| **Status-lifecycle affordance** (design doc `bdboard-o9v.6`) | ADR 0006 explicitly **defers** it | **COVERED (still deferred)** — there is **no** `update_status` method in `bd.py`; the affordance was designed but **never shipped**, so ADR 0006's deferral remains accurate. **Not a gap.** |
| Board time-window filter moved to toolbar (`bdboard-150t`, `1d11413`) | catalog `board-time-filter.md` | **COVERED** — UI/layout change, not an architectural decision; catalog-documented. |
| Masthead CLOSED stat synced to filter (`bdboard-de4z`); History window preserved across refresh (`bdboard-li44`) | — | Implementation hardening of ADR 0004/0005 pipelines; no new decision. |

---

## Sibling-check note (not this child's deliverable)

The README-accuracy (`bdboard-mol-80i`) and broken-link (`bdboard-mol-r0p`)
checks were also run this pass and found **clean** (see the molecule's bead
notes): `make links` → 0 errors / 119 OK / 3 accepted redirects; README claims
(`src/bdboard/bd.py`, `.github/workflows/code-health.yml`, the Flags table vs
`bdboard --help`, every `make` target) all verified accurate. The
stale-setup-step child (`bdboard-mol-3pk`) fixed the one defect it found (README
quick-start ordering). Those results belong to their own children; recorded here
only for traceability.

---

## Summary — missing-ADR list (the deliverable)

**Defects found this pass:** 1 (M1), **fixed inline.**

1. **M1 — MISSING: the formula-pour write surface had no ADR.** bdboard's
   UI-triggered, workspace-mutating `bd mol pour` capability (bdboard-ain) lived
   only in spike + catalog + code. **Fixed inline by writing ADR 0007** and
   indexing/cross-linking it.

**Resolved / intact since prior audits (no action):** D1 (ADR 0004) and D2
(ADR 0005) from the lon pass are both fixed and verified COVERED; the
c09/7up backlog (ADRs 0001–0006 + template + index) remains intact; ADR 0006's
status-lifecycle deferral remains accurate (affordance never shipped).

> Per project rules this audit does **not** self-close any bead. The one defect
> was fixable inline (write the ADR), so no new bead was filed for it; ADR 0007
> is the deliverable. Evidence is captured in the molecule bead's notes for
> LLM-judge verification.
