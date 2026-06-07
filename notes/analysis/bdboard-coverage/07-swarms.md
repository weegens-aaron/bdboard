# Swarms — Coverage Findings

> Owner bead: bdboard-6ljg. Field-guide chapter: `field-guide-07-swarms.html` (chapter 7).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `swarms`                                       |
| Field-guide ref  | `field-guide-07-swarms.html` (chapter 7)                          |
| bdboard owner    | `bdboard-6ljg`                                       |
| Primary sources  | `src/bdboard/derive/lanes.py` (`_is_molecule`, `lanes()`, `activity()`, `counts()`); `src/bdboard/derive/history.py` (`status_timeline`); `src/bdboard/app.py` (`_ordered_fields`, `_FIELD_ORDER`, `_diff_issue`); `templates/partials/{lanes,bead_card,field_row,bead_audit}.html`; `docs/catalog/{board-lanes,bead-audit}.md` |
| Status           | `done`                                  |

---

## 1. AVAILABLE — what the field guide documents

Source note: chapter 7's rendered prose ships as a compressed React/`__bundler`
payload (not extractable as plain text — same constraint recorded in chapter 3's
audit). The feature surface below is sourced from the chapter's **verified
reference outline** (`training/beads/volumes/field-guide-07-swarms/OUTLINE.md`,
audited against bd v1.0.4 `ce242a879` with a hands-on sandbox), which supersedes
the slide bundle and is a stronger citation than the slide text.

Chapter 7 ("Swarms & Multi-Agent Execution") documents how bd coordinates **many
agents working a single epic concurrently**. Key surface (OUTLINE §I–VII):

- **A swarm is a *molecule* bead, NOT a mutated epic** (OUTLINE §I, Discrepancy
  D2). `bd swarm create <epic-id>` creates a **new** bead with
  `issue_type=molecule`, `mol_type=swarm`, linked to the epic by a `relates-to`
  edge; the coordinator is stored as the molecule's `assignee`. The epic and its
  children are untouched. `molecule`/`swarm` are **internal** types (absent from
  `bd types`). Status is **never stored** on the molecule — it is computed live
  from the children.
- **Four swarm verbs** (OUTLINE §II): `create` (positional `[epic-id]`,
  `--coordinator`, `--force`, auto-wraps a non-epic), `list`
  (`{schema_version, swarms:[{id,epic_id,coordinator,total_issues,
  completed_issues,active_issues,progress_percent}]}`), `status` (computed
  Completed/Active/Ready/Blocked buckets; accepts epic *or* molecule id),
  `validate` (structural swarmability check).
- **Waves = bd's real parallel groups** (OUTLINE §III). `bd swarm validate`
  computes **ready fronts** from the DAG: `Wave 1`, `Wave 2`, … plus
  **estimated worker-sessions**, **max parallelism** (widest wave), **total
  waves** (DAG depth), and **Swarmable: YES/NO**. `parallel_group(s)` /
  `ParallelGroup` ARE real internal types in the bd binary — the structured
  wave model.
- **Claiming work** (OUTLINE §IV): no `bd swarm claim`; agents use
  `bd update <id> --claim` — an **atomic** assignee+`status=in_progress` flip
  that is the race-safety primitive letting N agents grab N distinct beads
  without collision. `swarm status` then shows the claimer on the Active row
  (`⟳ <id> [agent-fe]`).
- **Skills routing — the honest version** (OUTLINE §V, D3). `--skills <v>` is
  **folded into the description** as a `## Required Skills` section. There is
  **no `skills` JSON key**; bd does not route/filter/validate on it. "Routing"
  is an orchestrator convention reading that prose.
- **Execution metadata hints** (OUTLINE §VI, D4). `execution_parallel_group`,
  `execution_agent_type`, `execution_model`, `execution_effort`,
  `execution_mode` are stored as **free-form `metadata` keys**
  (`--set-metadata k=v`). bd **does not recognize them** (zero binary literals;
  an invented key stores identically). They are an orchestrator vocabulary,
  transparent to bd — and distinct from the real `parallel_group` wave model.
- **The audit interaction log** (OUTLINE §VII). `bd audit record`/`label` writes
  append-only `int-xxxx` entries to `.beads/interactions.jsonl` (`kind` =
  `llm_call`/`tool_call`/`label`; kind-specific `model/prompt/response` or
  `tool_name/exit_code`; `label` carries `parent_id` + reward signal). This is
  the cross-run "why did the agent do that" trail for SFT/RL — **explicitly
  distinct** from a single bead's event/audit history (chapter 1).

## 2. REFLECTED — what bdboard actually displays

**Headline: bdboard has ZERO swarm awareness.** A repo-wide search for
`swarm`, `mol_type`, `wave`, `coordinator`, `interactions`, `skills`,
`execution_*`, and `parallel_group` across `src/bdboard/**` returns **no
feature code** — only an unrelated comment in `store.py:96` ("not N parallel
ones") and the `molecule`-wrapper handling below. bdboard never calls
`bd swarm {create,list,status,validate}` and never reads
`.beads/interactions.jsonl`. Every swarm concept is either dropped, buried, or
silently reduced to its generic-bead representation. Itemized:

### 2.1 The swarm molecule itself is HIDDEN from the board

`_is_molecule()` (`lanes.py:101-113`) matches `issue_type == 'molecule'`, and
`lanes()` excludes it: `non_epics = [b for b in beads if not _is_epic(b) and
not _is_molecule(b)]` (`lanes.py:326`). The docstring's intent is to hide the
**formula-pour grouping wrapper** (redundant with the epic strip — chapter 5).
But the filter is **type-only**: it does **not** distinguish a formula-pour
wrapper from a **swarm molecule** (`mol_type=swarm`). So the swarm molecule —
the *only* object that carries the swarm's existence, coordinator/`assignee`,
and `bd swarm list` rollup — **never earns a card**. It is also not an epic, so
it is absent from `epic_lane()` (`lanes.py:206-291`). Net: a running swarm is
**invisible on the board**; the molecule is reachable only by typing its id into
the `/api/bead/<id>` modal URL, where it renders as a generic bead.

### 2.2 No swarm coordination state anywhere

Because bdboard never invokes the swarm verbs, **none** of the computed
coordination surface exists in the UI: no progress %, no Completed/Active/Ready/
Blocked rollup, no coordinator handle, no "Swarmable" check. Catalog
`docs/catalog/board-lanes.md` describes only the status-derived lanes; there is
no swarm catalog entry.

### 2.3 Waves / parallel groups are not surfaced

bdboard's lanes are **status-bucketed**, not DAG-ready-front computed
(`lanes.py:329-345`: closed/in_progress/blocked/open→ready|blocked/else). bd's
**wave** model (`swarm validate`: Wave 1/Wave 2, max parallelism, worker-
sessions) has **no representation**. The board cannot tell a user "these 2 beads
are wave 1, runnable now; this one is wave 2." `parallel_group` is never read.

### 2.4 `execution_*` hints render only as a raw JSON metadata blob

`metadata` IS in `_FIELD_ORDER` (`app.py:1345`), and `_ordered_fields`
(`app.py:1569-1589`) emits every non-hidden field. A dict-valued `metadata`
classifies as `json` (`_classify_field`, `app.py:1517-1527`) and renders via
`field_row.html:71` → `<pre class="field-json">{{ f.val | tojson(indent=2) }}`.
So `execution_agent_type`/`model`/`effort`/`mode`/`parallel_group` appear **only
as an unparsed JSON dump inside the metadata row** of the modal — never as
labeled, scannable hint rows, never on the card, never as a routing/grouping
affordance. (Verified shape: `bd show bdboard-6ljg --json` → `metadata: null`
here, but any bead with `--set-metadata execution_*` would dump verbatim.)

### 2.5 Skills are invisible as a concept (correctly, but worth stating)

Since `--skills` is description prose (`## Required Skills`) with **no `skills`
JSON key** (AVAILABLE §V), bdboard shows it only as part of the rendered
markdown `description` (`_KIND_MARKDOWN`, `app.py:1360`; `field_row.html:67`).
There is no `skills` field to surface and `_KIND_CHIPS` is `{labels, tags}`
only (`app.py:1353`), so even a hypothetical top-level `skills` list would fall
through to a raw `json` `<pre>` block, **not** friendly chips. bdboard does not
extract or badge the required-skills line.

### 2.6 The swarm audit interaction log is never read

The modal's "Audit trail" + "Lifecycle" views (`bead_audit.html`;
`history.py:status_timeline`; `app.py:_shape_audit`/`_diff_issue`) are built
**entirely from `bd history <id>`** (per-bead Dolt commit snapshots). They do
**not** read `.beads/interactions.jsonl`. So the swarm decision log
(`llm_call`/`tool_call`/`label` reward entries — the SFT/RL signal) is
completely absent. `_diff_issue` (`app.py:1610-1631`) gives detailed old→new
only for `{status, priority, assignee}`; a change to `metadata`/`skills`/
`parallel_group` collapses to a low-signal `"changed metadata"` line — so even
the per-bead audit conveys execution-hint churn as noise.

### 2.7 The "Activity" lane is a synthesized state-snapshot, not a concurrency feed

`activity()` (`lanes.py:353-381`, rendered `lanes.html:73-94`) is honest in its
own docstring: *"We don't have a real audit feed across all beads — bd doesn't
expose one — so we synthesize 'current state as event'."* It emits **one row
per bead** (latest timestamp + status-inferred verb + `assignee`/`created_by`
actor). It does convey *who* (per-actor rows), so concurrent agents appear as
distinct actors — but it is **not** grouped by swarm/wave/coordinator and does
not read the interaction log.

### 2.8 CRITICAL — N concurrent `in_progress` beads: render PASS, swarm-grouping FAIL

Per the area-3 confirmation (`03-status-lifecycle.md §2.2`, re-verified):
`lanes.py:333-334` appends **every** `in_progress` bead with **no cap**, sorts
by `(priority asc, updated_at desc)` (`lanes.py:347-348`), and
`lanes.html` loops the full list with no limit. Empirically the In-Progress lane
renders N>1 cleanly (injection test: 3 extra in_progress → lane size 4, no
truncation). The Activity lane likewise lists all of them with per-actor rows.
**So multi-WIP rendering itself is FINE and is NOT a gap.**

The residual **serial-only assumption** lives in `counts()`
(`lanes.py:390-399`): *"bdboard is a single-flight workflow tool — only one item
is in-progress at a time … in_progress is intentionally omitted."* The masthead
therefore drops the in_progress KPI entirely (it only re-appears via the
catch-all when count>0 — area 3 GAP 3 / `counts_skeleton.html`). For a swarm,
where many beads are concurrently in_progress **by design**, this framing is
backwards. Recorded as GAP 7 (cross-ref area 3 GAP 3 — don't double-file the
counts/skeleton fix).

**Beyond rendering, the gap is *legibility*:** four concurrent in_progress beads
from one swarm are visually **indistinguishable** from four unrelated ones.
There is no swarm/coordinator badge, no wave grouping, no parallel_group cluster
— the lane is a flat priority-sorted list. So bdboard renders multi-agent work
*correctly* but conveys multi-agent *coordination* not at all (GAPS 1–3, 8).

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | Swarm molecules (`issue_type=molecule`, `mol_type=swarm`) are hidden from the board by the type-only `_is_molecule` filter (`lanes.py:101-113,326`) — a running swarm and its coordinator handle are invisible; reachable only by direct modal URL. | P1 | File a bead: special-case `mol_type=swarm` so swarm molecules surface (own strip/badge) instead of being swept up with redundant formula-pour wrappers. |
| 2   | bdboard never calls `bd swarm {list,status,validate}`, so all computed coordination state (progress %, Completed/Active/Ready/Blocked rollup, coordinator, swarmable) is unsurfaced. | P2 | File a bead: add a swarm panel that shells `bd swarm status <id> --json` for the molecule modal / a swarm view. |
| 3   | Waves / ready-fronts (bd's real `parallel_group` model from `swarm validate`) have no representation; lanes are status-bucketed, not DAG-layer computed. | P2 | File a bead: surface `swarm validate` waves (Wave N, max parallelism) so concurrent-runnable beads are legible. |
| 4   | `execution_*` hints render only as a raw `<pre>` JSON dump inside the `metadata` row (`field_row.html:71`); never labeled hint rows, never on the card. | P3 | File a bead: parse known `execution_*` keys into labeled chips/rows in the modal (and optionally a card badge). |
| 5   | The swarm audit interaction log (`.beads/interactions.jsonl`: llm_call/tool_call/label reward entries) is never read — the cross-run "why did the agent do that" / SFT-RL trail is absent. | P2 | File a bead: add an interaction-log viewer (the audit panel only reads `bd history`, per-bead). |
| 6   | Required-skills prose (`## Required Skills` in description) is not extracted/badged; even a hypothetical `skills` list would render as raw JSON, not chips (`_KIND_CHIPS={labels,tags}`). | P3 | Minor: optionally pull the `## Required Skills` line into a skills chip; or accept description-only display as faithful (bd stores it as prose). |
| 7   | Serial-only framing baked into `counts()` (`lanes.py:390-399`, "single-flight … only one item in-progress") drops the in_progress masthead KPI — backwards for swarms where many beads are concurrently in_progress. | P2 | Cross-ref area 3 GAP 3: drop the single-flight framing; make in_progress a first-class fixed masthead cell. (Do not double-file.) |
| 8   | Concurrent in_progress beads render correctly but with no swarm/coordinator/wave/parallel_group grouping — N swarm beads are indistinguishable from N unrelated ones (`activity()` + lanes are flat). | P3 | File a bead: cluster/badge beads by swarm membership or `execution_parallel_group` so concurrent multi-agent work reads as coordinated. |
| 9   | `_diff_issue` (`app.py:1610-1631`) only details old→new for `{status,priority,assignee}`; changes to `metadata`/`skills`/`parallel_group` collapse to a low-signal "changed metadata" audit line. | P4 | Cosmetic: include execution-hint keys in the high-signal diff set so swarm metadata changes read meaningfully. |

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

- **Multi-WIP verdict (the CRITICAL ask):** PASS on *rendering* — the In-Progress
  and Activity lanes show N>1 concurrent in_progress beads with no cap or
  truncation (proven by injection in area 3 §2.2). The serial-only *assumption*
  survives only in `counts()`/`counts_skeleton.html` prose+layout (GAP 7,
  cross-ref area 3 GAP 3) — a framing/masthead bug, not a lane bug. The deeper
  swarm gap is **legibility**, not capacity: concurrency renders, coordination
  does not (GAPS 1–3, 5, 8).
- **Why GAP 1 is P1, not P0:** hiding the swarm molecule does not make a user act
  on the *wrong* bead (a P0 misrepresentation); it *silently omits* a real
  board-meaning object (the swarm handle). Textbook P1 ("silently absent"). The
  underlying child beads still render correctly in their lanes.
- **Faithful-by-design, not gaps:** `--skills`→description prose and `execution_*`
  being free-form/orchestrator-only mean bd itself does not treat them as
  structured/routable. bdboard showing them as description text + a metadata JSON
  blob is therefore *technically faithful to how bd stores them*; the gaps (4, 6)
  are about *improving legibility* of advisory hints, not correcting a
  misrepresentation.
- **Cross-section:** GAP 1 overlaps the formula/molecule display decision
  (chapter 5, `_is_molecule`) — the fix must split swarm molecules from
  formula-pour wrappers without un-hiding the latter. GAP 7 overlaps area 3
  GAP 3 (counts single-flight). Reference, don't duplicate.
