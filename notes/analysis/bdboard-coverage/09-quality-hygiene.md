# Quality & Hygiene — Coverage Findings

> Owner bead: bdboard-rohn. Field-guide chapter: `field-guide-09-quality-and-hygiene.html` (chapter 9).
> AVAILABLE sourced from the verified outline `../../../training/beads/volumes/field-guide-09-quality-and-hygiene/OUTLINE.md`
> (research bead `beads-cfy`, audited against bd v1.0.4 `ce242a879`).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `quality-hygiene`                              |
| Field-guide ref  | `field-guide-09-quality-and-hygiene.html` (chapter 9) |
| bdboard owner    | `bdboard-rohn`                                 |
| Primary sources  | `src/bdboard/bd.py`, `derive/lanes.py`; `templates/partials/counts.html`, `bead_audit.html`, `field_row.html`; `docs/catalog/board-counts.md`, `bead-audit.md` |
| Status           | `done`                                         |

---

## 1. AVAILABLE — what the field guide documents

Chapter 9 ("Quality & Hygiene Tooling") splits cleanliness into **two genuinely
different jobs** (OUTLINE § I): *graph hygiene* (is the bead graph healthy?) and
*contribution hygiene* (is my code PR ready?). bd exposes a fan of commands for
the first and exactly one for the second:

- **`bd lint`** (OUTLINE § II) — the **template contract**. Flags beads missing
  the required markdown sections **for their type**: `bug` → `## Steps to
  Reproduce` + `## Acceptance Criteria`; `task`/`feature` → `## Acceptance
  Criteria`; `epic` → `## Success Criteria`; `chore` → none. Default scope is
  open issues; **exits 1 on any warning, 0 when clean** (so it gates CI). The
  create-time sibling is `bd create --validate` / `validation.on-create`.
- **`bd dep cycles`** (OUTLINE § III) — focused circular-dependency detector
  (strongly-connected components). Clean → "No dependency cycles detected",
  exit 0. A cycle has **no topological order**, so every bead in it is
  permanently un-`ready` — one cycle silently freezes a whole component.
- **`bd graph check`** — superset integrity assertion: "cycles, orphans, and
  other integrity issues", exit 0/1. Here "orphans" = **structural** orphans:
  edges whose target bead doesn't exist, dangling refs, duplicate IDs.
- **Write-time cycle prevention** (OUTLINE § 3.4) — `bd dep add` refuses any
  edge that would close a loop ("Error: adding dependency would create a
  cycle"). So under normal use you essentially *cannot* hand-author a cycle;
  the checkers exist for bypass paths (`--no-cycle-check`, bulk `create
  --graph`/`import`, branch merges, direct SQL).
- **`bd orphans`** (OUTLINE § IV) — the *other* "orphan": issues **referenced
  in commit messages but still `open`/`in_progress`** (work committed but never
  `bd close`d). A git↔bd reconciliation, **not** a graph check. `--fix`
  auto-closes.
- **`bd duplicates`** / **`bd find-duplicates`** (OUTLINE § V) — exact
  content-hash dup groups vs fuzzy (mechanical Jaccard, default `--threshold
  0.5`, or `ai`) similarity.
- **`bd stale`** (OUTLINE § VI) — forgotten-work scanner: issues not updated in
  `--days` (default 30, min 1), `--status` filter, `--limit` 50.
- **`bd doctor`** / **`bd preflight`** (OUTLINE § VII) — the two "physicals".
  `doctor` = installation/DB integrity (and is **unsupported in embedded Dolt
  mode, the default** — needs `bd init --server`). `preflight` = a **beads-
  codebase contributor** PR checklist (`go test` / `golangci-lint` / `gofmt` /
  JSONL pollution / nix hash / version sync) — it runs **none** of the graph
  checks.
- **The recommended hygiene loop** (OUTLINE § VIII) — *there is no single bd
  command* that runs all graph checks; the pre-PR/handoff loop is a short
  hand-assembled script: `lint` → `graph check` → `orphans` → `stale` →
  `duplicates`/`find-duplicates`.

## 2. REFLECTED — what bdboard actually displays

**Headline: bdboard surfaces ZERO graph-hygiene signals.** It is a read-mostly
viewer, not a linter, and its entire `bd` command surface is limited to *read*
and *targeted-write* verbs — never a hygiene verb. Verified by enumerating every
`bd` invocation in `bd.py`:

| bdboard call | `bd.py` site | purpose |
| --- | --- | --- |
| `bd list --no-pager --limit 0` | `bd.py:274` | active snapshot |
| `bd list --status closed …` | `bd.py:308`, `:361` | closed lanes / History |
| `bd show <id> --long` | `bd.py:532` | bead detail |
| `bd history <id>` | `bd.py:549` | audit/lifecycle trail |
| `bd remember <body> --key` | `bd.py:603` | memory create |
| `bd formula list` / `bd mol pour` | `bd.py:641`, `:798` | formulas |
| `bd update <id> …` / `bd create` | `bd.py:848`, `:888` | inline edits |

**None of** `bd lint`, `bd dep cycles`, `bd graph check`, `bd orphans`,
`bd stale`, `bd duplicates`, `bd find-duplicates`, `bd doctor`, or `bd preflight`
is ever shelled out to. There is no template, route, badge, or derive helper
that renders a lint warning, a cycle, an orphan, a duplicate, or a stale flag.

Specific places a hygiene signal *could* live but doesn't:

- **lint / template completeness** — `field_row.html` and the bead modal render
  whatever description/acceptance/design fields exist and stay silent when they
  don't. A `bug` with **no `## Steps to Reproduce`** renders **identically** to
  a fully-templated one. There is no notion of "required section for this type"
  anywhere in the codebase.
- **dependency cycles — detected internally, then thrown away.** The *only*
  cycle-aware code in bdboard is `_topo_component_order` (`derive/lanes.py:164`),
  used to sequence the **epic strip**. It detects a cycle precisely
  (`if len(ordered_ids) != len(nodes):` `lanes.py:196`) but its only response is
  to `ordered_ids.extend(leftovers)` in stable-key order (`lanes.py:201`) so
  rendering stays deterministic. The cycle is **silently swallowed** — no badge,
  no warning, no log surfaced to the UI.
- **cycles in the lanes — invisible.** Lane blocked-ness uses
  `_has_unmet_blocking_dep` (`lanes.py:120-135`), a **one-hop** check: it never
  traverses for cycles. A cycle (A blocks B blocks A) puts **both** beads in the
  **Blocked** lane, indistinguishable from ordinary blocked work — yet neither
  can *ever* become Ready. The board shows "blocked", not "deadlocked".
- **structural orphan edges — masked as plain Blocked.** When a `blocks` target
  id isn't in the snapshot, `_has_unmet_blocking_dep` returns `True`
  ("unknown target — treat as unmet, conservative", `lanes.py:130-132`). So a
  bead blocked by a **non-existent / dangling** bead (the `graph check` orphan
  sense) renders as a normal Blocked bead — the broken edge is invisible.
- **commit-referenced orphans** — bdboard never reads git log (only `bd`
  subprocesses + the `.beads` file watcher), so it structurally **cannot**
  surface "committed but not closed" beads.
- **stale** — `field_row.html` shows `updated_at`/`created_at` (humanized
  timestamps), so staleness is *eyeballable*, but there is **no** age-threshold
  highlight, no "stale" badge, no sort-by-rot. `counts.html` tallies only
  open/blocked/deferred/closed (`docs/catalog/board-counts.md`).
- **duplicates / doctor / preflight** — entirely absent (and largely
  *appropriately* so — see GAP 6).

> **Naming false-friend:** bdboard's `bead_audit.html` / `/api/bead/{id}/audit`
> "**Audit trail**" is a `bd history` change-log view (`docs/catalog/bead-audit.md`),
> **not** a hygiene/lint audit. Don't mistake it for a quality surface — it
> reports *what changed*, never *what's wrong*.

### 2.1 AVAILABLE → REFLECTED coverage map

| bd hygiene surface | Reflected in bdboard? | Evidence |
| --- | --- | --- |
| `lint` (template contract) | **No** | no required-section concept anywhere |
| `dep cycles` | **No** (detected in `_topo_component_order`, discarded) | `lanes.py:196-201` |
| `graph check` (orphan edges) | **No** (dangling target → silent Blocked) | `lanes.py:130-132` |
| `orphans` (commit-referenced) | **No** (no git-log access) | `bd.py` command surface |
| `stale` | **No** (raw timestamps shown; no flag) | `field_row.html`, `counts.html` |
| `duplicates` / `find-duplicates` | **No** | absent |
| `doctor` | **No** (server-mode/env-only; correctly out of scope) | absent |
| `preflight` | **No** (codebase-contributor-only; correctly out of scope) | absent |

## 3. GAPS — what's misrepresented or unshown, and how much it matters

> **Framing (per the bead design note):** bdboard is a *viewer*, not a linter, so
> almost all of these are **enrichment opportunities (P2–P4), not viewer-SRP
> violations**. Surfacing a hygiene signal is read-only display of derived state
> — squarely in bdboard's lane. The two standouts (GAP 1, GAP 2) are stronger
> because bdboard *already has the data* and currently mis-frames or discards it.

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | A dependency **cycle** is detected in `_topo_component_order` (`lanes.py:196`) then **silently discarded** (`:201`); in the lanes a cyclic/permanently-deadlocked pair shows as ordinary **Blocked** (`_has_unmet_blocking_dep` is one-hop, `lanes.py:120-135`) — the board can't tell "blocked" from "blocked forever". | P2 | File a bead: keep the `_topo_component_order` cycle result and surface a "cycle"/"deadlocked" badge on affected beads (the detection is already free). |
| 2   | **No `bd lint` signal**: a bead missing its required template sections (a `bug` with no `## Steps to Reproduce`, a `task` with no `## Acceptance Criteria`) renders **identically** to a complete one — hiding the correctness problem from the board user best placed to fix it. | P2 | File a bead: derive per-type required-section completeness and show a "incomplete template" badge on the card/modal. |
| 3   | A **structural orphan edge** (a `blocks` target absent from the snapshot) is masked as a normal **Blocked** bead via the conservative `target is None → True` branch (`lanes.py:130-132`) — a broken/dangling dependency is invisible. | P2 | File a bead: distinguish "blocked by missing/unknown bead" from "blocked by open bead" with a distinct badge. |
| 4   | **No `stale` signal**: `updated_at` is shown but never age-flagged, so forgotten in-progress/open work is undistinguished from fresh work. | P3 | File a bead: add an optional age-threshold "stale" badge/sort (timestamps already rendered). |
| 5   | **No `orphans` (commit-referenced) signal**: committed-but-not-closed beads can't be surfaced because bdboard has no git-log data source. | P3 | File a bead (larger): add a git-log reconciliation feed; out of bdboard's current data reach. |
| 6   | **No `duplicates`/`find-duplicates` surfacing**: exact/fuzzy dup groups are not shown. | P4 | Optional: a low-priority "possible duplicate" hint; fuzzy matching is noisy (short-token quirk) and rarely a display concern. |
| 7   | _(disproven gap)_ **`doctor` / `preflight` absent** — `doctor` is server-mode/env-specific and unsupported in embedded mode (the default), and `preflight` is a beads-**codebase**-contributor checklist. Neither belongs on a general-purpose board. **Correctly absent.** | n/a | No action — record as deliberately out of scope. |

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

- **Why GAP 1 is P2, not P0/P1:** a cyclic bead is shown as **Blocked**, which
  is technically *true* (it is blocked) — so the displayed state isn't *wrong*
  (no P0). What's absent is the "this is blocked *permanently*" concept. That
  reads like P1 ("board-meaning concept absent"), but cycles are **rare by
  construction** (bd refuses them at `dep add` write-time; only bulk import /
  `--no-cycle-check` / branch-merge create them), so real-world impact is narrow
  → P2. The tie-breaker for prioritizing it anyway: **bdboard already computes
  the cycle** in `_topo_component_order` and throws it away — the surfacing cost
  is nearly zero.
- **GAP 2 (lint) is the chapter's headline tool** and the bead's named GAP
  example ("a bead failing `bd lint` looks identical to a healthy one"). It's P2
  not P1 because an incomplete-template bead still has a *correct* status/lane —
  nothing is *misrepresented*, a useful signal is merely *unsurfaced*. A
  half-templated bug is exactly the thing a board-watching human can fix on
  sight, which is what makes the enrichment valuable.
- **All hygiene gaps here are enrichment, not SRP violations.** A read-only
  badge derived from data bdboard already has (cycle, missing section, dangling
  edge, age) is display, not linting-as-a-service. The synthesis bead
  (`bdboard-bk1r`) should bucket area 9 as **Reflected? = None**, top gap **P2**,
  headline: *"bdboard surfaces no graph-hygiene signals; cycle detection is
  computed then discarded, and lint/orphan/stale never reach the UI."*
- **Cross-section:** GAP 3 (dangling-edge masking) and GAP 1 (cycles) both live
  in `derive/lanes.py` blocked-ness logic and overlap the dependency-graph audit
  (`bdboard-vhke`, area 2) — coordinate so the badge work isn't double-filed.
