# Maintainer Docs Validation Scorecard (`__docs/`) vs FlowDoc Rubric

> **Bead:** bdboard-30vz (Validate regenerated maintainer docs against rubric)
> **Epic:** bdboard-uyt1 · **Milestone:** bdboard-bivn
> **Rubric:** [`notes/tasks/bdboard-pf4f/flowdoc-rubric.md`](../bdboard-pf4f/flowdoc-rubric.md)
> **Candidate:** `__docs/` (maintainer family, **M**) — finalized by bdboard-mol-4ik
> **Reference:** the `flowdoc` agent gold output under `~/rep_engineer_station/docs/<service>/`
> **Validator:** code-puppy-8e2379 · objective re-runnable checks (see Method)

## Verdict

**FAITHFUL — fidelity_pct = 100% · all 6 maintainer gates PASS.**

No gate violations, no negative deltas vs the agent reference. The maintainer
doc set matches reference quality; **no further tightening of the maintainer
family is justified by this rubric pass.** The structural root cause the audit
flagged (GAP-0: the `flowdoc` skill does not exist on disk, so template fidelity
had no carrier) is closed in the output: `__docs/_FlowDocGuide.md` now carries
the verbatim templates (Feature/Flow/Endpoint/View/Concept) as the sole fidelity
carrier, and every item doc conforms to it.

## Method (re-runnable)

All checks run from repo root against `__docs/`:

| Check | Command (abridged) | Result |
|-------|--------------------|--------|
| Item-file ↔ manifest parity | `find __docs -name '*.md' ! -name 'index.md' ! -name '_*.md' ! -name 'Architecture.md' ! -name 'Troubleshooting.md' \| wc -l` vs `grep -cE '^- \[x\]' __docs/_Manifest.md` | **25 == 25** |
| Cross-link integrity (L1/N2/MF4) | Python walk of every `[text](path)` in `__docs/**/*.md`, resolve relative to file | **682 links / 0 broken** |
| Unfilled tokens (E1) | `grep -rnE '\{placeholder\}\|path/to/\|TODO\|TBD\|XXX\|NNN'` (route params `{id}` excluded as legitimate) | **0 real tokens** |
| Impl-map path reality (E2) | extract every `src/bdboard/...py\|.html` ref, test `-f` | **37/37 exist** |
| Mermaid presence (E4) | `grep -c '```mermaid'` per item doc | **≥1 in every item doc** (Architecture & Views: 2) |
| Callouts (E5) | `grep -rE '> \[!(WARNING\|NOTE\|TIP\|CAUTION\|IMPORTANT)\]'` | **139 callouts** |
| Template completeness (T1/T2) | header diff of Architecture + sampled Feature/Flow vs `_FlowDocGuide.md` | **exact section match** |

## Scorecard (M family — H1–H4 and E3 are not applicable to maintainer markdown)

| Dim | Weight | Gate | Reference | Candidate | Delta | Note |
|-----|--------|------|-----------|-----------|-------|------|
| S1 Correct output dir | 2 | Y | 2 | 2 | 0 | `__docs/` (double underscore), `index.md` at root |
| S2 Required top-level files | 2 | Y | 2 | 2 | 0 | index.md, Architecture.md, _Manifest.md, Troubleshooting.md all present |
| S3 Section subdirs + index | 2 | - | 2 | 2 | 0 | Features/ Flows/ Endpoints/ Views/ Concepts/, each with index.md |
| S4 One item per file, no orphans | 1 | - | 2 | 2 | 0 | 25 manifest items ↔ 25 backing files |
| MF1 Progress block | 1 | - | 2 | 2 | 0 | Total 25 / Done 25 / Remaining 0 reconciles |
| MF2 Grouped sections | 1 | - | 2 | 2 | 0 | Features/Flows/Endpoints/Views/Concepts |
| MF3 Stable ID numbering | 1 | - | 2 | 2 | 0 | banded 001+ / 010+ / 050+ / 060+ / 080+ |
| MF4 Checkbox + arrow-link line format | 2 | Y | 2 | 2 | 0 | every `- [x] NNN \| Type: Name -> [Link](Path)`; all targets resolve |
| T1 Architecture completeness | 2 | - | 2 | 2 | 0 | Quick Start, Tech Stack, System Diagram, Features-at-a-Glance, Key Flows, External Deps, Directory Guide, API Surface, Views |
| T2 Per-item template sections | 2 | - | 2 | 2 | 0 | Feature/Flow/Endpoint/View/Concept docs match `_FlowDocGuide.md` verbatim in shape |
| T3 Troubleshooting finalized | 1 | - | 2 | 2 | 0 | Troubleshooting.md (10.3 KB) Symptom→Cause→Fix, not a stub |
| E1 No unfilled template tokens | 2 | Y | 2 | 2 | 0 | only legitimate route params `{id}`/`{bead_id}` remain |
| E2 Concrete impl maps | 2 | - | 2 | 2 | 0 | 37/37 referenced `src/bdboard/...` paths exist on disk |
| E4 Diagrams where templated | 1 | - | 2 | 2 | 0 | mermaid in every item doc |
| E5 Callouts | 1 | - | 2 | 2 | 0 | 139 GFM callouts |
| N1 PascalCase filenames | 1 | - | 2 | 2 | 0 | `SwimLaneBoard.md`, `Features/` etc. |
| N2 Manifest link↔file parity | 2 | Y | 2 | 2 | 0 | covered by 0-broken link sweep |
| L1 Cross-link integrity | 2 | Y | 2 | 2 | 0 | 682/0 broken |
| L2 Bidirectional Related | 1 | - | 2 | 2 | 0 | Related sections present and resolve both ways (spot-checked) |
| C1 Features-not-files framing | 1 | - | 2 | 2 | 0 | docs lead with behavior, file-second |
| C2 Consistent voice | 1 | - | 2 | 2 | 0 | maintainer-explanatory throughout |

### Math

- Applicable dims: 21 (E3 + H1–H4 excluded as user/HTML-only).
- `weighted_score = sum(score*weight) = sum(2*weight)` → equals `weighted_maximum`.
- **fidelity_pct = 100%.** Gates (S1, S2, MF4, E1, N2, L1) all score 2 → no gate failure.
- Band: **Faithful (≥ 90)**.

## Audit-gap closure (residuals)

The audit (bdboard-6ucx → bdboard-2omf) surfaced one cross-cutting structural gap:

- **GAP-0 — missing `flowdoc` skill carrier.** *Closed in output.* `_FlowDocGuide.md`
  inlines the full templates (the audit-prescribed fix), and every item doc
  conforms section-for-section. No residual.

**Residual deltas: none.** Every M-family dimension scores at reference parity.

## Reproducibility

Reference service pinned per rubric guidance (`rep-order-service` family shape in
`~/rep_engineer_station/docs/`). Link/token/path checks are exhaustive (not
sampled) over all 35 `__docs/**/*.md`; T2 sampled `SwimLaneBoard` (Feature) and
`LiveRefreshPipeline` (Flow) against `_FlowDocGuide.md`. Re-running the commands
in the Method table yields the same numbers.
