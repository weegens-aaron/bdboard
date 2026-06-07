# Decision: cadence + invoker for recurring maintenance formulas

- **Bead:** bdboard-ace (task / decision)
- **Discovered from:** bdboard-zda (formula spike)
- **Status:** decided — **no scheduler shipped** (that is the decision).
  **PARTIALLY SUPERSEDED** — see note below.
- **Date:** 2026-05-29

> **Superseded by bdboard-65z (formulas are now variable-less).** The runbook
> in §4 below shows per-pour `--var repo=…` / `--var quarter=…` arguments. That
> reflects the old formula design. bdboard-65z dropped **all** formula
> variables and all cadence/date binding (and bdboard-q9w's earlier
> `quarter`→`date` rename is now moot). The **cadence + invoker decision in
> this doc still stands** (manual quarterly pour, no scheduler); only the
> variable-passing in the runbook commands is stale — pour the formulas with no
> `--var` flags. See `.beads/formulas/README.md` for the current invocation.

> This document is the deliverable for bdboard-ace. It records the chosen
> cadence and invoker for the two shipped maintenance formulas
> (`docs-validation`, `code-health-audit`), the options considered, and the
> explicit trigger conditions under which we would revisit automation. It
> ships **no** runtime code and **no** scheduler — choosing *not* to automate
> yet is the decision, per the spike's "do not block adoption on a scheduler"
> guidance.

---

## 1. Problem

`bd` formulas have **no scheduler**. A formula only spawns work when something
external invokes `bd mol pour` / `bd mol wisp` (confirmed empirically in
bdboard-zda, §4: "No scheduling. Something external (cron, a human, an
orchestrator) must invoke pour/wisp on a cadence."). The two maintenance
formulas shipped by the formula epic —

- `docs-validation` (bdboard-jye)
- `code-health-audit` (bdboard-jyf)

— are now live in `.beads/formulas/` but nothing fires them. This bead decides
**how often** they run (cadence) and **who/what** fires them (invoker).

---

## 2. Decision (TL;DR)

- **Cadence: quarterly**, at the start of each quarter.
- **Invoker: manual** — a human runs `bd mol pour` (persistent path).
- **Automation: deferred** — no cron, no GitHub Actions schedule, no
  orchestrator hook is shipped now. Revisit only when the trigger conditions
  in §5 are met.

This matches the interim policy already recorded in
`.beads/formulas/README.md` (both formulas' "Chosen cadence" sections) — this
bead **ratifies** that interim policy as the deliberate decision and documents
the reasoning + revisit criteria so it isn't an accidental default.

---

## 3. Options considered

| Option | Invoker | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. Manual quarterly pour** | Human runs `bd mol pour` at quarter start | Zero infra; zero new failure modes; human chooses the right moment; trivially reversible; matches low formula volume (2) | Relies on a human remembering; can slip | **CHOSEN** |
| B. CI scheduled job (`on: schedule` cron in GitHub Actions) | GitHub Actions runner | Reliable timer; runs unattended | Runner needs write access to the bead store + `bd dolt push`; spawned beads with nobody watching = stale audit clutter; harder to suppress for a quiet quarter; auth/secret surface | Deferred |
| C. Local `cron` / `launchd` | A single developer's machine | Simple to set up | Single-machine bus factor; silent when laptop is off; not git-synced; surprises teammates | Rejected |
| D. Orchestrator hook (`$GT_ROOT` integration) | External orchestrator | Centralized; scalable to many repos/formulas | No orchestrator in play for this repo today; YAGNI; biggest infra cost | Deferred |

### Why manual wins *for now*

1. **Volume is tiny.** Two formulas, quarterly. The annual invocation count is
   ~8 commands. Building/owning a scheduler for 8 commands/year is textbook
   over-engineering (YAGNI).
2. **Formulas spawn work; they don't run it** (spike §4). An unattended
   scheduler that pours an audit epic + 4 children when nobody is around to
   triage them just manufactures stale beads — the opposite of the
   "one bead per finding, with an owner" audit-trail value.
3. **A human picks the moment.** Quarter-start is a judgment call (don't pour
   the day before a release freeze). Manual invocation keeps that judgment.
4. **Reversible & cheap.** Manual → automated is a one-way door we can walk
   through later; automated → manual (unwiring CI secrets / orchestrator
   hooks) is more expensive to walk back.
5. **No new failure modes.** No runner auth, no `bd dolt push` from CI, no
   secret management, no "why did 12 beads appear at 3am?" surprises.

---

## 4. Runbook (the manual cadence)

At the **start of each quarter**, the maintainer runs both formulas
(preview first, then for real):

```bash
# Preview (no issues created) — confirm the tree shape before committing
bd mol pour docs-validation     --var repo=bdboard --dry-run
bd mol pour code-health-audit   --var repo=bdboard --var quarter=2026-Q3 --dry-run

# Spawn the work (persistent / git-synced audit trail)
bd mol pour docs-validation     --var repo=bdboard
bd mol pour code-health-audit   --var repo=bdboard --var quarter=2026-Q3

# Sync the spawned beads to the remote
bd dolt push
```

Notes:
- Use **`pour`** (persistent), not `wisp` — these audits want a permanent
  record. Both formulas keep top-level `pour:true` as a safety net so even an
  accidental `wisp` still materializes the full tree (see
  `formula-vapor-pour-gotcha` memory).
- Bump the `quarter` var each cycle (`2026-Q3`, `2026-Q4`, …).
- Triage spawned children per the **Bug Discovery Protocol** — one bead per
  finding; don't fix inline unless blocking.

### Reminder mechanism (lightweight, not a scheduler)

To stop the cadence from silently slipping without building automation, file a
**plain recurring reminder bead** ("Run quarterly maintenance formulas") at the
start of each quarter as part of triaging the previous quarter's audit. This is
the spike's own guidance (§4: a single periodic reminder is a job for a plain
recurring bead, not a formula and not infra). A reminder bead is cheap, visible
in `bd ready`, and needs zero infrastructure.

---

## 5. When to revisit (trigger conditions for automation)

Promote from manual to **Option B (CI scheduled)** — the most likely next step
— when **any** of these becomes true:

1. **Drift in practice:** a quarter is missed because someone forgot, more than
   once. (Manual is only "good enough" if it actually happens.)
2. **Formula count grows:** more than ~4–5 recurring formulas, where the manual
   command list becomes error-prone.
3. **Cross-repo scale:** the same formulas need to run across multiple
   repositories (then Option D / orchestrator becomes worth the cost).
4. **CI gains bead-store write + `bd dolt push` capability** with managed
   secrets — removing the main blocker that makes Option B expensive today.

Until then: **manual quarterly pour stands.** Re-evaluating is itself cheap;
prematurely automating is not.

---

## 6. Outcome

- Cadence and invoker are **decided and documented** (this doc +
  `.beads/formulas/README.md`).
- **No scheduler is built** — deliberately, per spike guidance not to block
  adoption on automation.
- Revisit criteria are explicit so the deferral is a decision, not neglect.
