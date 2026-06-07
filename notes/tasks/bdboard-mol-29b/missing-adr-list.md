# bdboard-mol-29b — ADR / decision-coverage check

Date: 2026-06-01
Scope: significant architectural/process decisions made in **code + beads**,
cross-referenced against written records in `docs/decisions/` (ADRs) and
`docs/design/<bead-id>/` (design docs + `*-decision.md` files).

> **Third pass.** This re-runs the ADR-coverage check first done in
> `docs/tasks/bdboard-mol-c09/` (2026-05-29) and again in
> `docs/tasks/bdboard-mol-7up/` (2026-05-31). Between the 7up audit and this
> one, **the ADR backlog the prior audits flagged was actually written** — so
> this pass (a) verifies that backfill, and (b) surfaces decisions made since
> that are still undocumented. Per project rules this audit does not self-close
> the bead and does not auto-file follow-up ADR-authoring beads.

## Method

1. Re-inventoried the two decision homes against `git log -1` =
   `fbe4e34` (2026-06-01 00:55):
   - `docs/decisions/` — formal ADRs.
   - `docs/design/<bead-id>/` — design docs + `*-decision.md`.
2. Diffed every commit since the 7up audit (`git log e662e2d..HEAD`, 21
   commits) for new architectural/process decisions and read the bead notes
   behind the significant ones.
3. Verified that the 7up/c09 missing list (M1–M4, N1–N3, X1–X2) was acted on.

---

## Headline result

**The entire prior missing-ADR list has been written down.** Commit `524c3fb`
(bdboard-jdd, "fix ADR process gap — add template, index, 0001, backfill
M1-M4") turned `docs/decisions/` from a single orphaned `0002` into a complete,
indexed ADR set:

| Prior gap | Now recorded in | Verdict |
|---|---|---|
| X1 (no `0001`) | `0001-record-architecture-decisions.md` | RESOLVED |
| X2 (no template/index, two homes, no rule) | `0000-template.md` + `README.md` index + "ADR vs design doc" rule | RESOLVED |
| M1 (Dolt git-refs sync) | `0003-beads-sync-via-dolt-git-refs.md` (+ local-only deployment note) | RESOLVED |
| M2 (runtime source = `bd` CLI JSON) | `0004-runtime-source-of-truth-bd-cli-json.md` | RESOLVED |
| M3 (live-refresh watcher→Store.refresh→SSE) | `0005-live-refresh-architecture.md` | RESOLVED |
| N1 (non-recursive `noms/` watch fd-safety) | folded into `0005` | RESOLVED |
| M4 (manual field-editing model) | `0006-manual-field-editing-model.md` | RESOLVED |
| N2 (formulas now generic/variable-less) | "superseded" pointer added to `docs/design/bdboard-ace/cadence-invoker-decision.md` | RESOLVED (verify pointer present) |
| N3 (CI uses uv venv + `--no-sync`) | workflow YAML + bead notes; lightweight, ADR optional | ACCEPTED AS-IS |

The README index's own preamble cites both prior audits as the reason it exists.
The friction that made every prior audit find the same gaps (no canonical ADR
path — old gap X2) is gone.

---

## NEW decisions since the 7up audit (`e662e2d..HEAD`)

### D1. Runtime read path is now a SPLIT, BOUNDED active/closed fetch — ADR 0004 is partially stale  ⚠️ ONLY remaining gap

- **What changed.** ADR 0004 (M2) documents the runtime read as a single
  `bd list --all --no-pager --limit 0 --json` call (it says so verbatim in the
  header blockquote, the Decision section, and the Alternatives table). That is
  no longer how bdboard reads bead state. A chain of three changes replaced it:
  - **bdboard-owz** (spike): measured the single `--all --limit 0` fetch as the
    dominant first-paint/refresh cost (493 KB, 154 issues) and recommended
    bounding it.
  - **bdboard-zdz** (`f872c3e`): `BdClient.list_all()` now makes **two**
    serialized `bd list` calls — active unbounded + closed capped at
    `CLOSED_LANE_LIMIT=50`, sorted `closed_at` desc — instead of one `--all`
    call truncated client-side (~63% payload reduction).
  - **lazy-load** (`8837682`): added `list_active()`/`list_closed()`,
    `snapshot_active()`/`snapshot_closed()` with **separate caches**, an
    `/api/lanes/closed` endpoint, and HTMX `hx-trigger="load"` lazy loading so
    first paint ships active-only (~5 KB).
  - **bdboard-y40** (`e2a78ad`): promoted the closed-lane time window to a
    board-wide filter affecting the bounded closed fetch.
- **Why it's ADR-worthy.** This is a real, durable change to the **runtime
  data-flow contract** ADR 0004 is supposed to be the canonical record of. It
  also encodes a deliberate, non-obvious trade-off: the masthead closed count
  is now a **capped value (≤50), not the true total** (true count only via the
  History page). A future contributor reading ADR 0004 would believe reads are
  a single unbounded `--all` fetch and could "simplify" the split back,
  silently reintroducing the payload-weight problem owz fixed and breaking the
  lazy-load first-paint path.
- **Where the decision lives now:** `bdboard-owz`/`-zdz`/`-y40` bead notes +
  the code (`bd.py::list_all`/`list_active`/`list_closed`,
  `store.py` split snapshots, `derive/lanes.py`, `/api/lanes/closed`) + commit
  messages. **No durable decision record**, and ADR 0004's stated read command
  is now inaccurate.
- **Gap:** PARTIAL — the new behaviour is implemented and bead-noted, but ADR
  0004 (the canonical home) is **stale** and there is no record of the
  count-honesty trade-off.
- **Recommended:** amend ADR 0004 — update the read command(s) to the
  split active(unbounded) + closed(bounded, `CLOSED_LANE_LIMIT`) model, note
  the lazy-load two-phase first paint, and record the capped-closed-count
  consequence. Cross-link bdboard-owz/-zdz/-y40. This is an *amendment* to an
  existing ADR, not a new number (per the README, immutable ADRs are superseded
  by new numbers, but a factual correction of a now-inaccurate command + an
  added consequence is the lighter, correct touch here; if the team prefers
  immutability, a superseding `0007` works too).

### Non-decisions (reviewed, no ADR needed)

The remaining post-7up commits carry no durable architectural decision content:
README accuracy fixes (`31faa6d`, `5267496`, `f4214cc`, `f298429`), the
open-source de-Walmarting / prose scrub (`bd7aea6`, `98ec85e`, `ac521d4` — the
local-only doc scrub, already reflected in ADR 0003's deployment note),
`bdboard-uof` make-target alignment, the subprocess fd-leak fix (`78a419b`,
already covered by ADR 0005's fd-safety rationale), the venv-activation setup
fix (`c4e9793`), the masthead in-progress-count removal (`62c5207`), the
broken-link-sweep template exclusion (`fbe4e34`), and the pour refresh-ordering
fix (`de66415`). Correctly left undocumented as ADRs.

---

## Summary — missing-ADR list (the deliverable)

**Newly missing (write/amend this — the only open gap):**

1. **D1 — runtime read is now a split, bounded active/closed fetch.** Amend ADR
   `0004-runtime-source-of-truth-bd-cli-json.md`: correct the read command to
   the active(unbounded) + closed(capped `CLOSED_LANE_LIMIT=50`, `closed_at`
   desc) model, document the lazy-load two-phase first paint
   (`/api/lanes/closed`, separate `snapshot_active`/`snapshot_closed` caches),
   and record the capped-closed-count consequence. Cross-link bdboard-owz /
   bdboard-zdz / bdboard-y40.

**Resolved since the prior audits (no action):**

- M1–M4 → ADRs 0003–0006; N1 folded into 0005; X1 → 0001; X2 → template +
  README index + ADR-vs-design-doc rule (all via bdboard-jdd, `524c3fb`).
- N2 → "superseded" pointer in `docs/design/bdboard-ace/cadence-invoker-decision.md`.
- N3 → workflow YAML + bead notes (ADR optional, accepted as-is).

**Process health:** the root-cause gap (X2 — no canonical ADR home) that made
every prior audit find the same class of defect is **closed**. The ADR process
now exists and is being used; D1 is a normal "code moved faster than the ADR"
drift, not a systemic gap.

> Per project rules this audit does not self-close the bead and does not file
> the follow-up ADR-amendment bead automatically. D1 is the single recommended
> follow-up if the team wants ADR 0004 brought back in sync with the code.
