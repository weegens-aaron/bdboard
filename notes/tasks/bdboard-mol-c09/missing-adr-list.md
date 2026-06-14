# bdboard-mol-c09 — ADR / decision-coverage audit

Date: 2026-05-29
Scope: significant architectural/process decisions made in **code + beads**
cross-referenced against written records in `notes/decisions/` (ADRs) and
`notes/design/` (design docs + `decision`-type beads).

## Method

1. Enumerated all 123 beads (`bd list --all --json`) and the last 144 git
   commits to surface "significant recent changes."
2. Inventoried existing written decision records:
   - `notes/decisions/` — formal ADRs (only **one**: `0002-dashboard-architecture.md`).
   - `notes/design/<bead-id>/` — 8 design docs + 1 `decision`-type bead
     (`bdboard-tsu`, captured in bead body, not in a file).
3. Flagged decisions that shaped the codebase/architecture but have **no**
   written rationale, OR have rationale only in transient locations (bead
   notes / README / `bd remember` memories) rather than a durable design record.

## Legend

- **MISSING** — significant decision with **no** durable written record outside
  a bead note / README paragraph / memory. Strongest ADR candidates.
- **PARTIAL** — rationale exists in `notes/design/` or a `decision` bead, but was
  never promoted to a formal ADR in `notes/decisions/`. Lower priority; coverage
  exists, just not in the canonical ADR home.
- **PROCESS** — gap in the ADR system itself (numbering, template, index).

---

## Tier 1 — MISSING (write these ADRs)

### M1. Beads sync via Dolt git-refs ("Approach A"), not JSONL, not third-party host
- **Where the decision lives now:** `bdboard-6gp` (spike findings, bead notes) +
  `bdboard-9i7` (impl) + a `README.md` "JSONL freshness / Dolt remote" section.
- **Why it's ADR-worthy:** This is the project's core data-persistence and
  cross-machine-sync architecture. It deliberately rejects two alternatives
  (committing `.beads/issues.jsonl` as the wire protocol; third-party Dolt
  hosting) and picks `refs/dolt/data` on the existing git origin. That's a
  textbook "context + decision + alternatives + consequences" ADR.
- **Gap:** No file in `notes/decisions/`. README documents the *how-to* but is
  onboarding-focused (and ADR-0002 explicitly says rationale should NOT live in
  the README). The spike bead is the only place the *why/alternatives* are
  recorded, and bead notes are not a durable design home.
- **Recommended:** `notes/decisions/0003-beads-sync-via-dolt-git-refs.md`.

### M2. Runtime source of truth = `bd` CLI JSON output, never `.beads/issues.jsonl`
- **Where the decision lives now:** `bd remember` memory `stack-overview` +
  `refresh-architecture` + scattered README lines + a code comment fix
  (`bdboard-0r1` item #20/#21).
- **Why it's ADR-worthy:** Cross-cutting invariant that the whole read path
  (`store.py`, `bd.py`, derive modules) depends on. It was actively mis-documented in code
  comments/README (fixed in `bdboard-68q`), which is exactly the kind of drift a
  durable ADR prevents.
- **Gap:** Recorded only in memories/README; no decision record stating *why*
  JSONL is never read (freshness + upstream COMMUNITY_TOOLS guidance).
- **Recommended:** fold into M1's ADR, or write a sibling
  `notes/decisions/0004-runtime-source-of-truth.md`.

### M3. Live-refresh pipeline: `watchfiles` → `Store.refresh` (`bd list`) → SSE `beads_changed`
- **Where the decision lives now:** `bd remember` memory `refresh-architecture`
  + incidentally described inside design spikes (`bdboard-7q9`, `bdboard-9n4`,
  `bdboard-rrc`, `bdboard-5p1`) as a thing those features *reuse*.
- **Why it's ADR-worthy:** It's the shared real-time mechanism every feature
  plugs into (broadcast-only-on-structural-change, optimistic re-render +
  SSE reconcile). New features keep referencing it as settled prior art, but
  the decision itself was never written as a standalone record — it's only
  derivable by reading four spike docs.
- **Gap:** No consolidated record; the only canonical statement is a one-line
  `bd remember` memory.
- **Recommended:** `notes/decisions/0005-live-refresh-architecture.md`.

### M4. Manual field editing — editability registry + open-only mutation + append-only notes
- **Where the decision lives now:** `notes/design/bdboard-7q9/manual-field-editing-spike.md`
  (good spike) **plus** two decisions made *after* the spike that aren't in any
  design doc:
  - **Edits gated to OPEN beads only** (`bdboard-1lf`) — a real policy decision.
  - **`notes` is append-only / `append_only=True`** as a registry invariant
    (`bdboard-o9v.4`) — protects bug-discovery/verification history.
  - **`updated_at` optimistic-lock** (`bdboard-o9v.5`) shipped from a "v2
    follow-up" note with no decision record of its own.
- **Why it's ADR-worthy:** The "editability registry as the extensibility seam"
  is the architectural through-line of the whole `bdboard-o9v` epic and is the
  template the status-transition design (`bdboard-o9v.6`) explicitly copies.
- **Gap:** PARTIAL spike coverage, but the post-spike *policy* decisions
  (open-only, append-only-as-invariant, optimistic-lock-now-not-later) are
  uncaptured.
- **Recommended:** promote to `notes/decisions/0006-manual-field-editing-model.md`
  (the durable invariants), keep the spike as supporting detail.

---

## Tier 2 — PARTIAL (rationale exists, not promoted to an ADR)

These have a real written record in `notes/design/` or a `decision` bead. They
are **covered**; flagged only because `notes/decisions/` is the project's stated
canonical ADR home (per ADR-0002 consequences). Promote opportunistically.

| # | Decision | Recorded in | Promote? |
|---|---|---|---|
| P1 | Priority color scale P0–P4 (light+dark) | `bdboard-tsu` (decision bead body) | Optional — bead is thorough but file-less |
| P2 | No scheduler for recurring formulas (cadence/invoker) | `notes/design/bdboard-ace/cadence-invoker-decision.md` | Already a decision doc; move to `notes/decisions/`? |
| P3 | Formula grouping node shows as epic (Option A) | `notes/design/bdboard-ain.2/grouping-node-display-decision.md` | Already a decision doc |
| P4 | Code-health checks in CI, not a bd formula | ADR-0002 §Decision 2 | Already an ADR ✅ |
| P5 | Memory View read-only vs CRUD | `notes/design/bdboard-5p1/memory-view-design.md` §3 | Covered |

Observation: P2 and P3 are literally titled `*-decision.md` and live under
`notes/design/`. The project has **two homes** for decisions (`notes/design/` and
`notes/decisions/`) with no rule for which goes where — see PROCESS gap X2.

---

## Tier 3 — PROCESS gaps in the ADR system

### X1. Missing ADR-0001
`notes/decisions/` starts at `0002`. There is no `0001-*.md` and no record of
what 0001 was (superseded? never written?). Either backfill `0001` (e.g. the
"adopt ADRs / record-architecture-decisions" meta-decision) or add a note in
the index explaining the gap.

### X2. No ADR index or template, and two competing decision homes
- No `notes/decisions/README.md` (or `0000-template.md`) defining the ADR format,
  numbering, or status lifecycle.
- Decisions are split between `notes/decisions/*.md` (ADR-numbered) and
  `notes/design/<bead>/*-decision.md` (bead-scoped) with no documented rule for
  which to use. This is *why* M1–M4 slipped through: the path of least
  resistance was a bead note or a design doc, never a numbered ADR.
- **Recommended:** add `notes/decisions/0000-template.md` + an index, and a
  one-line rule (e.g. "cross-cutting/architectural → numbered ADR; feature-local
  → `notes/design/<bead>/`").

---

## Summary — missing-ADR list (the deliverable)

**Write (MISSING):**
1. M1 — Beads sync via Dolt git-refs (Approach A) — **highest priority**
2. M2 — Runtime source of truth is `bd` CLI JSON, never `issues.jsonl`
3. M3 — Live-refresh architecture (watchfiles → Store.refresh → SSE)
4. M4 — Manual field-editing model (editability registry, open-only, append-only, optimistic-lock)

**Promote when convenient (PARTIAL):** P1 (priority palette), P2 (no scheduler),
P3 (grouping node display).

**Fix the ADR process (PROCESS):** X1 (missing 0001), X2 (no template/index +
two competing decision homes).

> Per project rules this audit does not self-close the bead and does not file
> the follow-up ADR-authoring beads automatically; M1–M4 / X1–X2 are the
> recommended follow-up beads if the team wants the records written.
