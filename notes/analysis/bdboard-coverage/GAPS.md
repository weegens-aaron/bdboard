# bdboard Display-Fidelity — Consolidated Issues & Gaps

**Synthesis bead:** `bdboard-bk1r` · **Epic:** `bdboard-gnhi`
**Inputs:** the 9 completed section findings in this directory (`01`–`09`).
**Nature:** a mechanical merge — every gap below is traceable to a section row;
no new analysis, just consolidation, dedup, severity × value ranking, and
concrete follow-up bead recommendations. This file files **no beads itself**;
it hands a planner a ready-to-pour shortlist.

> **The axis is REFLECTED, not LEVERAGED.** bead-chain is a *driver* — it asked
> what bd features it consumes. bdboard is a *display* — it asks what bd state it
> shows the user. Every severity below is about **misleading the human reading
> the board**, per the reframed rubric in [`README.md`](./README.md).

---

## Executive summary

bdboard is a **general-purpose, read-mostly FastAPI + HTMX dashboard** that any
developer can point at **any** bd workspace. Measured against the full bd 1.0.4
feature surface (the 9-chapter field guide), it is an **excellent, faithful
reader of a bead's stored *content*** and a **near-total blind spot on bd's
*coordination & movement* layers**. Field-presence fidelity is deliberately
total (anatomy: `_ordered_fields` appends unknown keys alphabetically + a raw-
JSON escape hatch, so nothing bd emits is ever hidden); the gaps are about
**lane classification, visual differentiation, and unsurfaced subsystems**.

The gaps cluster into **four stories**:

1. **One code site silently lies about readiness.** `_has_unmet_blocking_dep`
   (`lanes.py:126`, mirrored in the epic strip at `lanes.py:236`) gates only on
   `blocks` and **never on `waits-for`** — yet the field guide names `waits-for`
   as one of bd's **two** blocking edge types. Two independent sections
   (dependency-graph, gates) discovered the **same P0** from this one hole: a
   bead gated solely by a `waits-for` fanout edge is shown in the **READY lane**
   while bd excludes it from `bd ready`. This is the textbook *blocked-shown-as-
   ready* misrepresentation — the same class as the reversed-dep `bdboard-fjk`
   P0. **One blocker-set edit closes both P0s.**

2. **Whole bd subsystems are invisible because bdboard never invokes their
   verbs.** Gates (area 6) and swarms (area 7) have **zero** awareness — gate
   beads render as claimable *ready work*, swarm molecules are *hidden*
   entirely, and graph hygiene (area 9: lint/cycles/orphans/stale) surfaces
   **nothing**. These are read-mostly-posture omissions, not correctness bugs —
   but several are cheap, high-value enrichments because **bdboard already holds
   or already computes the data** (the cycle is detected then thrown away).

3. **The board's *type* signal is flat.** All 9 bead types + `event` render as
   identical uppercase grey text (`bdboard-anatomy-type-flat`); the field
   guide's glyph system (●▲■○◆◇↗▸◎) is wholly unreflected. A `milestone`/`gate`/
   coordination bead is indistinguishable from a `chore` at a glance. This is
   the root that makes gate (area 6) and mol-type (area 5) legibility worse.

4. **bdboard narrates *local* truth perfectly but says nothing about
   *movement*.** It honors the chapter-8 doctrine (Dolt-via-CLI is truth, JSONL
   is a souvenir, never writes `.beads/`) and is structurally always-fresh
   against *local* Dolt — but shows **no** sync state (ahead/behind origin), and
   its `live · push` pill is confusably named (it means the SSE socket, not
   `bd dolt push`).

Everything else is either a **deliberate boundary** (multi-WIP / general-purpose
is the *intended* design; read-mostly is the SRP stance; not inventing
wing/scope/BM25 UI that bd has no data for) or a **narrow-window polish** item
(field-render nits, P3/P4 enrichments).

### The single biggest insight

> **bdboard's biggest gap is one code site.** `_has_unmet_blocking_dep`
> (`lanes.py:126`, mirrored at `lanes.py:236`) gates readiness on `blocks`
> **only** and silently drops `waits-for` — one of bd's two blocking edge types.
> **Two** independent sections (dependency-graph area 2 #1, gates area 6 #1)
> found the **same P0** from this single hole: a `waits-for`-gated bead is shown
> in the READY lane while bd considers it blocked. One blocker-set edit
> (honoring vacuous-satisfy on a childless spawner) closes **both P0s** — the
> same shape as the reversed-dep `bdboard-fjk` class. The **second-biggest is
> FREE**: bdboard already computes a dependency cycle in `_topo_component_order`
> (`lanes.py:196`) and **throws it away** (`lanes.py:201`), so a permanently-
> deadlocked pair renders as ordinary "Blocked" — surfacing the already-computed
> cycle as a badge costs almost nothing.

(Recommended for `bd remember`.)

---

## Capability matrix

The filled matrix lives in [`README.md`](./README.md#capability-matrix-filled-by-the-synthesis-bead-bdboard-bk1r).
Compact restatement (A = Available per field guide, R = Reflected by bdboard):

| # | Area | A? | R? | Top sev | Gaps | Headline |
|---|------|----|----|---------|------|----------|
| 1 | Anatomy |  | **Partial** (all fields shown; type flat) | **P1** | 8 | every field surfaced (no drops), but all 9 types + `event` render as identical grey text — glyph system unreflected |
| 2 | Dependency graph |  | **Partial** (`blocks` + direction good) | **P0** | 5 | `waits-for` not gated in lanes → blocked-shown-as-ready; no DAG view |
| 3 | Status lifecycle |  | **Partial** (5 lanes; multi-WIP OK) | **P1** | 6 | `pinned`/`hooked` fall through `else` → shown as Deferred; multi-WIP renders fine |
| 4 | Memories & recall |  | **Full** (3/4 verbs; recall covered) | P3 | 5 (+1 no-action) | highest-fidelity surface; wing/scope/BM25 refuted as not-bd |
| 5 | Formulas & molecules |  | **Partial** (pour/liquid only) | P2 | 5 (+2 no-action) | solid pour write-surface; vapor poured as persistent (warning swallowed); no molecule rollup |
| 6 | Gates & coordination |  | **None** | **P0** | 7 | zero gate awareness; open gate shown as claimable READY work; `waits-for` false-ready |
| 7 | Swarms |  | **None** | **P1** | 9 | zero swarm awareness; swarm molecule hidden; concurrency renders but coordination invisible |
| 8 | Data layer (Dolt) |  | **Partial** (faithful local reader) | P2 | 7 | faithful local-Dolt reader (JSONL-as-souvenir honored) but total blind spot on sync/movement |
| 9 | Quality & hygiene |  | **None** | P2 | 6 (+1 disproven) | no graph-hygiene signals; cycle detection computed then discarded; lint/orphan/stale never reach UI |

---

## Severity × value ranking (the deduped inventory)

Every gap from the 9 sections, deduped and ordered by **severity first, then
value/leverage** (cheap-fix-closing-real-misrepresentation beats expensive nice-
to-have). "Source" cites the originating section + its local gap number.

### P0 — display misrepresents state so a user acts on the wrong bead

| Rank | Gap (deduped) | Source(s) | Value / leverage | Follow-up |
|------|---------------|-----------|------------------|-----------|
| 1 | **`waits-for` is not a blocking edge in lane derivation.** `_has_unmet_blocking_dep` (`lanes.py:126`) and the epic-strip check (`lanes.py:236`) gate only on `blocks`/`blocked-by`, so a bead gated solely by an unmet `waits-for` fanout edge is computed `ready` and rendered in the **READY lane** while bd excludes it from `bd ready` — blocked-shown-as-ready. | dep-graph#1, gates#1 (**2× P0, same code site**) | **Highest.** One blocker-set edit (honor vacuous-satisfy on a childless spawner) closes 2 P0s. | **FB-1** [TOP] |

### P1 — a board-meaning concept is silently wrong or absent

| Rank | Gap (deduped) | Source(s) | Value / leverage | Follow-up |
|------|---------------|-----------|------------------|-----------|
| 2 | **No per-type visual treatment.** All 9 types + `event` render as identical uppercase grey `.bead-type` text (`bead_card.html:33`, `styles.css:800-805`); the guide's glyph system (●▲■○◆◇↗▸◎) is wholly unreflected, so a `milestone`/coordination bead looks like a `chore`. Root of the gate (area 6) and mol-type (area 5) legibility gaps. | anatomy#1 | High; board-wide. Lifts gate/swarm/mol legibility too. | **FB-2** |
| 3 | **Open gate beads render as claimable READY work.** `gate` is neither epic nor molecule and its own `blocks` edge points *outward*, so an open gate satisfies "open + no unmet blocker" → READY lane (`lanes.py:314-345`). A *wait condition* is presented as actionable work — the rubric's canonical P1. | gates#2 | High. The gate→target block already works (`lanes.py:337`); only the gate-side framing is wrong. | **FB-3** |
| 4 | **`pinned`/`hooked` have no lane → shown as Deferred.** Both fall through the `else` catch-all (`lanes.py:341-342`); the masthead shows a `pinned`/`hooked` count with **no matching lane**. Never-auto-close infra and molecule machinery are read as intentionally-parked work. | status#1, status#2 (same `else` hole) | Medium. One explicit branch / badge closes both. | **FB-4** |
| 5 | **Swarm molecules are hidden from the board.** The type-only `_is_molecule` filter (`lanes.py:101-113,326`) sweeps up `mol_type=swarm` molecules with redundant formula-pour wrappers, so a running swarm — the only object carrying the coordinator + rollup — never earns a card (reachable only by direct modal URL). | swarms#1 | Medium. Split `mol_type=swarm` from pour wrappers (don't un-hide the latter). | **FB-5** |

### P2 — a capability is unsurfaced where showing it would materially improve fidelity

Ordered by value within P2 (free / already-held data first).

| Rank | Gap (deduped) | Source(s) | Follow-up |
|------|---------------|-----------|-----------|
| 6 | **Cycle detected then discarded** (`_topo_component_order` `lanes.py:196` → `:201`); a deadlocked pair shows as ordinary Blocked. **Structural orphan / dangling-target edge** masked as plain Blocked (`lanes.py:130-132`). **No `bd lint` template-completeness signal** — a `bug` missing `## Steps to Reproduce` looks identical to a complete one. All three are *enrichment from data bdboard already has or can derive*. | quality#1, quality#3, quality#2 | **FB-6** (cycle badge is nearly free) |
| 7 | **Single-flight framing drops the `in_progress` masthead KPI.** `counts()` docstring + `counts_skeleton.html` ("only one item is in-progress") omit the cell; real `counts()` re-adds it via catch-all when >0 → layout jitter, and the framing contradicts bdboard's general-purpose multi-WIP mission. | status#3, swarms#7 (dedup) | **FB-7** |
| 8 | **No sync-state visibility.** bdboard reads *local* Dolt and never calls `bd dolt status/remote`, so unpushed-local / behind-origin is invisible; the `live · push` pill (`base.html:543`) reflects only the SSE socket and is confusable with `bd dolt push`. | data-layer#1, data-layer#4 | **FB-8** |
| 9 | **No gate/coordination overview.** bdboard never calls `bd gate list/check` or `bd merge-slot check`; `await_type`/`await_id` render only as raw alphabetical scalar rows (no PR/run link, no timer deadline); merge-slots are indistinguishable from work (`gt:slot` only a modal chip, `metadata.holder/waiters` dumped as raw JSON). | gates#5, gates#3, gates#4 | **FB-9** |
| 10 | **Molecule / swarm structure not legible as a unit.** Poured children scatter across status lanes with no epic→children rollup; bd's `swarm status` (progress/Completed/Active/Ready/Blocked) and `swarm validate` **waves** (parallel groups, max parallelism) have no representation. `bd mol progress` / `bd swarm status` would back a rollup. | formulas#2, swarms#2, swarms#3 | **FB-10** |
| 11 | **Vapor-phase pour warning swallowed.** `pour_formula` reads stderr only on non-zero exit (`bd.py:825-827`); a `phase:"vapor"` formula warns on stderr with **exit 0**, so bdboard silently creates **persistent, git-synced** beads the author meant to be ephemeral. The one genuine write-surface misrepresentation. | formulas#1 | **FB-11** |
| 12 | **Data-layer staleness honesty.** Closed lane + CLOSED KPI silently clip closures older than `BOARD_CLOSED_WINDOW_DAYS=3` with no affordance; a *sustained* refresh failure freezes the board on stale data with only a log line (no UI banner). | data-layer#2, data-layer#3 | **FB-12** |
| 13 | **Swarm interaction log never read.** `.beads/interactions.jsonl` (llm_call/tool_call/label reward entries — the SFT/RL trail) is absent; the audit panel only reads per-bead `bd history`. | swarms#5 | **FB-13** |
| 14 | **Anatomy field-render polish.** `design` renders unformatted and sorts to the alphabetical tail (in registry as `md`, absent from `_FIELD_ORDER`+`_KIND_MARKDOWN`); the `issue_type` edit dropdown is lossy (6 of 9 types — `spike`/`story`/`milestone` unselectable); magic labels (`dim:val`, `gt:slot`, `provides:X`) render as undifferentiated chips. | anatomy#3, anatomy#2, anatomy#5 | **FB-14** |

### P3 — minor gap; workaround exists or impact is narrow

| Gap (deduped) | Source(s) | Disposition |
|---------------|-----------|-------------|
| No DAG/graph visualization — lanes + 1-D epic strip only; none of the guide's 5 render formats (esp. interactive D3). | dep-graph#2 | Promote to a view later; lanes still convey readiness. |
| `waits-for`/`external` have no `_dep_label` map entry (raw token); blocking vs advisory edges render with identical weight. | dep-graph#3, dep-graph#4 | Fold into FB-1/FB-9 styling. |
| No shipped status-transition affordance (claim/block/defer/close designed in `bdboard-o9v.6`, not built). | status#4 | Read-only is a legitimate stance; ship o9v.6 only if wanted. |
| Auto-key generation unsurfaced (create form forces a key); `bd recall` permalink not wired (mitigated by full-body cards); no recency ordering (upstream bd has no timestamp); forget-nonexistent → 500 not soft no-op. | memories#1,#2,#3,#4 | Small polish beads; memory view is already high-fidelity. |
| No wisp/ephemeral pour option; other mol verbs (`bond`/`squash`/`distill`/`progress`) unsurfaced. | formulas#4, formulas#5 | `bd mol progress` would back FB-10. |
| Pending vs resolved gate state shown only by lane (misframed). | gates#6 | Falls out of FB-3. |
| `execution_*` hints only a raw JSON blob; required-skills prose not badged; concurrent beads not clustered by swarm/wave. | swarms#4, swarms#6, swarms#8 | Falls out of FB-5/FB-10. |
| `live · push` relabel; no read-only/never-exports badge; no workspace (engine/remote/backup/kv) panel. | data-layer#4,#5,#7 | #4 folds into FB-8. |
| No `stale` age-flag badge; no commit-referenced `orphans` feed (needs git-log source). | quality#4, quality#5 | Stale is easy (timestamps shown); orphans needs new data reach. |

### P4 — cosmetic / future-proofing / deliberate boundary / disproven

| Gap | Source(s) | Disposition |
|-----|-----------|-------------|
| Composition fields (`mol_type`/`ephemeral`/`wisp_type`/`skills`) shown but unbadged; mol-type/phase blindness. | anatomy#8, formulas#3 | Falls out of FB-2/FB-10. |
| `external:<proj>:<cap>` edges unlabeled (bd hides them anyway). | dep-graph#5 | Out of scope until external deps in play. |
| Blocked lane conflates status-blocked vs dep-blocked; `counts.html` raw status-key labels. | status#5, status#6 | Cosmetic sub-badges. |
| Create-time key-collision warned only statically (faithful to upsert). | memories#5 | Optional confirm-on-overwrite. |
| `_diff_issue` details only `{status,priority,assignee}`; merge-slot/swarm metadata churn collapses to "changed metadata". | gates#7, swarms#9 | Cosmetic high-signal-set extension. |
| Active-only first paint can transiently mis-derive blocked-by-closed (~1 refresh, self-healing). | data-layer#6 | Known trade-off. |
| Duplicates/find-duplicates not surfaced. | quality#6 | Low value; fuzzy matching noisy. |
| **`bd memory` wing/scope/BM25** — **NO ACTION**, refuted as not-bd. | memories#6 | See "NOT a gap". |
| **Molecule-wrapper hiding (Option A)** — **NO ACTION**, correct. | formulas#6 | See "NOT a gap". |
| **swarm → area 7** cross-ref only. | formulas#7 | Counted once, in area 7. |
| **`doctor`/`preflight` absent** — **DISPROVEN**, correctly out of scope. | quality#7 | See "NOT a gap". |

---

## Dedup & cross-section reconciliation notes

- **Two P0s → one root cause.** dep-graph#1 and gates#1 are the *same*
  `waits-for`-not-in-the-blocker-set hole at `lanes.py:126` (mirrored `:236`).
  Merged into **FB-1**. The `blocks` gating already in place is the proven
  template; the fix must honor vacuous-satisfy (a childless spawner → waiter is
  ready) and not break the `_dep_label` mapping.
- **Flat type rendering surfaces in three areas.** anatomy#1 (all types look the
  same) is the *root*; gates#2 (gate shown as ready work) and formulas#3
  (mol-type blindness) are downstream. anatomy#1 → **FB-2** (glyph system);
  gates#2 → **FB-3** (needs gate-state framing beyond a glyph); formulas#3 is
  subsumed by FB-2/FB-10. The memory `bdboard-anatomy-type-flat` is the shared
  evidence — don't re-file "types look identical" per area.
- **Single-flight framing appears twice.** status#3 and swarms#7 are the same
  `counts()`/`counts_skeleton.html` bug → **FB-7** (one fix). **Multi-WIP
  rendering itself is NOT a gap** (proven by injection in both sections) — see
  "NOT a gap".
- **`pinned` + `hooked`** are the same `else` catch-all (status#1, status#2) →
  one **FB-4**.
- **The `lanes.py` blocked-ness logic is a hot spot.** waits-for (FB-1), cycles
  (quality#1), dangling edges (quality#3), and the one-hop check all live in
  `_has_unmet_blocking_dep`/`_topo_component_order`. FB-1 and FB-6 must
  coordinate so the badge/blocker work isn't double-filed across areas 2 & 9.
- **`waits-for` is split correctly across sections.** The *edge gating* is area 2
  / area 6 (FB-1); the *fanout aggregation mode* (`all-children`/`any-children`)
  is **not surfaceable** because bd v1.0.4 doesn't expose it (gates D3) —
  recorded as faithful-by-design, not a gap.
- **Molecule rollup is one need from two angles.** formulas#2 (`bd mol progress`)
  and swarms#2/#3 (`bd swarm status`/`validate` waves) both want an epic-as-a-
  unit rollup → merged into **FB-10**.
- **Two "audit trails" are different things.** The modal "Audit trail"
  (`bd history`, per-bead) is NOT the swarm interaction log
  (`.beads/interactions.jsonl`, cross-run). Counted separately; the latter is
  FB-13.
- **`bdboard-fjk` is RESOLVED.** Edge-direction correctness (the area-2 headline
  P0 risk) is fixed and judges-passed; `_dep_label` derives the label from type
  AND direction. **No P0 is assigned to direction** — recorded so synthesis
  doesn't resurrect a closed bug.

---

## Prioritized top-gaps shortlist → recommended follow-up beads

Concrete, ready-to-pour. **Recommendations only** — a planner/human should
review scope before filing (this synthesis bead files none). Each carries a
suggested `bd create` and a rationale.

### FB-1 — Treat `waits-for` as a blocking edge in lane derivation [TOP]

*Closes 2 P0s (dep-graph#1, gates#1) at one code site.*

```bash
bd create --type=bug --priority=1 \
  --title='Treat waits-for as a blocking edge in lane derivation (blocked-shown-as-ready)' \
  --description='_has_unmet_blocking_dep (lanes.py:126) and the epic-strip blocker check (lanes.py:236) gate only on ("blocks","blocked-by","blocked_by"). waits-for is one of bd two blocking edge types (field guide ch2 2.4 / ch6 VI), so a bead gated solely by an unmet waits-for fanout edge is computed ready and rendered in the READY lane while bd excludes it from bd ready -- a blocked-shown-as-ready P0 (same class as bdboard-fjk). Add "waits-for" to the blocker set, honoring vacuous-satisfy (a childless spawner means the waiter is genuinely ready). ## Acceptance Criteria\n- a bead gated by an unmet waits-for edge lanes as Blocked, not Ready\n- a waits-for bead whose spawner has no open children stays Ready (vacuous-satisfy)\n- the _dep_label mapping is unaffected (no reversal regression)\n- fixture test covers both the gated and vacuous cases'
```

### FB-2 — Per-type glyph/badge system on cards + modal [HIGH]

*Closes the flat-type root (anatomy#1); lifts gate/swarm/mol legibility.*

```bash
bd create --type=task --priority=1 \
  --title='Render a per-type glyph/badge instead of flat grey issue_type text' \
  --description='All 9 bead types + event render as identical uppercase grey .bead-type text (bead_card.html:33, styles.css:800-805; modal scalar row). The field guide glyph system (task ● bug ▲ feature ■ chore ○ epic ◆ decision ◇ spike ↗ story ▸ milestone ◎) is wholly unreflected, so a milestone/gate/coordination bead is indistinguishable from a chore at a glance (memory bdboard-anatomy-type-flat). Map issue_type -> glyph + color on the card and in the modal header. ## Acceptance Criteria\n- each built-in type renders a distinct glyph + color on the card\n- the modal header shows the type glyph\n- an unknown/custom type falls back to the current grey text (no crash)'
```

### FB-3 — Make gate beads first-class (not claimable ready work)

```bash
bd create --type=task --priority=1 \
  --title='Special-case issue_type=gate so an open gate is shown as a wait, not ready work' \
  --description='gate beads flow through generic bucketing; an open ad-hoc gate has no unmet blocker of its own (its blocks edge points outward) so it lands in the READY lane as claimable work (lanes.py:314-345) -- the rubric canonical P1. Also surface the await condition: await_type/await_id render only as raw alphabetical scalar rows (app.py:1580-1588) -- never a PR/run link, timer deadline, or manual-only bead-gate flag. Special-case issue_type=gate (own treatment/badge, framed as a pending wait) and parse await_type/await_id into a labeled gate-condition row. ## Acceptance Criteria\n- an open gate is not presented as claimable READY work\n- gh:pr/gh:run await_id render as links; timer shows a deadline; bead gate flagged manual-only\n- the gate->target blocks edge (already correct) is unchanged'
```

### FB-4 — Give `pinned`/`hooked` an explicit lane/badge

```bash
bd create --type=task --priority=1 \
  --title='Handle pinned/hooked statuses explicitly instead of dumping them in Deferred' \
  --description='pinned and hooked have no lane branch and fall through the else catch-all (lanes.py:341-342), so never-auto-close infra (pinned) and molecule/formula machinery (hooked) are shown as intentionally-parked Deferred work; the masthead also shows a pinned/hooked count with no matching lane. Add explicit handling (own lane or distinct card badge; consider hiding hooked like molecule wrappers). ## Acceptance Criteria\n- a pinned bead is visually distinct from a deferred bead\n- a hooked bead is handled explicitly (badge or hidden), not shown as Deferred\n- masthead counts and lanes agree (no count without a lane)'
```

### FB-5 — Surface swarm molecules on the board

```bash
bd create --type=task --priority=2 \
  --title='Split mol_type=swarm from formula-pour wrappers so running swarms are visible' \
  --description='The type-only _is_molecule filter (lanes.py:101-113,326) hides ALL molecule beads to suppress the redundant formula-pour grouping wrapper -- but it also hides mol_type=swarm molecules, the only object carrying a swarm existence, coordinator/assignee, and bd swarm list rollup. A running swarm is invisible on the board (reachable only by direct modal URL). Detect mol_type=swarm and surface it (own strip/badge) while still hiding pour wrappers. ## Acceptance Criteria\n- a mol_type=swarm molecule earns a card/badge with its coordinator\n- formula-pour grouping wrappers remain hidden (no regression to Option A)\n- a non-swarm molecule wrapper is unchanged'
```

### FB-6 — Surface graph-hygiene signals bdboard already has

*Cycle detection is already computed and discarded — nearly free.*

```bash
bd create --type=task --priority=2 \
  --title='Surface cycle / dangling-edge / incomplete-template badges in the lanes' \
  --description='bdboard surfaces zero graph-hygiene signals. (1) A dependency cycle is already detected in _topo_component_order (lanes.py:196) then silently discarded (:201) -- a deadlocked pair shows as ordinary Blocked; keep the result and badge affected beads (nearly free). (2) A structural orphan edge (blocks target absent from the snapshot) is masked as plain Blocked via the conservative target-is-None branch (lanes.py:130-132); distinguish blocked-by-missing from blocked-by-open. (3) No bd lint signal -- a bug missing ## Steps to Reproduce renders identically to a complete one; derive per-type required-section completeness and badge incomplete beads. ## Acceptance Criteria\n- beads in a cycle carry a cycle/deadlocked badge (reuse the existing detection)\n- a bead blocked by a missing/unknown target is visually distinct from blocked-by-open\n- incomplete-template beads show an indicator (per-type required sections)'
```

### FB-7 — Drop the single-flight framing; make `in_progress` a first-class masthead cell

```bash
bd create --type=task --priority=2 \
  --title='Make in_progress a fixed masthead KPI and drop the single-flight framing' \
  --description='counts() docstring (lanes.py:390-399) and counts_skeleton.html assert "bdboard is a single-flight workflow tool -- only one item is in-progress at a time" and omit the in_progress cell; real counts() re-adds it via the catch-all when >0, so the masthead grows a 5th cell on hydration (layout jitter) and the framing contradicts bdboard general-purpose multi-WIP mission (proven: lanes render N>1 cleanly). Make in_progress a first-class fixed cell matching the skeleton; remove the single-flight prose. ## Acceptance Criteria\n- in_progress is a fixed masthead cell present in both skeleton and live counts\n- no layout jitter on hydration\n- the single-flight docstring/comment is removed'
```

### FB-8 — Add sync-state visibility (and relabel the `live · push` pill)

```bash
bd create --type=task --priority=2 \
  --title='Show Dolt sync state (ahead/behind/no-remote) and relabel the live pill' \
  --description='bdboard reads local Dolt and never calls bd dolt status/remote, so unpushed-local-writes (ahead of origin) and unpulled-remote-writes (behind origin) are invisible -- a teammate bd dolt push leaves your board silently stale-vs-origin. The masthead live . push pill (base.html:543) reflects only the SSE socket and is confusable with bd dolt push. Add a sync badge shelling bd dolt status / bd dolt remote list, and relabel the pill (e.g. live . updates). ## Acceptance Criteria\n- a sync badge shows unpushed/behind/no-remote state\n- shelling bd dolt status soft-fails (no 500) when no remote is configured\n- the live pill no longer reads as a Dolt-sync indicator'
```

### FB-9 — Gates/coordination panel + merge-slot affordance

```bash
bd create --type=task --priority=2 \
  --title='Add a gates/coordination panel (bd gate list) and a merge-slot mutex affordance' \
  --description='bdboard never calls bd gate list/check or bd merge-slot check, so there is no gate overview, no pending-gate count, and merge-slots are indistinguishable from regular work (gt:slot only a modal chip; metadata.holder/waiters dumped as raw JSON, field_row.html:71). Add a gates/coordination panel shelling bd gate list --json (optional gate check/merge-slot check), and detect gt:slot to render an available/held-by-X + waiter-queue mutex affordance. ## Acceptance Criteria\n- a gates panel lists open gates with their await condition\n- a merge-slot renders held/available + the waiter queue (not raw JSON)\n- bd verb failures degrade gracefully (inline message, not 500)'
```

### FB-10 — Molecule / swarm rollup (progress + waves)

```bash
bd create --type=task --priority=2 \
  --title='Add an epic->children rollup backed by bd mol progress / bd swarm status + validate waves' \
  --description='Poured molecule children scatter across status lanes with no grouping/progress rollup back to the parent epic (formulas#2), and bd swarm computed state -- progress %, Completed/Active/Ready/Blocked, coordinator, and the swarm validate WAVE model (parallel groups, max parallelism, worker-sessions) -- has no representation (swarms#2/#3). Add an epic-strip rollup (count/progress) backed by bd mol progress <id> --json, and a swarm view shelling bd swarm status/validate. ## Acceptance Criteria\n- the epic strip shows a child count/progress rollup\n- a swarm surfaces progress % and Completed/Active/Ready/Blocked\n- waves (Wave N, max parallelism) are legible for a swarmable epic'
```

### FB-11 — Surface the vapor-phase pour warning

```bash
bd create --type=bug --priority=2 \
  --title='Capture pour stderr on success and warn when a vapor-phase formula is poured as persistent' \
  --description='pour_formula reads stderr only on non-zero exit (bd.py:825-827); bd mol pour prints the "you poured a vapor-phase formula" warning on stderr with exit 0, so bdboard silently creates persistent, git-synced beads the formula author meant to be ephemeral (wisp). This is the one genuine write-surface misrepresentation in the pour flow. Capture pour stderr even on success and surface a "this formula recommends wisp (ephemeral) -- poured as persistent" notice. ## Acceptance Criteria\n- a vapor-phase pour surfaces the recommend-wisp warning in formula_pour_result.html\n- a normal (liquid) pour is unchanged\n- the atomic pour result is never lost on a warning'
```

### FB-12 — Data-layer staleness honesty

```bash
bd create --type=task --priority=2 \
  --title='Label the closed-window and surface sustained refresh-failure staleness' \
  --description='The Closed lane and CLOSED KPI only show closures within BOARD_CLOSED_WINDOW_DAYS=3 (lanes.py:40, bd.py:298-304) with no affordance, so a user cannot tell "no old closures" from "old closures hidden". And a sustained bd list failure freezes the board on the previous snapshot (store.py serve-stale-on-failure) with only a log line -- no UI banner. Label the Closed lane with its window (+ a "see History for older" link), and show a "data stale -- last updated HH:MM" banner after N consecutive refresh failures. ## Acceptance Criteria\n- the Closed lane states its active window and links to the uncapped History\n- a sustained refresh failure surfaces a stale banner (not just a log line)\n- a transient single failure does not flash the banner'
```

### FB-13 — Swarm interaction-log viewer

```bash
bd create --type=task --priority=2 \
  --title='Add a viewer for the swarm interaction log (.beads/interactions.jsonl)' \
  --description='The modal Audit trail/Lifecycle views are built entirely from bd history <id> (per-bead Dolt snapshots) and never read .beads/interactions.jsonl, so the cross-run llm_call/tool_call/label reward trail (the SFT/RL "why did the agent do that" signal) is absent. Add an interaction-log viewer (separate from the per-bead history). ## Acceptance Criteria\n- the interaction log is readable in the UI (filter by kind: llm_call/tool_call/label)\n- the existing per-bead bd history audit is unchanged\n- a missing interactions.jsonl degrades gracefully'
```

### FB-14 — Anatomy field-render polish

```bash
bd create --type=task --priority=2 \
  --title='Render design as markdown + ordered, de-lossify the type dropdown, decode magic labels' \
  --description='Three anatomy field-render nits: (1) design is markdown-bearing (registry editor=md) and emitted by bd show --long, but absent from _FIELD_ORDER (sorts to the alphabetical tail) and _KIND_MARKDOWN (app.py:1362), so ADR rationale loses formatting -- add it to both. (2) The issue_type inline-edit dropdown _ISSUE_TYPE_OPTIONS (app.py:1441) lists only 6 of 9 types, so editing a spike/story/milestone cannot preserve its type -- source from bd types or add the missing built-ins. (3) Magic labels (dim:val, gt:slot, provides:X, export:X, template) render as undifferentiated chips -- style/decode them distinctly. ## Acceptance Criteria\n- design renders as markdown in the content group order\n- the type dropdown can select every built-in type (non-lossy)\n- magic labels are visually distinct from freeform tags'
```

> **P3/P4 items** (the two lower tables above) are recorded for completeness but
> are **not** recommended for immediate filing — they're narrow-window, fall out
> of the FB-N work above, deliberate boundaries, or disproven. A planner can
> promote any of them later; the verbatim follow-up lines live in each section's
> GAPS table.

---

## What is explicitly NOT a gap (so a future planner doesn't re-litigate)

- **Multi-`in_progress` / general-purpose use is the INTENDED design.** The
  In-Progress lane renders N>1 concurrent beads with **no cap** (proven by
  injection in status §2.2 and swarms §2.8). bdboard is general-purpose — any
  developer can point it at **any** bd workspace. The surviving single-WIP
  *assumption* lives **only** in `counts()`/`counts_skeleton.html` prose+layout
  (a framing bug → **FB-7**); it is **not** evidence that single-WIP is the
  intended model. **Do not re-litigate multi-WIP as a defect — it is a goal.**
- **bd memory has no wing / scope / BM25 ranking.** Those are code-puppy
  *kennel* concepts (`repo:`/`agent:`/`user:` wings, ranked recall), **not** bd.
  bd's memory layer is a flat, single-namespace, unranked key→body map
  (verified, memory `bd-memory-layer-flat-unranked`); bdboard's flat alphabetical
  list + substring search **is** the faithful design. **Do not file "add scope
  filter / ranked search."** (memories#6.)
- **Read-mostly posture / not absorbing every bd verb.** bdboard not invoking
  most write/coordination/maintenance verbs (gate resolve, swarm create, mol
  bond/squash/distill, dolt push, compact/gc) is its SRP stance. The gaps are
  about *displaying* state legibly, not turning bdboard into a full bd CLI. The
  recommended FBs add *read* panels (or one honest write notice, FB-11), not a
  mandate to mirror every verb.
- **Molecule-wrapper hiding (Option A) is correct.** The formula-pour grouping
  wrapper is the true single parent but has no `blocks` edges and no board value;
  hiding it (with the epic-root rename so repeat pours are distinguishable) is a
  recorded, sound decision (ADR 0007 / grouping-node decision). **Do not file
  "show the wrapper."** (formulas#6.) FB-5 is different — it un-hides only the
  `mol_type=swarm` case the type-only filter wrongly sweeps up.
- **JSONL-as-souvenir / never writing `.beads/`.** Reading bd-CLI-JSON over
  `issues.jsonl`, never writing `.beads/`, and the single-writer subprocess gate
  are all **correct** reflections of the chapter-8 doctrine (anti-pattern #1,
  embedded single-writer). They are strengths (data-layer §2.1–2.3), not gaps.
- **`doctor` / `preflight` absent.** `doctor` is server-mode/env-specific and
  unsupported in embedded Dolt (the default); `preflight` is a beads-*codebase*
  contributor PR checklist. Neither belongs on a general-purpose board —
  **correctly absent** (quality#7, disproven).
- **`until` ignored for gating.** Correct per the field guide (non-gating edge,
  an explicit Vol I correction). Because the blocker set is an allow-list of
  `blocks` variants, `until` is non-blocking by design — **do not "fix" it into
  a blocker** (dep-graph notes).
- **Edge-direction correctness (`bdboard-fjk`) is RESOLVED.** `_dep_label`
  derives the relationship label from type AND direction in one place (judges
  passed). There is no reversal for the 10 mapped types — **do not reopen.**
- **Read-only / no status-transition affordances** is a legitimate stance. The
  o9v.6 transition design exists but shipping it is optional (status#4), not a
  fidelity defect.
