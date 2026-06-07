# bdboard-mol-lon — ADR / decision-coverage check

Date: 2026-06-02
Scope: significant architectural/process decisions made in **code + beads**,
cross-referenced against written records in `notes/decisions/` (ADRs) and
`notes/design/<bead-id>/` (design docs + `*-decision.md` files).

> **Fourth pass.** This re-runs the ADR-coverage check first done in
> `notes/tasks/bdboard-mol-c09/` (2026-05-29), again in
> `notes/tasks/bdboard-mol-7up/` (2026-05-31), and again in
> `notes/tasks/bdboard-mol-29b/` (2026-06-01). The c09/7up audits found a large
> missing-ADR backlog; the `bdboard-jdd` commit wrote all of it; the 29b audit
> verified that backfill and surfaced exactly **one** new gap (D1: ADR 0004
> gone stale vs. the split/bounded read path). This pass (a) checks whether D1
> was fixed, (b) diffs the **39 commits since the 29b audit**
> (`git log 1a3e7c4..HEAD`, HEAD=`7a8bdf5`) for new architectural/process
> decisions, and (c) re-verifies the prior backfill is intact. Per project
> rules this audit does **not** self-close the bead.

## Method

1. Re-inventoried both decision homes at HEAD=`7a8bdf5`:
   - `notes/decisions/` — formal ADRs 0000–0006 + README index (intact).
   - `notes/design/<bead-id>/` — design docs + `*-decision.md` files.
2. Diffed every commit since the 29b audit commit (`1a3e7c4..HEAD`, 39
   commits) and read the bead notes / code behind the architecturally
   significant ones (207 beads total via `bd list --all --json`).
3. Verified each ADR against the **current code** it claims to describe
   (`src/bdboard/bd.py`, `store.py`, `derive/lanes.py`) rather than trusting
   the ADR's own prose — staleness is the failure mode the prior passes proved
   most likely here.

## Legend

- **STALE** — a written ADR exists but no longer matches the code it is the
  canonical record of. The decision *is* documented; the documentation is now
  *wrong*. This is the dominant defect class in this repo (the ADRs are dated
  2026-06-01; the code kept moving).
- **MISSING** — a significant decision with no durable written record at all.
- **COVERED** — verified accurate against the current code, no action.

---

## Headline result

The c09/7up missing-ADR backlog **remains written and indexed** (ADRs
0001–0006 + `0000-template.md` + `README.md` with the ADR-vs-design-doc rule).
The systemic root cause — no canonical ADR home (old gap X2) — is still closed.

**Two defects this pass, both STALE (code drifted past an existing ADR):**

1. **D1 — ADR 0004 still describes a single unbounded read; the code is now a
   three-way split/bounded read.** Carried over from the 29b audit **unfixed**,
   and now *more* inaccurate than when 29b flagged it (the `list_all` method
   29b referenced no longer even exists).
2. **D2 — ADR 0005 omits the revision-signature self-feedback-loop guard**
   (`bdboard-ywep`), a new, non-obvious architectural addition to the
   live-refresh pipeline that landed after the 29b audit.

No fully-MISSING decisions were found this pass — every significant decision
has *some* written home; two of those homes are now factually stale.

---

## D1 — ADR 0004 is STALE: the runtime read is a three-way split/bounded fetch   [CARRIED OVER, UNFIXED]

- **What ADR 0004 says (the canonical record):** reads are a single
  `bd list --all --no-pager --limit 0 --json` call. The command appears
  verbatim in the header blockquote, the Decision section, **and** the
  Alternatives table — three places, all now wrong.
- **What the code actually does** (`src/bdboard/bd.py`, verified at HEAD):
  there is **no `list_all` method anymore**. The single fetch was replaced by
  three distinct, purpose-built reads:
  - `list_active()` → `bd list --no-pager --limit 0` — active issues only
    (open/in_progress/blocked/deferred), the ~5 KB fast path for first paint.
  - `list_closed(window_days)` → `bd list --status closed --closed-after <iso>
    --sort closed --no-pager --limit 0` — the **board** Closed lane + header
    CLOSED KPI, **date-window-bounded** (not count-capped) so the lane and the
    KPI count the same set (`bdboard-p8v`).
  - `list_closed_history(limit, closed_after)` → `bd list --status closed
    --sort closed --no-pager --limit 0 [--closed-after <iso>]` — the **History**
    page path, **count-uncapped** by design (a static cap would make older
    closures unreachable, `bdboard-a194`) but **window-bounded** when a filter
    is active (`bdboard-gp06`).
- **Store side** (`src/bdboard/store.py`): three separate caches
  (`_active_snap` / `_closed_snap` / `_history_snap`) with `snapshot_active()`,
  `snapshot_closed()`, `snapshot_history(closed_after)`, lazy-loaded
  independently, plus an `/api/lanes/closed` endpoint and HTMX
  `hx-trigger="load"` so first paint ships **active-only**.
- **Why it's ADR-worthy / why the staleness bites:** ADR 0004 is supposed to be
  the canonical record of the runtime data-flow contract. A contributor reading
  only ADR 0004 would believe reads are one unbounded `--all` fetch and could
  "simplify" it back — silently reintroducing the payload-weight problem
  the split fixed, breaking the lazy-load first-paint path, and breaking the
  deliberate count-honesty trade-offs (board CLOSED = date-bounded set;
  History = uncapped). None of those trade-offs are recorded anywhere durable.
- **Where the decision actually lives now:** `bdboard-owz` / `-zdz` / `-y40` /
  `-p8v` / `-a194` / `-gp06` bead notes + the code + commit messages. No
  durable decision record, and ADR 0004's stated command is wrong.
- **Recommended fix:** amend ADR 0004 — replace the single-command claim with
  the three read paths above, document the lazy-load two-phase first paint
  (`/api/lanes/closed`, separate snapshots), and record the count-honesty
  consequences (board CLOSED is a **date-bounded** set, History is the
  **count-uncapped** retrospective). Cross-link the beads above. Per the README
  ADRs are immutable-and-superseded, but a factual correction of a now-wrong
  command + added consequences is the lighter, correct touch (29b's reasoning);
  a superseding `0007` is acceptable if the team prefers strict immutability.

> **Status note:** the 29b audit flagged this exact gap (its "D1") and
> recommended the same amendment. It was **not** acted on, so it recurs here —
> and is now strictly worse, since the `list_all` method 29b pointed at has
> since been deleted. Filed as a bead this pass so it stops slipping.

---

## D2 — ADR 0005 is STALE: missing the revision-signature self-feedback guard   [NEW SINCE 29b]

- **What ADR 0005 says:** the live-refresh pipeline is three stages —
  `watchfiles` watcher (non-recursive on `noms/` + `.beads/`) → `Store.refresh`
  (re-run `bd list`) → SSE `beads_changed`, broadcast **only when the bead list
  structurally changed** (equality check). Accurate as far as it goes.
- **What landed after the 29b audit** (`bdboard-ywep`, commit `f2179e3`,
  "Fix live-sync wedge: break refresh self-feedback loop"): a **fourth,
  load-bearing mechanism** the ADR doesn't mention. `BdClient.revision_signature()`
  fingerprints every dolt db's `.dolt/noms/manifest` (the tiny file holding
  dolt's current **root hash**); `Store.refresh()` compares it against the last
  refreshed signature and **skips the `bd list` subprocess entirely** when it is
  unchanged.
- **Why it exists (the bug it fixes):** a *read-only* `bd list` itself rewrites
  the watched `noms/` manifest (new inode + bumped mtime), so the watcher fires
  for our **own** read → refresh → read → event → refresh, spinning forever and
  (because `bd list` is slower than the self-trigger latency on a large
  `noms/`) cancelling each in-flight refresh before it finished, so the board
  **never updated until relaunch**. The manifest *content* (root hash) is
  identical across read-only churn and only flips on a real write, so comparing
  it distinguishes "dolt actually changed" from "our own read jiggled the
  files."
- **Why it's ADR-worthy:** this is a durable, non-obvious correctness
  invariant of the very pipeline ADR 0005 is the canonical record of. It
  deliberately rejects the naive "always re-run `bd list` on any watcher event"
  (which ADR 0005's own Decision §2 still implies). An empty signature is
  explicitly treated as "no signal → always refresh" (legacy JSONL-only safety).
  A contributor reading only ADR 0005 would not know the guard exists and could
  remove it as "redundant with the equality check" — reintroducing the
  refresh-loop wedge, which the equality check alone does **not** prevent (the
  loop starves before the equality check is ever reached).
- **Related, same area (no separate ADR needed):** `bdboard-xbc7` ("SSE
  auto-refresh drops trailing/isolated writes", commit `2429217`) is a watcher
  **debounce-timing** correctness fix in the same pipeline; `bdboard-1e5f`
  (`proc.kill()` `ProcessLookupError` guard, `5130dbb`) is a defensive bug fix.
  Both are implementation hardening of ADR 0005's pipeline, not new decisions —
  but the amendment for D2 should mention the debounce/cooldown timing exists so
  the timing isn't "simplified" either.
- **Recommended fix:** amend ADR 0005 — add the revision-signature skip as a
  stage-2 precondition ("compare dolt manifest root-hash; skip the `bd list`
  subprocess when unchanged; empty signature = always refresh"), and note the
  self-feedback loop it prevents. Cross-link `bdboard-ywep` (and `bdboard-xbc7`
  for the debounce timing). Factual amendment, same call as D1.

---

## COVERED — verified accurate this pass (no action)

| Area (commit / bead) | ADR / record | Verdict |
|---|---|---|
| Off-machine Dolt sync **re-enabled**, remote repointed to code origin (`bdboard-calu`, `5476ba6`/`60d2961`/`ea18196`) | ADR 0003 "Note on current deployment" block | **COVERED** — the reversal of the local-only posture, the misconfigured-separate-repo incident, and the `bd bootstrap` hydration path are all recorded in 0003. |
| Fresh-clone bead hydration via `bd bootstrap` (`bdboard-5xkj`, `e358d01`/`0cbd2fe`) | ADR 0003 deployment note (`bd bootstrap`, not `bd init` + pull) | **COVERED.** |
| jscpd duplication gate added to CI (`bdboard-29ic`, `ed0cf92`) | ADR 0002 §Decision 2 ("code-health checks in CI, not a bd formula") | **COVERED** — adding jscpd is an incremental tool *within* an existing ADR's policy, not a new decision. |
| History count-cap removal + window-driven closed fetch (`bdboard-a194`, `bdboard-gp06`) | — | Rolled into **D1** (it's the History arm of the same split-read decision). |
| lychee `exclude_path` regex anchoring (`7a8bdf5`), README lane-order/setup fixes | — | Doc-tooling / doc-accuracy fixes; no architectural decision. Owned by the other docs-validation children. |

---

## Process-health observation (not a defect of this bead)

`AGENTS.md` / `bd prime` still assert the project is **"local-only — there is
no git or dolt remote"**, but ADR 0003 + `bdboard-calu` record that off-machine
Dolt sync was **re-enabled** (remote repointed to the code origin; full history
pushed to `refs/dolt/data`). That is a doc/contract contradiction, but it is a
**README/agent-doc accuracy** issue, not an ADR-coverage gap (the *decision*
itself is correctly captured in ADR 0003). It belongs to the README-accuracy
child of this docs-validation epic, not here. Noted for traceability; **not**
re-filed by this bead to avoid duplicate beads.

---

## Summary — missing-ADR list (the deliverable)

**Defects found this pass (one bead filed per defect, per the epic):**

1. **D1 — ADR 0004 STALE.** Single unbounded read documented; code is a
   three-way split (`list_active` / `list_closed` date-bounded /
   `list_closed_history` count-uncapped) with separate caches + lazy-load.
   Amend ADR 0004; cross-link `bdboard-owz`/`-zdz`/`-y40`/`-p8v`/`-a194`/`-gp06`.
   *(Carried over unfixed from the 29b audit; now worse.)*
2. **D2 — ADR 0005 STALE.** Live-refresh ADR omits the revision-signature
   self-feedback-loop guard (`bdboard-ywep`) that skips the `bd list`
   subprocess when the dolt manifest root-hash is unchanged. Amend ADR 0005;
   cross-link `bdboard-ywep` (+ `bdboard-xbc7` for debounce timing).

**Resolved / intact since prior audits (no action):**

- c09/7up backlog (M1–M4, N1, X1, X2) → ADRs 0001–0006 + template + README
  index, all still present and indexed.
- Off-machine Dolt sync re-enable → ADR 0003 deployment note. Fresh-clone
  hydration (`bd bootstrap`) → ADR 0003. jscpd gate → within ADR 0002.

**Process health:** the systemic gap (no canonical ADR home) stays closed. Both
defects are ordinary "code outran the ADR" staleness — the failure mode this
repo is now structurally prone to, which argues for an ADR-freshness check
(diff each ADR's stated commands against the code) in a future docs-validation
pass.

> Per project rules this audit does not self-close the bead. Defects D1 and D2
> are filed as beads (one per defect, per the epic) for separate scheduling and
> LLM-judge verification.
