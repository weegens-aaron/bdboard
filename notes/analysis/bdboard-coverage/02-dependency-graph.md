# Dependency Graph — Coverage Findings

> Owner bead: bdboard-vhke. Field-guide chapter: `field-guide-02-dependency-graph.html` (chapter 2).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `dependency-graph`                              |
| Field-guide ref  | `field-guide-02-dependency-graph.html` (chapter 2) |
| bdboard owner    | `bdboard-vhke`                                  |
| Primary sources  | `src/bdboard/app.py` (`_dep_label` filter); `src/bdboard/derive/lanes.py` (`get_dependency_type`, `_has_unmet_blocking_dep`, `epic_lane`, `lanes`); `templates/partials/field_row.html` (deps block), `bead_modal.html`; cross-ref bug `bdboard-fjk` + memory `dep-edge-direction` |
| Status           | `done`                                          |

---

## 1. AVAILABLE — what the field guide documents

Chapter 2 ("Dependency Graph & the Edge Taxonomy", audited against bd v1.0.4
`ce242a879`) is sourced from the verified
`volumes/field-guide-02-dependency-graph/OUTLINE.md` (the rendered HTML is a
compressed React bundle, so the outline is the stronger citation — same
convention as areas 1 and 3).

**Twelve edge types in three categories (§I, §II):**

| # | Edge type | Direction | Category | Gates `bd ready`? |
| --- | --- | --- | --- | --- |
| 1 | `blocks` | A → B (B depends on A) | **blocking** | **YES** |
| 2 | `waits-for` | A → {B1..Bn} | **blocking** (fanout gate) | **YES** |
| 3 | `parent-child` | P → C | structural | no |
| 4 | `related` | A ↔ B | informational | no |
| 5 | `relates-to` | A ↔ B | informational | no |
| 6 | `tracks` | A → B | informational | no |
| 7 | `discovered-from` | A → B | informational | no |
| 8 | `caused-by` | A → B | informational | no |
| 9 | `validates` | A → B | informational | no |
| 10 | `until` | A → B | informational | **no** (corrected from Vol I) |
| 11 | `supersedes` | A → B | informational | no |
| 12 | `external:<proj>:<cap>` | A → ext | cross-project | resolved at query time |

- **The bright line (§II):** *only `blocks` and `waits-for` gate work.* All
  other 10 types are advisory — they carry meaning for humans/tools but do
  **not** prevent a bead from appearing in `bd ready`. Verified empirically in
  the field guide (Appendix B.1): 11 downstream beads, one per type, wired to
  one open upstream — only `blocks` and `waits-for` showed in `bd blocked`.
- **`until` is NOT blocking (§2.3):** an explicit empirical correction to Vol I,
  which had mis-classified it. `bd ready --explain` reports "no blocking
  dependencies" for an `until`-linked bead.
- **`waits-for` IS blocking (§2.4):** stores a *distinct* `dependency_type:
  "waits-for"` (not `"blocks"`), with gate modes `all-children` (default) /
  `any-children`, but gates readiness identically to `blocks`.
- **Direction / perspective (§I, §III):** `bd dep add B A` means "B depends on
  A" (edge A → B). bd reports the literal `dependency_type` (e.g. `blocks`)
  **identically on both ends** of the edge — it is the edge type, not a
  perspective-relative label. The human-meaningful relationship ("blocked by"
  vs "blocks") must therefore be derived from **type + which side you're
  viewing from** (inbound `dependencies` vs outbound `dependents`).
- **Readiness is computed, not stored (§III):** layers via topological sort of
  the **blocking subgraph only**; Layer 0 = ready, Layer 1+ = blocked. Non-
  blocking edges are ignored by the layer computation. The graph-derived
  blocking is authoritative even when the stored `status` field is stale (§3.5).
- **Five render formats (§IX):** default layered ASCII DAG, `--compact` tree,
  `--box`, `--dot` (Graphviz), and `--html` (interactive D3 with pan/zoom). All
  render the *same* topology.
- **Integrity (§VII, §VIII):** blocking edges cannot cycle (unconditional pre-
  add guard); non-blocking edges may cycle harmlessly; `bd dep cycles` /
  `bd graph check` inspect the blocking subgraph only.

## 2. REFLECTED — what bdboard actually displays

bdboard surfaces dependencies in **two distinct places**, with two **separate**
type-handling code paths that do not agree on the edge taxonomy:

### 2.1 Modal dep rows — the relationship label (the `bdboard-fjk` path)

The bead modal renders `dependencies` / `dependents` / `deps` lists as `deps`-
kind rows (`_KIND_DEPS` `app.py:1357`; classified `app.py:1522`). Each row's
relationship label comes from the `dep_label` Jinja filter:

- `field_row.html:49` — `{{ (d.dependency_type or d.type or d.rel) | dep_label(f.key) }}`
  passes the stored edge type **and** the field key (`dependencies` =
  inbound / `dependents` = outbound) as the direction.
- `_dep_label(dep_type, direction)` (`app.py:51-92`, registered
  `app.py:98`) maps each type to an `(inbound_label, outbound_label)` pair:

  | stored type | inbound (`dependencies`) | outbound (`dependents`) |
  | --- | --- | --- |
  | `blocks` | "blocked by" | "blocks" |
  | `related` / `relates-to` | "related" | "related" |
  | `parent-child` | "child of" | "parent of" |
  | `discovered-from` | "discovered from" | "discovered" |
  | `validates` | "validated by" | "validates" |
  | `caused-by` | "caused by" | "causes" |
  | `tracks` | "tracked by" | "tracks" |
  | `supersedes` | "superseded by" | "supersedes" |
  | `until` | "until" | "until" |
  | *(anything else)* | raw type | raw type |

**This is the resolved state of `bdboard-fjk` (CLOSED, judges passed).** The
prior regression hard-coded "blocked by"/"blocks" by which list was rendered,
discarding the type; the current filter derives the label from **type AND
direction** in one place — exactly the contract the `dep-edge-direction` memory
demands ("the displayed label must depend on direction AND type"). **Direction
correctness in the modal is therefore GOOD** — there is no reversal or
ambiguity for the 10 mapped types.

**Caveat:** the filter's `label_map` covers **10** of the 12 edge types. It has
**no entry for `waits-for` or `external`**, so those fall through to the raw-
type fallback (`waits-for` shows literally as "waits-for", `external` as
"external"). Acceptable (not *wrong*), but un-humanized.

### 2.2 Lane derivation — what counts as "blocked" (the readiness path)

bdboard recomputes readiness for the swim lanes rather than reading `bd ready`:

- `get_dependency_type(dep)` (`lanes.py:71-77`) normalizes `type` / `dependency_type`.
- `_has_unmet_blocking_dep(bead, by_id)` (`lanes.py:120-138`) walks the bead's
  deps and treats an edge as a blocker **only if** its type is in
  `("blocks", "blocked-by", "blocked_by")` (`lanes.py:126`) AND the target is
  not closed. Unknown target → conservatively treated as blocked.
- `lanes()` (`lanes.py:314-345`): a bead with `status == "open"` goes to the
  **blocked** lane iff `_has_unmet_blocking_dep` is true, else to **ready**
  (`lanes.py:339-342`); an explicit `status == "blocked"` always goes to the
  blocked lane (`lanes.py:336-337`). So bdboard **unions** stored-status-blocked
  with graph-derived-blocked — good fidelity to §3.5 (it does not blindly trust
  the stale status field for open beads).
- The epic strip (`epic_lane`, `lanes.py:235-247`) wires predecessor → successor
  ordering using the **same** `blocks`-only filter, producing a left-to-right
  topological sequence of epics (a partial, epic-scoped topo render).

**The fidelity defect:** `_has_unmet_blocking_dep` gates on `blocks` variants
**only — it never checks `waits-for`** (confirmed: no `waits-for` token exists
anywhere in `src/bdboard`). Per the field guide §2.4, `waits-for` is one of the
**two** blocking edge types. A bead gated *solely* by an unmet `waits-for`
fanout edge will be computed `ready` by bdboard and rendered in the **READY
lane** — the textbook P0 "blocked shown as Ready."

### 2.3 What is correctly NON-blocking

Because `_has_unmet_blocking_dep` only counts `blocks` edges, **all 10 advisory/
structural types are correctly NOT treated as blockers** by the lane logic —
including `until`, matching the field guide's empirical correction (§2.3). A
bead linked to an open upstream via `related`, `tracks`, `parent-child`,
`discovered-from`, `caused-by`, `validates`, `supersedes`, `relates-to`, or
`until` correctly stays in the READY lane. This is a genuine positive: bdboard
does not conflate advisory edges with blockers.

### 2.4 What is NOT reflected at all

- **No DAG / graph visualization.** bdboard has swim lanes + a 1-D epic strip
  and nothing else — none of the field guide's five render formats (§IX),
  especially the interactive D3 `--html` view, have an equivalent. There is no
  `waits-for`, `graph`, `dag`, or `DAG` symbol anywhere in `src/bdboard`. Layer
  depth, parallelism width, fanout gates, and cross-component structure are all
  invisible. The epic strip is the closest thing (an epic-only topo line).
- **No edge-type filter or per-edge styling.** Modal dep rows render every edge
  type with identical markup (`.dep-rel` span, `field_row.html:47-50`); a hard
  `blocked by` and a soft `related` look the same apart from the label text.
- **Cross-project `external` edges** get no special treatment (and bd itself
  hides them without `external_projects` config, so they rarely appear).

### 2.5 Edge-type-by-edge-type coverage (AVAILABLE → REFLECTED)

| Edge type | Modal label (`_dep_label`) | Lane gating (`_has_unmet_blocking_dep`) | Faithful? |
| --- | --- | --- | --- |
| `blocks` | "blocked by" / "blocks" | **gates**  | YES |
| `waits-for` | raw "waits-for" (no map entry) | **NOT gated** (should gate) | **NO — P0 (gating) + P3 (label)** |
| `parent-child` | "child of" / "parent of" | non-gating  | YES |
| `related` | "related" | non-gating  | YES |
| `relates-to` | "related" | non-gating  | YES |
| `tracks` | "tracked by" / "tracks" | non-gating  | YES |
| `discovered-from` | "discovered from" / "discovered" | non-gating  | YES |
| `caused-by` | "caused by" / "causes" | non-gating  | YES |
| `validates` | "validated by" / "validates" | non-gating  | YES |
| `until` | "until" | non-gating  (matches §2.3) | YES |
| `supersedes` | "superseded by" / "supersedes" | non-gating  | YES |
| `external` | raw "external" (no map entry) | not gated (bd hides anyway) | PARTIAL (P4) |

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | `waits-for` is not treated as a blocking edge in lane derivation: `_has_unmet_blocking_dep` (`lanes.py:126`) gates only on `blocks`/`blocked-by`, so a bead gated solely by an unmet `waits-for` fanout edge is computed `ready` and rendered in the READY lane — a false-ready (blocked shown as Ready). `waits-for` is one of the two blocking types per field guide §2.4. | **P0** | File a bead: add `"waits-for"` to the blocking set in `_has_unmet_blocking_dep` (and the `epic_lane` wiring at `lanes.py:236`); add a fixture test with a `waits-for`-gated bead. |
| 2   | No DAG / graph visualization: bdboard renders lanes + a 1-D epic strip only — none of the field guide's five render formats (§IX), esp. the interactive D3 `--html` view, are reflected, so layer depth, parallelism, and fanout structure are invisible. | P2 | File a bead: add a graph/DAG view (e.g. embed `bd graph --html` D3 or render the blocking subgraph) for at-a-glance topology. |
| 3   | `waits-for` has no `_dep_label` map entry (`app.py:66-75`), so the modal shows the raw token "waits-for" instead of a human label ("waiting on" / "awaited by"). | P3 | File a bead: add `"waits-for": ("waiting on", "awaited by")` to the `label_map`. |
| 4   | Modal dep rows give no visual weight to blocking vs advisory edges: a `blocked by` and a `related` render with identical `.dep-rel` styling, so a hard blocker isn't visually distinguished from a soft cross-reference. | P3 | File a bead: style blocking-edge labels (`blocks`/`waits-for`) distinctly from advisory ones in `field_row.html` / `styles.css`. |
| 5   | `external:<proj>:<cap>` cross-project edges have no label map entry or special treatment (render raw "external"); narrow impact since bd hides them without `external_projects` config. | P4 | File a bead (low): add an `external` label + cross-project styling once external deps are in play. |

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

- **Edge-direction correctness is GOOD — explicitly assessed.** This was the
  area's headline P0 risk (a reversed edge makes a user act on the wrong
  prerequisite). After the `bdboard-fjk` fix (CLOSED, judges passed), the modal
  `_dep_label` filter (`app.py:51-92`) derives the relationship label from
  **type AND direction** in a single place, satisfying the `dep-edge-direction`
  memory ("bd reports `dependency_type: blocks` identically on BOTH sides — the
  displayed label must depend on direction AND type"). There is **no current
  reversal or ambiguity** for the 10 mapped types, so **no P0 is assigned to
  direction**. The only `waits-for`/`external` shortfall in the modal is a
  *raw-type-instead-of-humanized-label* issue (P3/P4), not a reversal.
- **The surviving P0 is a gating gap, not a direction gap (GAP 1).** bdboard's
  two dependency code paths disagree on the taxonomy: the **modal label** path
  knows 10 types; the **lane gating** path knows only `blocks`. The field guide
  recognizes **two** blocking types — `blocks` *and* `waits-for` — and bdboard
  silently drops `waits-for` from readiness, producing a false-ready. This is
  the highest-stakes finding in the area.
- **`until` handled correctly by luck-of-design.** Because the gating set is an
  allow-list of `blocks` variants (not a deny-list), `until` is correctly
  non-blocking, matching the field guide's empirical Vol I correction (§2.3) —
  a positive worth preserving (don't "fix" it into a blocker).
- **The absence of a true DAG view is a real but P2 gap (GAP 2):** lanes still
  convey readiness, so it doesn't *misrepresent* state; it just under-shows the
  structure the field guide spends five render formats on. The epic strip is a
  partial, epic-only topological render.
- **Cross-section dependencies:** the `blocked` lane / blocked-badge mechanics
  also touch area 3 (status-lifecycle); `waits-for` as the gate primitive is
  owned in depth by area 6 (gates & coordination) — GAP 1's fix should
  coordinate with area 6 so a `waits-for`/gate bead is both *gated* (area 2) and
  *visually marked as a gate* (area 6).
```