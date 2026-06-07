# Status Lifecycle — Coverage Findings

> Owner bead: bdboard-2w9b. Field-guide chapter: `field-guide-03-status-lifecycle.html` (chapter 3).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `status-lifecycle`                                       |
| Field-guide ref  | `field-guide-03-status-lifecycle.html` (chapter 3)                          |
| bdboard owner    | `bdboard-2w9b`                                       |
| Primary sources  | `src/bdboard/derive/lanes.py`; `templates/partials/lanes.html`, `counts.html`, `counts_skeleton.html`, `closed_lane.html`; `docs/catalog/board-lanes.md`; `docs/design/bdboard-o9v.6/status-transition-affordance-design.md` |
| Status           | `done`                                  |

---

## 1. AVAILABLE — what the field guide documents

bd 1.0.4 exposes **seven** lifecycle statuses. bd enforces them with an explicit
allow-list — `bd list --status=foo` rejects unknown values with *"valid: open,
in_progress, blocked, deferred, closed, pinned, hooked"* (verified against the
installed `bd` and recorded in `docs/design/bdboard-o9v.6/…§2`). Chapter 3
("Status, Lifecycle & Operational State") frames these as an **operational state
machine**, not free-form scalars:

- **`open`** — the not-started resting / backlog state.
- **`in_progress`** — active work; set atomically by `bd update --claim` (also
  sets assignee). bd places **no single-WIP cap** — any number of beads may be
  `in_progress` at once (swarms, multiple agents/humans).
- **`blocked`** — explicit "waiting on a dependency" status. bd *also* derives
  blocked-ness from unmet `blocks`/`blocked-by` dep edges (chapter 2), so
  "blocked" is both a stored status **and** a derived condition.
- **`deferred`** — *intentionally parked* (a choice), distinct from `blocked`
  (a dependency wait). `--defer <date>` hides the bead from `bd ready` until then.
- **`closed`** — terminal/done; `bd close` carries a reason (and `--session`).
- **`pinned`** — operational-state axis: infra / never-auto-close. Pinned beads
  resist auto-close (need `bd close --force`). **Not** a normal work state.
- **`hooked`** — bd-internal molecule/formula machinery lifecycle. **Not** a
  human-facing manual target.

Idiomatic transitions (chapter 3 §"lifecycle"): `open → in_progress` (claim) →
`closed` (done); side-trips to `blocked`/`deferred` and back; `closed → open|
in_progress` is a *reopen*. `pinned`/`hooked` are operational-axis states bd
manages, orthogonal to the open→closed work axis.

> Note: chapter 3's rendered prose ships as a compressed React/`__bundler`
> payload (not extractable as plain text), so the status enum above is sourced
> from bd's own runtime allow-list and the o9v.6 design doc, which verified it
> empirically against the same `bd` binary — a stronger citation than the slide
> text.

## 2. REFLECTED — what bdboard actually displays

bdboard is a **read-only mirror**: it *derives five lanes* from `bd list`
snapshots and never mutates status. Lane assignment lives in
`derive/lanes.py:lanes()` (`lanes.py:325-348`):

- **Closed lane** — `status in {closed, resolved, done}` (`lanes.py:31`,
  `lanes.py:329-331`). Date-bounded at fetch (`BOARD_CLOSED_WINDOW_DAYS`).
- **In-Progress lane** — `status == 'in_progress'` (`lanes.py:333-334`).
  `buckets["in_progress"].append(b)` — **no cap**, every match is appended.
- **Blocked lane** — `status == 'blocked'` **OR** (`status == 'open'` AND an
  unmet `blocks`/`blocked-by` dep) (`lanes.py:335-340`, `_has_unmet_blocking_dep`
  `lanes.py:120-135`). So bdboard reproduces bd's *derived* blocked-ness, not
  just the stored status.
- **Ready lane** — `status == 'open'` with no unmet blocking dep (`lanes.py:338-340`).
- **Deferred lane** — the `else` **catch-all** (`lanes.py:341-342`): "everything
  else open-ish."

Rendered by `templates/partials/lanes.html:35` (loops the fixed key list
`["deferred","blocked","ready","in_progress"]`) + lazy `closed_lane.html`. Each
lane card uses `bead_card.html`; epics are pulled out into the strip
(`epic_lane()`), so the `in_progress` **count seen in the lane can differ from
the masthead count** by the number of in_progress epics (live example below).
Catalog: `docs/catalog/board-lanes.md`.

**Masthead counts** — `derive/lanes.py:counts()` (`lanes.py:382-410`) →
`templates/partials/counts.html`. Fixed cell order `["open","blocked","deferred",
"closed"]`, then a catch-all appends *any other status with count>0*
(`lanes.py:405-407`). The cell **label is the raw status key** (`counts.html`:
`{{ status }}`), e.g. `in_progress`/`pinned`, not a humanized label.

**Status-transition affordances** — **none shipped.** The status row in the bead
modal is a plain read-only scalar. A full verb-labelled transition affordance
(claim / block / defer / close / reopen, with a guard table and close-policy)
was *designed* in `docs/design/bdboard-o9v.6/status-transition-affordance-design.md`
but that doc explicitly ships **no code**. So bdboard reflects bd's lifecycle
*state* but exposes **zero lifecycle actions** — consistent with its read-mostly
mission, but worth recording.

### 2.1 Full 7-status → lane mapping (verified)

Verified empirically by running `derive.lanes.lanes()` over the live snapshot
(17 beads) plus injected `pinned`/`hooked`/multi-`in_progress` fixtures.

| bd status | bdboard lane | rule (`lanes.py`) | faithful? |
| --- | --- | --- | --- |
| `open` (no unmet dep) | **Ready** | `:338-340` | YES |
| `open` (unmet blocking dep) | **Blocked** (derived) | `:335-340` | YES — idiomatic, mirrors bd's derived blocked-ness |
| `in_progress` | **In-Progress** | `:333-334` (append, no cap) | YES |
| `blocked` | **Blocked** | `:335-336` | YES |
| `deferred` | **Deferred** (via `else`) | `:341-342` | YES — but by accident of the catch-all, not an explicit branch |
| `closed`/`resolved`/`done` | **Closed** | `:329-331` | YES |
| `pinned` | **Deferred** (via `else`) | `:341-342` | NO — **misrepresented**, see GAP 1 |
| `hooked` | **Deferred** (via `else`) | `:341-342` | NO — **misrepresented**, see GAP 2 |

> Empirical proof (GAP 1/2): injecting one `pinned` + one `hooked` bead, both
> land in the **Deferred** lane (`fakes in deferred?: ['FAKE-pin','FAKE-hook']`).
> `counts()` *does* surface them as extra masthead cells (`'pinned':1,'hooked':1`)
> via the catch-all — so the masthead shows a pinned/hooked count with **no
> matching lane**, and the bead itself sits silently in Deferred.

### 2.2 CRITICAL — multiple simultaneous `in_progress` beads render correctly

**Confirmed: the In-Progress lane is general-purpose multi-WIP, not single-WIP.**
`lanes.py:333-334` appends *every* `in_progress` bead with no cap, sorts by
`(priority asc, updated_at desc)` (`:346-347`), and `lanes.html:35-46` loops the
full list with no `[:1]`/limit. Empirically:

- Live snapshot has **2** `in_progress` beads: `bdboard-2w9b` (task) and
  `bdboard-gnhi` (epic). The lane shows 1 because the **epic lives in the strip**
  (`lanes()` excludes epics) — the masthead count of 2 is the honest total. This
  count-vs-lane delta is correct behaviour, not a bug.
- Injecting **3** extra non-epic `in_progress` beads → In-Progress lane size **4**
  (`['WIP-0','bdboard-2w9b','WIP-1','WIP-2']`), priority-sorted. No truncation.

So multi-WIP rendering itself is **fine** and is **not** flagged as a gap. The
*only* single-WIP residue is in framing/skeleton — see GAP 3.

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | `pinned` has no lane branch → falls through `else` and is shown as **Deferred** (`lanes.py:341-342`), conflating never-auto-close infra with intentionally-parked work; masthead shows a `pinned` count with no matching lane. | P1 | File a bead: add an explicit `pinned` branch (own lane or a distinct card badge) so infra beads aren't read as deferred. |
| 2   | `hooked` has no lane branch → same `else` → shown as **Deferred** (`lanes.py:341-342`); formula/molecule machinery state is indistinguishable from parked work. | P1 | File a bead: handle `hooked` explicitly (badge or hide like `molecule` wrappers) rather than dumping it in Deferred. |
| 3   | Baked-in **single-WIP assumption** in `counts()` docstring (`lanes.py:392-399`) and `counts_skeleton.html:9-10` ("bdboard is a single-flight workflow tool — only one item is in-progress at a time"); the skeleton omits the `in_progress` cell while real `counts()` re-adds it when >0 → masthead grows a 5th cell on hydration (layout jitter) and the framing contradicts bdboard's general-purpose multi-WIP mission. | P2 | File a bead: drop the single-flight framing; make `in_progress` a first-class fixed masthead cell matching the skeleton. |
| 4   | No shipped status-**transition** affordance — bd's lifecycle verbs (claim/block/defer/close/reopen) are designed (`bdboard-o9v.6`) but not built; status is read-only in the modal. | P3 | Optional: ship the o9v.6 follow-up beads if interactive transitions are wanted (read-only is a legitimate stance). |
| 5   | Blocked lane conflates stored `status==blocked` with derived `open + unmet-dep` (`lanes.py:335-340`) — no visual distinction between the two. Idiomatic (mirrors bd's own derived blocked-ness) but a user can't tell "soft-blocked status" from "dependency-blocked". | P4 | Optional: add a sub-badge distinguishing status-blocked vs dep-blocked. |
| 6   | `counts.html` renders the **raw status key** as the cell label (`{{ status }}` → `in_progress`, `pinned`) instead of a humanized label, inconsistent with the friendly lane titles in `lanes.html`. | P4 | Cosmetic: map status keys through `_STATUS_META` labels in the counts cell. |

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

- **Why pinned/hooked default to P1, not P0:** they don't make a user act on the
  *wrong* bead (a P0 misrepresentation), but they *silently mislabel a distinct
  operational concept* (a status with no real lane) — the textbook P1 case in the
  rubric. If `pinned`/`hooked` are vanishingly rare in practice the impact is
  narrow, but the catch-all is a latent fidelity hole the moment they appear.
- **Multi-WIP verdict (the CRITICAL ask):** PASS — the In-Progress lane renders
  N>1 cleanly with no cap (proven by injection). Multi-WIP itself is *not* a gap.
  The single-WIP *assumption* survives only in `counts()`/`counts_skeleton.html`
  prose+layout, captured as GAP 3 — a framing/skeleton bug, not a lane bug.
- Cross-section: GAP 4 (no transition affordance) overlaps with the
  manual-editing epic (`bdboard-o9v`); don't double-file — reference o9v.6.
