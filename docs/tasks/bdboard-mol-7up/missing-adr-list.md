# bdboard-mol-7up — ADR / decision-coverage audit

Date: 2026-05-31
Scope: significant architectural/process decisions made in **code + beads**
cross-referenced against written records in `docs/decisions/` (ADRs) and
`docs/design/` (design docs + `decision`-type beads).

> **Follow-up audit.** This re-runs the ADR-coverage check first done in
> `docs/tasks/bdboard-mol-c09/missing-adr-list.md` (2026-05-29). It (a)
> re-verifies whether that audit's recommendations were acted on, and (b)
> surfaces NEW decisions made in the commits since (`d16e264..HEAD`). Per
> project rules this audit does not self-close the bead and does not auto-file
> the follow-up ADR-authoring beads.

## Method

1. Diffed the commits since the previous audit (`git log d16e264..HEAD`, 18
   commits) for new architectural/process decisions, and re-read the bead
   notes behind the significant ones.
2. Re-inventoried the written decision homes:
   - `docs/decisions/` — formal ADRs. **Still only one:**
     `0002-dashboard-architecture.md` (unchanged since the c09 audit).
   - `docs/design/<bead-id>/` — 8 design docs + 2 `*-decision.md` files.
3. Checked whether the c09 audit's recommended ADRs (M1–M4) or process fixes
   (X1, X2) were written, or whether ADR-authoring follow-up beads were filed.

## Headline result

**Nothing from the previous audit was acted on.** `docs/decisions/` is byte-for-byte
the same single ADR; no `0001`, `0003`–`0006`, template, or index was added, and
no ADR-authoring beads were filed (searched `bd list --all` for them: none). So
the entire c09 missing-ADR list **carries forward unchanged**, and this pass adds
the new decisions made since.

---

## Part A — Carry-forward from bdboard-mol-c09 (still MISSING)

All four still have **no** durable record in `docs/decisions/`. Restated tersely;
see the c09 doc for full rationale.

| # | Decision | Still lives only in | Status |
|---|---|---|---|
| M1 | Beads sync via Dolt git-refs ("Approach A"), not JSONL, not 3rd-party host | `bdboard-6gp`/`bdboard-9i7` bead notes + README | STILL MISSING |
| M2 | Runtime source of truth = `bd` CLI JSON, never `issues.jsonl` | `bd remember` memories + README | STILL MISSING |
| M3 | Live-refresh pipeline: watcher → `Store.refresh` → SSE | `bd remember` memory + spike docs | STILL MISSING (now **amended**, see N1) |
| M4 | Manual field-editing model (registry, open-only, append-only, optimistic-lock) | `docs/design/bdboard-7q9/` spike + bead notes | STILL MISSING |

Process gaps also unchanged:

- **X1** — no `docs/decisions/0001-*.md`; numbering still starts at `0002`.
- **X2** — still two competing decision homes (`docs/decisions/*.md` vs
  `docs/design/<bead>/*-decision.md`) with no rule for which to use, and no ADR
  template/index. This remains the root cause of every gap below.

---

## Part B — NEW decisions since the c09 audit (`d16e264..HEAD`)

### N1. Watcher strategy: watch dolt `noms/` dirs NON-recursively, not the whole `.beads/` tree
- **Where the decision lives now:** `bdboard-3sf` bead notes + a long docstring
  on `BdClient.watch_targets()` (`src/bdboard/bd.py`) + a regression test
  (`tests/test_watch_targets.py`).
- **Why it's ADR-worthy:** This is a load-bearing change to M3's live-refresh
  architecture — the very mechanism the c09 audit already flagged as
  undocumented. It deliberately rejects `awatch(.beads, recursive=True)` (the
  obvious approach) because on macOS the kqueue backend opens one fd per watched
  dir, exhausting `RLIMIT_NOFILE` and crashing every subprocess call. The fix
  watches a tiny fixed set of `noms/` dirs non-recursively. That's a real
  "context + decision + rejected-alternative + consequences" record, and it now
  *modifies* the still-unwritten M3 decision.
- **Gap:** The "why" is well captured in a code docstring + bead, but there is
  no decision record, and M3 itself was never written — so the watcher's design
  is derivable only by reading code comments and a closed bug bead.
- **Recommended:** fold into the M3 ADR (`0005-live-refresh-architecture.md`) as
  the watcher subsection, OR a sibling once M3 exists.

### N2. Workflow formulas are generic/variable-less (no `repo`, no date/cadence binding)
- **Where the decision lives now:** `bdboard-65z` bead notes + the formula files
  themselves (`.beads/formulas/*.formula.json`) + the formulas `README.md`.
- **Why it's ADR-worthy (borderline):** This **reverses** an earlier, documented
  design — `docs/design/bdboard-ace/cadence-invoker-decision.md` and the
  formula-spike notes assumed per-pour `repo`/`quarter` variables and a
  quarterly cadence. bdboard-65z dropped all variables and all cadence/date
  language (and `bdboard-q9w` had just renamed `quarter`→`date` two commits
  earlier — now moot). When a *new* decision supersedes a *written* one, the
  written one (`cadence-invoker-decision.md`) is now partly stale and nothing
  records the reversal in a durable place.
- **Gap:** PARTIAL — the new state is documented in the formula files + their
  README, but the *decision to go generic* (and that it supersedes the
  variable/cadence assumptions in `bdboard-ace`) is only in a bead note.
- **Recommended:** lightweight — add a "Superseded by bdboard-65z (formulas are
  now variable-less)" note to `docs/design/bdboard-ace/cadence-invoker-decision.md`
  so the stale doc points forward. Full ADR not required.

### N3. CI runs against a `uv` venv with `--no-sync`, not `--system`
- **Where the decision lives now:** `bdboard-mol-tgq` / `bdboard-b6i` bead notes
  + the `.github/workflows/*.yml` diffs (commits `abb0cd6`, `44c682c`).
- **Why it's ADR-worthy (borderline):** A real CI/process decision with a sharp
  rationale — `uv pip install --system` crashed on GitHub's externally-managed
  runner Python (PEP 668), which had silently turned the pip-audit/pytest steps
  into **no-ops** (a security-relevant CI gap). The fix (use a uv venv; add
  `--no-sync` so CI ignores the Walmart-pinned `uv.lock`) encodes two
  environment-specific constraints worth remembering before someone "simplifies"
  the workflow back to `--system`.
- **Gap:** PARTIAL — captured in bead notes + the YAML, but a future editor
  reading only the workflow won't know *why* `--no-sync` and a venv are load-bearing.
- **Recommended:** a comment block in the workflow YAML pointing at bdboard-mol-tgq
  is sufficient; ADR optional.

### Non-decisions (reviewed, no ADR needed)
The remaining post-c09 commits are bug fixes, DRY refactors, and CSS/layout
tweaks with no architectural decision content: the masthead two-row saga
(`bdboard-vbz`/`-9y7`/`-xgu`/`-c52`/`-rip`), count-honesty guard (`bdboard-98e`),
env-independent route tests (`bdboard-e4l`), and the two DRY extractions
(`bdboard-rhv`, `bdboard-6nv`). Correctly left undocumented as ADRs.

---

## Summary — missing-ADR list (the deliverable)

**Still missing from the prior audit (write these — unchanged priority):**
1. M1 — Beads sync via Dolt git-refs (Approach A) — **highest priority**
2. M2 — Runtime source of truth is `bd` CLI JSON, never `issues.jsonl`
3. M3 — Live-refresh architecture (watcher → Store.refresh → SSE) —
   **now must include N1** (non-recursive `noms/` watch strategy)
4. M4 — Manual field-editing model (registry, open-only, append-only, optimistic-lock)

**New since c09 (lighter touch):**
5. N1 — Watcher fd-safety strategy → fold into the M3 ADR.
6. N2 — Formulas are now generic/variable-less → add a "superseded" pointer to
   `docs/design/bdboard-ace/cadence-invoker-decision.md`.
7. N3 — CI uses a uv venv + `--no-sync`, not `--system` → comment in workflow YAML.

**Fix the ADR process (PROCESS — still open, and the root cause):**
- X1 — missing `0001`.
- X2 — no ADR template/index + two competing decision homes. **Until X2 is
  fixed, every audit will keep finding the same class of gap** (decisions land
  in bead notes / design docs / code comments because there's no frictionless,
  canonical ADR path). Highest-leverage fix.

> Per project rules this audit does not self-close the bead and does not file
> the follow-up ADR-authoring beads automatically. M1–M4, N1–N3, and X1–X2 are
> the recommended follow-up beads if the team wants the records written. The
> single highest-leverage action remains **X2** — define the ADR home/template —
> because it's why nothing from the c09 audit got written.
