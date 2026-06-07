# Gates & Coordination — Coverage Findings

> Owner bead: bdboard-6yvg. Field-guide chapter: `field-guide-06-gates-and-coordination.html` (chapter 6).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `gates-coordination`                           |
| Field-guide ref  | `field-guide-06-gates-and-coordination.html` (chapter 6) |
| bdboard owner    | `bdboard-6yvg`                                 |
| Primary sources  | `src/bdboard/derive/lanes.py` (`_is_epic`, `_is_molecule`, `_has_unmet_blocking_dep`, `lanes()`, `counts()`); `src/bdboard/app.py` (`_dep_label`, `_FIELD_ORDER`, `_classify_field`, `_ordered_fields`, `_diff_issue`); `templates/partials/{bead_card,field_row,bead_modal}.html`; `notes/catalog/board-lanes.md` |
| Status           | `done`                                         |

---

## 1. AVAILABLE — what the field guide documents

Source note: chapter 6's rendered prose ships as a compressed React/`__bundler`
payload (not extractable as plain text — same constraint recorded in chapters 3
& 7). The feature surface below is sourced from the chapter's **verified
reference outline**
(`training/beads/volumes/field-guide-06-gates-and-coordination/OUTLINE.md`,
audited against bd v1.0.4 `ce242a879` in an isolated `gate`-prefix sandbox),
which supersedes the slide bundle and is a stronger citation.

Chapter 6 ("Gates & Async Coordination") documents how bd makes one bead **wait**
on an external/async condition before becoming runnable. Two distinct mechanisms
plus an exclusive-access primitive:

- **A gate IS a bead** (OUTLINE §I). `bd gate create --blocks <id>` produces a
  dedicated **`issue_type=gate`** bead carrying `await_type`
  (`human`/`timer`/`gh:run`/`gh:pr`/`bead`) and optional `await_id`, wired to the
  target by a **`blocks`** edge (gate → target). `gate` is an **internal** type
  (absent from `bd types`). Auto title `Gate: <type>`, auto description
  `Ad-hoc gate blocking <target>`. The moment the gate exists, the target leaves
  `bd ready`; when the gate closes, the target returns.
- **Five gate types + await-id formats** (OUTLINE §II): `human` (no await-id,
  manual close), `timer` (`--timeout` Go-duration, auto-resolves when
  `now > created_at + timeout`), `gh:run` (await-id = Actions run ID; resolves on
  `completed`+`success`, escalates on `failure`/`canceled`), `gh:pr` (await-id =
  PR number; resolves `MERGED`, escalates `CLOSED`), `bead` (await-id =
  `<rig>:<bead-id>`; resolves when the cross-rig target closes — **but** see §V).
- **The gate verb set** (OUTLINE §III): `create`/`list`/`show`/`resolve`/
  `add-waiter`/`discover` (`check` in §IV). `gate list` groups under "Open Gates
  (N)"; `gate show` surfaces `Await Type` + waiters; `gate resolve` ≡
  `bd close`; `add-waiter` registers a **worker address** for a wake
  notification (NOT a bead-parking blocker; `bd gate wake` is not real in 1.0.4).
- **The `gate check` engine** (OUTLINE §IV): the polling evaluator that **closes
  resolved gates** and (`--escalate`) escalates failed ones. `--type` filters
  (`gh`/`gh:run`/`gh:pr`/`timer`/`bead`/`all`), `--dry-run`, summary line
  `Checked N gates: R resolved, E escalated, X errors`.
- **Bead gates are addressable but cross-rig auto-resolution is REMOVED in
  v1.0.4** (OUTLINE §V, D5): `gate check --type=bead` reports
  `pending - ... cannot be checked (multi-rig routing removed)`. Bead gates are
  manually resolvable only.
- **Fanout & aggregation** (OUTLINE §VI) is a **separate mechanism** from gate
  beads, built on a **`waits-for` dependency edge** (`--waits-for <spawner>`)
  plus an aggregation mode `--waits-for-gate all-children` (default) /
  `any-children`. It is evaluated by the **ready/blocked computation**, NOT by
  `gate check`. Verified semantics: a childless spawner is **vacuously satisfied**
  (waiter is `ready`); once the spawner has open children the waiter **drops out
  of `bd ready`** (blocked) until all (or any) children close. The mode itself is
  **not surfaced** in `show --json` / `dep list` / `metadata` (D3) — it's a
  behaviour, not a displayed field.
- **Merge-slots** (OUTLINE §VII): bd's exclusive-access primitive — a mutex made
  of a bead. **One slot per rig**, id `<prefix>-merge-slot`, label **`gt:slot`**.
  State: `status=open` (available) / `status=in_progress` (held),
  `metadata.holder`, `metadata.waiters` (priority-ordered queue). Verbs
  `create`/`check`/`acquire` (`--wait` to queue) /`release`. **Advisory queue**
  (D4): `release` does NOT auto-promote, `acquire` does NOT dequeue — fair
  hand-off is a convention, only single-holder acquire + holder-checked release
  are enforced.
- **Gates inside formulas** (OUTLINE §VIII): a formula step's `gate` field is
  auto-created as a gate bead on pour; `bd mol ready --gated` resumes molecules
  parked at a now-closed gate (cross-ref chapter 5).

## 2. REFLECTED — what bdboard actually displays

**Headline: bdboard has ZERO gate/coordination awareness.** A repo-wide search
for `gate` (the coordination noun), `await`, `await_type`, `await_id`,
`merge-slot`, `gt:slot`, and `waits-for` across `src/bdboard/**` and
`notes/catalog/**` returns **no feature code** — only unrelated hits
(`_subprocess_gate` the asyncio semaphore, the "status gate" for field-edit
locking at `app.py:1072-1093`, and awaited coroutines). bdboard never calls
`bd gate {list,show,check,resolve}` or `bd merge-slot {check,...}`, never reads
`await_type`/`await_id` semantically, and never special-cases the `gt:slot`
label. Every coordination concept is reduced to its generic-bead representation.
Itemized:

### 2.1 Gate beads render as plain work — no gate-state affordance

`gate` is neither an epic (`_is_epic`, `lanes.py:97`) nor a molecule
(`_is_molecule`, `lanes.py:101`), so a gate bead flows straight through the
generic bucketing in `lanes()` (`lanes.py:314-345`). An **open ad-hoc gate has
no blocking dependency of its own** (its `blocks` edge points *outward* to the
target as a `dependent`; `_has_unmet_blocking_dep` at `lanes.py:120-135` only
inspects the bead's *own* `blocks`/`blocked-by` deps). So the gate satisfies
`status == "open"` with no unmet blocker and lands in the **READY lane**
(`lanes.py:342`) — i.e. it is presented as **actionable, claimable work** when it
is in fact a *wait condition*. On the card (`bead_card.html`) it shows id +
priority + title (`Gate: human`) + the flat `issue_type` text "gate"
(`bead_card.html` `bead-type` span). Per the anatomy audit
(`01-anatomy.md`, memory `bdboard-anatomy-type-flat`), all 9 types + gate render
as identical uppercase grey `.bead-type` text — so "gate" is **weakly**
distinguishable as a type label but carries **no** gate-state semantics, no
"pending wait" badge, no await-condition.

### 2.2 `await_type` / `await_id` surface only as raw alphabetical scalar rows

Neither `await_type` nor `await_id` is in `_FIELD_ORDER` (`app.py:1314-1346`), so
they fall to `_ordered_fields`' second pass (`app.py:1580-1588`) that appends
unknown keys **alphabetically**. `_classify_field` (`app.py:1515-1530`) types a
plain string as `scalar`, and neither key is in `_SHORT_META_FIELDS`
(`app.py:1366-1385`), so they render as full-width raw rows (`field_row.html:81`
else-branch → `{{ f.val }}`): literally `await_type: human` / `await_id: 42`.
There is **no interpretation**: a `gh:pr` gate's `await_id=42` is not a link to
PR #42, a `timer` gate shows no countdown / deadline (the `--timeout` isn't even
a stored field bd surfaces), a `gh:run` await-id is not a run link, and a `bead`
gate's `<rig>:<bead-id>` is inert text (consistent with bd's own removed cross-rig
routing, but bdboard gives no hint the condition is unpollable). The await
condition — the entire point of a gate — is conveyed as undifferentiated key:value
text buried below the alphabetical fold of the modal.

### 2.3 The gate→target block IS reflected (the one thing that works)

The **target** of a gate is handled correctly: the gate appears in the target's
dependency list as a `blocks` edge, so `_has_unmet_blocking_dep`
(`lanes.py:120-135`) sees an open blocker and routes the target to the **BLOCKED
lane** (`lanes.py:337-340`) — matching bd dropping it from `bd ready`. In the
modal the dep row (`field_row.html:38-58`) renders `_dep_label('blocks',
'dependencies')` → **"blocked by"** (`app.py:51-88`) plus the gate's id, status,
and title (`Gate: human`). So a user *on the target* gets a partial signal — "I'm
blocked by something called Gate: human" — but must manually click through, and
nothing labels that blocker as a *gate* with a *condition*. This is the correct
half; the gate-side (§2.1) and the await-condition (§2.2) are the gaps.

### 2.4 CRITICAL — `waits-for` fanout edges are NOT treated as blockers (P0)

`_has_unmet_blocking_dep` (`lanes.py:126`) and the epic-strip blocker check
(`lanes.py:236`) both gate on `dep_type not in ("blocks", "blocked-by",
"blocked_by")` — **`waits-for` is not in the set**. A bead created with
`--waits-for <spawner>` therefore has its blocking dependency **ignored**: with
`status=open` and no recognized blocker it routes to the **READY lane**
(`lanes.py:342`). But per AVAILABLE §VI, once the spawner has open children that
waiter is **excluded from `bd ready`** (functionally blocked). So bdboard shows
**Ready** for a bead bd considers **blocked** — the textbook P0 misrepresentation
(blocked-shown-as-ready, the same failure class as the reversed-dep `bdboard-fjk`
P0). bdboard also can't evaluate the `all-children`/`any-children` aggregation
(bd doesn't surface the mode — D3 — and bdboard reads no children rollup), so it
has no path to compute the real readiness. Honest edge: when the spawner is
**childless**, the waiter is vacuously ready and bdboard's Ready placement
happens to be correct — but that is luck, not logic. In the modal the `waits-for`
edge at least renders **visibly** as raw `waits-for <id>` (`_dep_label` falls
through to the raw-type fallback, `app.py:84-88`), so the relationship is shown;
it's the **lane classification** that lies.

### 2.5 Merge-slots are indistinguishable from regular work

A merge-slot is a bead, so it status-buckets like any other: a **held** slot
(`status=in_progress`) lands in the IN-PROGRESS lane (`lanes.py:334`); an
**available** slot (`status=open`, no deps) lands in READY (`lanes.py:342`). The
`gt:slot` label renders as a chip **only in the modal** (`labels` ∈ `_KIND_CHIPS`,
`app.py:1356`; `field_row.html:32-36`) — cards don't show labels
(`bead_card.html` renders no label chips), so on the board a merge-slot is a
**plain card with no mutex/queue affordance**. `metadata.holder` /
`metadata.waiters` are a dict → classified `json` (`app.py:1528`) → dumped as a
raw `<pre>` blob in the metadata row (`field_row.html:71`), never a "held by X,
2 waiting" line or a queue list. There is no "available/held" status, no acquire,
no advisory-queue rendering. (Verified `metadata` IS in `_FIELD_ORDER`,
`app.py:1345`, but only as the catch-all JSON dump.)

### 2.6 No gate/slot overview, no resolve/check affordances

Because bdboard never invokes the coordination verbs, **none** of the operational
surface exists: no `gate list` "Open Gates (N)" view, no pending-gate count in
the masthead (`counts()` tracks only open/blocked/deferred/closed,
`lanes.py:390-410`), no `gate check` resolve/escalate, no `merge-slot
check`/`acquire`/`release`. There is no gate or merge-slot catalog entry;
`notes/catalog/board-lanes.md` documents only the four status-derived lanes.

### 2.7 Pending vs resolved gates: distinguishable only by lane, and misframed

A **pending** (open) gate sits in the READY lane (§2.1); a **resolved** (closed)
gate moves to the CLOSED lane (`lanes.py:330-332`, `_is_closed`). So
pending/resolved ARE distinguishable — but *by the wrong frame*: pending reads as
"ready to work" rather than "actively waiting," and a timer/gh gate gives no clue
whether its condition is met until bd's own `gate check` flips it closed
(invisible to bdboard until the next snapshot). There is no "pending wait" vs
"resolved" gate state shown qua gate.

### 2.8 Gate/slot metadata churn collapses to low-signal audit lines

The per-bead audit (`_diff_issue`, `app.py:1610-1631`, rendered via
`bead_modal.html` audit slot) details old→new only for high-signal keys
(`{status, priority, assignee}` per the swarm audit, `07-swarms.md §2.6`). A
change to a merge-slot's `metadata.holder`/`metadata.waiters` — the *entire*
coordination signal — collapses to a single low-signal `"changed metadata"` line.

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | `waits-for` fanout edges are not in the blocker set (`lanes.py:126,236`), so a bead waiting on a spawner with open children renders in the READY lane while bd excludes it from `bd ready` — blocked-shown-as-ready. | P0 | File a bead: treat `waits-for` as a blocker in `_has_unmet_blocking_dep` (honoring vacuous-satisfy on a childless spawner) so fanout waiters lane as blocked. |
| 2   | Gate beads (`issue_type=gate`) flow through generic bucketing and an open gate lands in READY as plain claimable work (`lanes.py:314-345`) — no gate-state affordance, no "pending wait" framing. | P1 | File a bead: special-case `issue_type=gate` (own treatment/badge; surface as a wait, not ready work). |
| 3   | `await_type`/`await_id` render only as raw alphabetical scalar rows (not in `_FIELD_ORDER`; `app.py:1580-1588`, `field_row.html:81`) — never a human-readable condition (PR/run link, timer deadline, cross-rig target). | P2 | File a bead: parse `await_type`/`await_id` into a labeled gate-condition row (link gh:pr/gh:run, show timer deadline, flag bead gate as manual-only). |
| 4   | Merge-slot beads are indistinguishable from regular work — status-bucketed, `gt:slot` only a modal chip, `metadata.holder`/`waiters` dumped as raw JSON (`field_row.html:71`); no held/available state or queue rendering. | P2 | File a bead: detect `gt:slot` and render a mutex affordance (available/held by X, waiter queue) on the card and modal. |
| 5   | bdboard never calls `bd gate list`/`gate check`/`merge-slot check`, so there is no gate overview, no pending-gate count, and no resolve/escalate/acquire affordance. | P2 | File a bead: add a gates/coordination panel shelling `bd gate list --json` (+ optional `gate check`/`merge-slot check`). |
| 6   | Pending vs resolved gates are distinguishable only by lane (pending→ready, resolved→closed) and pending is misframed as "ready work"; timer/gh condition state is invisible until bd flips it. | P3 | Minor: once gates are first-class (GAP 2), show a pending/resolved gate state rather than relying on the lane. |
| 7   | `_diff_issue` (`app.py:1610-1631`) details only `{status,priority,assignee}`; a merge-slot `metadata.holder`/`waiters` change — the whole coordination signal — collapses to "changed metadata". | P4 | Cosmetic: include holder/waiters (or all `gt:slot` metadata) in the high-signal diff set. |

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

- **The explicit asks, answered:**
  - *Are gate beads distinguishable from plain work?* Only **weakly** — by the
    flat grey `issue_type` text "gate" on the card (`bead_card.html`); there is
    **no** gate-state affordance and an open gate is rendered as **READY/claimable
    work** (GAP 2, P1 — this is the rubric's own canonical P1 example).
  - *Is gate state / await-id surfaced?* `await_type`/`await_id` appear **only**
    as raw alphabetical key:value rows in the modal (GAP 3, P2). Timer/gh gates
    show **no** condition (no deadline countdown, no PR/run link) — just inert
    `await_id` text.
  - *Pending vs resolved distinguishable?* Yes, but only via lane (ready vs
    closed) and pending is **misframed** as ready work (GAP 6, P3).
- **Why GAP 1 is the P0, not GAP 2:** GAP 2 (gate shown as ready) *omits a board
  concept* but the gate itself is not work a user would wrongly act on past a
  glance — textbook P1 ("shown as plain work," verbatim the rubric example). GAP 1
  (`waits-for` ignored) actually **flips a blocked bead to Ready**, so a user
  claims work bd would not have offered — a true P0 state misrepresentation in the
  `bdboard-fjk` class.
- **Faithful-by-design, not gaps:** bd v1.0.4 itself (a) doesn't surface the
  `all-children`/`any-children` mode (D3) and (b) has *removed* cross-rig bead-gate
  auto-resolution (D5). bdboard showing neither is technically faithful to bd's
  own storage — but GAP 1/3 are about *correctly classifying* and *legibly
  labeling* what bd DOES express (the `waits-for` edge, the `await_*` fields), not
  inventing state bd hides.
- **Cross-section:** GAP 1 overlaps chapter 2 (dependency graph,
  `02-dependency-graph.md` / `bdboard-vhke`) — the `waits-for` taxonomy gap lives
  in the same `_has_unmet_blocking_dep` blocker-set as the dep-edge work; the fix
  must extend the blocker set without breaking the dep-label mapping. GAP 5
  overlaps chapter 5 (formula-poured gates) — a gates panel would also surface
  `bd mol ready --gated` molecules. Reference, don't duplicate.
