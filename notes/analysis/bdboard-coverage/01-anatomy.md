# Anatomy of a Bead — Coverage Findings

> Owner bead: bdboard-cnzi. Field-guide chapter: `field-guide-01-anatomy-of-a-bead.html` (chapter 1).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `anatomy`                                       |
| Field-guide ref  | `field-guide-01-anatomy-of-a-bead.html` (chapter 1) |
| bdboard owner    | `bdboard-cnzi`                                       |
| Primary sources  | `src/bdboard/app.py` (field registry + ordering); `templates/partials/field_row.html`, `bead_modal.html`, `bead_card.html`, `bead_priority_badge.html`; `src/bdboard/bd.py` (`show_long`); `static/styles.css`; `docs/catalog/bead-modal.md`, `bead-inline-edit.md`, `bead-raw.md` |
| Status           | `done`                                  |

---

## 1. AVAILABLE — what the field guide documents

Chapter 1 ("Complete Anatomy of a Bead", audited against bd v1.0.4 `ce242a879`)
frames a bead as *one shape* shared across every type: the `type` field only
declares **intent**, while the field set and graph machinery are identical for
all of them. Sourced from the verified
`volumes/field-guide-01-anatomy-of-a-bead/OUTLINE.md` (the build bead consumes
this; the rendered HTML is a compressed React/`__bundler` payload, so the
outline is the stronger citation — same convention as the chapter-3 audit).

**Nine built-in types + an event pseudo-type (§III), each with a distinct glyph:**

| # | Type | Glyph | Lint requires |
| --- | --- | --- | --- |
| 1 | `task` | ● | Acceptance Criteria |
| 2 | `bug` | ▲ | Steps to Reproduce + Acceptance Criteria |
| 3 | `feature` | ■ | Acceptance Criteria |
| 4 | `chore` | ○ | *(none)* |
| 5 | `epic` | ◆ | Success Criteria |
| 6 | `decision` | ◇ | *(design field expected)* |
| 7 | `spike` | ↗ | *(none)* |
| 8 | `story` | ▸ | *(none)* |
| 9 | `milestone` | ◎ | *(none)* — a coordination bead |
| +1 | `event` (pseudo) | — | created via `--type=event` + 4 dedicated flags |

Plus **custom types** (`types.custom`) and **aliases** (`feat→feature`,
`adr→decision`). The glyphs are the guide's primary at-a-glance type signal.

**~35 fields (§IV), grouped by purpose:**

- **Identity** — `id`, `title`, `type`.
- **Core metadata** — `status` (7 statuses), `priority` (P0–P4), `assignee`,
  `labels` (some *magic*: `dim:val` state labels, `gt:slot`, `export:X`,
  `provides:X`, `template`), `due`, `defer`, `estimate` (**integer minutes**).
- **Content** — `description`, `acceptance`, `design` (ADR rationale),
  `notes` (append-only scratchpad), `context` (agent-injected).
- **Graph / structure** — `parent`, `deps`, `waits-for`, `waits-for-gate`,
  `external-ref`, `spec-id`.
- **Composition / execution** — `ephemeral` (wisp), `mol-type`
  (`work`/`swarm`/`patrol`), `wisp-type`, `skills`, `metadata` (JSON blob).
- **Event-only** — `event-actor`, `event-category`, `event-payload`,
  `event-target`.
- **System / behavioral flags** — `no-history`, `no-inherit-labels`, `repo`,
  `force`, `validate`, `silent`, etc. (creation-time switches, not stored body).
- **System-managed timestamps** — `created_at`, `updated_at`, `started_at`,
  `closed_at`, `close_reason` (read-only).

**Edge taxonomy (§V):** 12 edge types — covered in depth by area 2
(`02-dependency-graph.md`); this section only touches how the `deps`/
`dependencies` *fields* render in the bead.

## 2. REFLECTED — what bdboard actually displays

**The headline fidelity property: bdboard drops nothing.** The bead detail is
fetched with `bd show <id> --long --json` (`bd.py:518,532` — `show_long`), i.e.
the **full** field set, and `_ordered_fields()` (`app.py:1569-1588`) renders
**every** non-hidden key: known keys in a curated order (`_FIELD_ORDER`
`app.py:1314-1349`), then *"Anything not listed is appended alphabetically so we
never silently hide new bd fields"* (`app.py:1311-1312`). Only `_type` is hidden
(`_HIDDEN` `app.py:1351`). The modal grid loops these rows
(`bead_modal.html:30-34` → `field_row.html`), and a **raw JSON escape hatch**
(`/api/bead/{id}/raw`, `app.py:1258-1260`; `bead_modal.html:18`; catalog
`bead-raw.md`) dumps *every field bd knows about*. So at the **field-presence**
level, coverage is effectively total — a new bd field shows up automatically.

**Render-kind dispatch** lives in `_classify_field` (`app.py:1521-1531`) and is
rendered by `field_row.html` branching on `f.kind`:

- `chips` — `labels`/`tags` (`_KIND_CHIPS` `app.py:1357`) → chip list.
- `deps` — `deps`/`dependencies`/`dependents` (`_KIND_DEPS` `app.py:1358`) →
  dependency rows with `dep_label` (see area 2).
- `comments` — `comments` (`_KIND_COMMENTS` `app.py:1359`) → comment cards.
- `markdown` — **only** `description`, `notes`, `close_reason`,
  `acceptance_criteria` (`_KIND_MARKDOWN` `app.py:1361`) → rendered via `md`.
- `json` — dicts/lists (e.g. `metadata`) → `<pre>`.
- `scalar`/`empty` — everything else → bare text / `—`.

**Field keys render verbatim** as the row label: `field_row.html` `<dt
class="field-key">{{ f.key }}</dt>` — i.e. `acceptance_criteria`, `issue_type`,
`external_ref`, `created_at` show as raw snake_case, not humanized.

**Type (`issue_type`) is surfaced as plain text only:**

- **Card** — `bead_card.html:36` `<span class="bead-type">{{ b.issue_type }}</span>`,
  styled by a single `.bead-type` rule (`styles.css:800-806`: uppercase, grey).
  There are **no** `.type-task`/`.type-bug`/… classes and **no glyphs** anywhere.
- **Modal** — `issue_type` is a `_SHORT_META_FIELDS` scalar row
  (`app.py:1366-1389`) → plain text in the compact grid.
- **Edit** — inline-editable via a `<select>` whose options come from
  `_ISSUE_TYPE_OPTIONS = ("bug","feature","task","epic","chore","decision")`
  (`app.py:1444`) — **6 of the 9** built-in types.

**Priority** is the one field with rich visual treatment: a `P{n}` badge with
per-level color (`bead_priority_badge.html`; `bead_card.html:21-23`;
`.bead-priority.p0..p4` `styles.css:776-780`).

**Inline editing** (catalog `bead-inline-edit.md`) is registry-gated
(`_FIELD_REGISTRY` `app.py:1446-1476`): editable = `title`, `description`,
`acceptance_criteria`, `design`, `priority`, `assignee`, `issue_type`,
`external_ref`, `estimate`, `notes` (append-only). Everything else is read-only
by default (`_READONLY_SPEC` `app.py:1479`), and editing is locked entirely once
a bead is `in_progress`/closed (`_bead_is_editable` `app.py:1503-1511`).

### 2.1 Field-by-field coverage (AVAILABLE → REFLECTED)

| Field-guide field | bd emits? | bdboard treatment | faithful? |
| --- | --- | --- | --- |
| `id`, `title` | yes | ordered scalar rows; `id` also a card/modal anchor | YES |
| `type` | yes (`issue_type`) | plain text, **no glyph/color** (see GAP 1) | PARTIAL |
| `status` | yes | colored badge — but only open/in_progress/blocked/closed colored; deferred/pinned/hooked grey (see area 3) | PARTIAL (cross-ref area 3) |
| `priority` | yes | colored `P{n}` badge | YES |
| `assignee` | yes | scalar row + card chip | YES |
| `labels` | yes | chips — **magic labels not decoded** (see GAP 5) | PARTIAL |
| `due`, `defer` | when set | appended alphabetically as raw scalar rows | PARTIAL — shown but unlabeled/unordered |
| `estimate` | when set | scalar integer, **no unit** (guide says minutes) (GAP 6) | PARTIAL |
| `description` | yes | markdown-rendered | YES |
| `acceptance` (`acceptance_criteria`) | yes | markdown-rendered | YES |
| `design` | **yes (verified)** | **plain scalar, NOT markdown, sorts to bottom** (GAP 3) | NO |
| `notes` | yes | markdown, append-only edit | YES |
| `context` | when set | raw scalar row (appended) | PARTIAL |
| `parent`, `external_ref`, `spec_id` | when set | scalar rows (raw keys) | PARTIAL |
| `deps`/`dependencies`/`dependents` | yes | dep rows w/ `dep_label` (see area 2) | YES (detail → area 2) |
| `metadata` | when set | JSON `<pre>` | YES |
| `comments` | via count/list | comment cards | YES |
| composition (`mol_type`,`ephemeral`,`wisp_type`,`skills`) | when set | raw scalar rows (appended) | PARTIAL — shown but no semantics |
| event-only (`event_*`) | when set | raw scalar rows (appended) | PARTIAL (GAP 7) |
| timestamps (`created/updated/started/closed_at`, `close_reason`) | yes | scalar rows; `close_reason` markdown | YES |

Verified empirically: `bd show bdboard-cnzi --long --json` emits
`acceptance_criteria, assignee, comment_count, created_at, dependencies,
dependency_count, dependent_count, description, design, id, issue_type, labels,
parent, priority, started_at, status, title, updated_at`. Note `design` **is**
present yet falls to the alphabetical tail and renders unformatted.

### 2.2 Type-by-type visual treatment (all 10)

bd emits a `issue_type` string; bdboard renders it identically for every type —
uppercase grey text on the card, plain scalar in the modal. **No type carries a
glyph, icon, or per-type color**, so the field guide's primary type signal
(●▲■○◆◇↗▸◎) is entirely unreflected.

| Type | Guide glyph | Card render | Modal render | In edit dropdown? | Distinguishable? |
| --- | --- | --- | --- | --- | --- |
| `task` | ● | "TASK" text | `issue_type: task` | YES | text only |
| `bug` | ▲ | "BUG" text | scalar | YES | text only |
| `feature` | ■ | "FEATURE" text | scalar | YES | text only |
| `chore` | ○ | "CHORE" text | scalar | YES | text only |
| `epic` | ◆ | "EPIC" text* | scalar | YES | text only (*epics also pulled into the strip — area 3) |
| `decision` | ◇ | "DECISION" text | scalar | YES | text only |
| `spike` | ↗ | "SPIKE" text | scalar | **NO** | text only |
| `story` | ▸ | "STORY" text | scalar | **NO** | text only |
| `milestone` | ◎ | "MILESTONE" text | scalar | **NO** | text only |
| `event` (pseudo) | — | "EVENT" text | scalar + raw `event_*` rows | NO | text only |

Verdict: every type is rendered, none is *visually* differentiated, and the edit
dropdown can't even name `spike`/`story`/`milestone`/`event`.

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | No per-type visual treatment: all 9 types + `event` render as identical uppercase grey text (`bead_card.html:36`, `.bead-type` `styles.css:800-806`; modal scalar row) — the guide's glyph system (●▲■○◆◇↗▸◎) is wholly unreflected, so a `milestone`/coordination bead is indistinguishable from a `chore` at a glance. | P1 | File a bead: add a per-type glyph/badge (map `issue_type`→glyph+color) on the card and in the modal header. |
| 2   | `issue_type` inline-edit dropdown is lossy: `_ISSUE_TYPE_OPTIONS` (`app.py:1444`) lists only 6 of 9 built-in types — `spike`, `story`, `milestone` (and `event`, custom types) cannot be selected, so editing a spike/story/milestone silently can't preserve its type. | P2 | File a bead: source the enum from `bd types` (or add the 3 missing built-ins) so the dropdown is non-lossy. |
| 3   | `design` renders as unformatted plain text: it IS markdown-bearing (registry `editor="md"` `app.py:1451`) and IS emitted by `bd show --long` (verified), but it's absent from `_FIELD_ORDER` (sorts to the alphabetical tail) AND `_KIND_MARKDOWN` (`app.py:1361`), so ADR/design rationale loses all formatting and ordering. | P2 | File a bead: add `design` to `_FIELD_ORDER` (content group) and `_KIND_MARKDOWN`. |
| 4   | Field labels are raw bd keys: `field_row.html` `<dt>{{ f.key }}</dt>` shows `acceptance_criteria`/`issue_type`/`external_ref`/`created_at` verbatim (snake_case), inconsistent with the guide's field names and bdboard's friendly lane titles. | P3 | File a bead: add a key→humanized-label map for the modal `<dt>`. |
| 5   | Magic labels not decoded: bd's special labels (`dim:val` state, `gt:slot` gate slot, `provides:X`, `export:X`, `template`) render as undifferentiated chips (`_KIND_CHIPS`, `field_row.html` chips branch) — a gate-slot or state label looks like a freeform tag. | P2 | Cross-ref area 6 (gates); consider styling/decoding magic-label chips distinctly. |
| 6   | `estimate` shown unit-less: rendered as a bare integer scalar, but the guide defines it as **minutes** — "60" is ambiguous (minutes? hours? points?). | P3 | File a bead: append a "min" unit (or humanize to h/m) in the estimate row. |
| 7   | `event` pseudo-type and its `event_actor/category/payload/target` fields have no treatment: they'd appear as raw alphabetical scalar rows with snake_case keys; event beads (operational-state source of truth) are visually indistinguishable from any task. | P3 | File a bead: give `event` a glyph (folds into GAP 1) and order/label the `event_*` fields. |
| 8   | Composition/execution fields (`mol_type`, `ephemeral`, `wisp_type`, `skills`) surface only as raw scalar rows with no semantics — shown (good, not dropped) but a wisp/swarm/patrol bead reads like a plain bead. | P4 | Cross-ref areas 5/7; optional: badge mol_type/ephemeral. |

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

- **The big positive (don't lose it in the gaps):** field *presence* fidelity is
  excellent and deliberate — `_ordered_fields` appends unknown keys
  alphabetically (`app.py:1311-1312`) and the raw-JSON escape hatch
  (`app.py:1258`) guarantees nothing bd emits is ever truly hidden. The gaps are
  about *visual differentiation and per-field rendering polish*, not dropped data.
  So **Available = full; Reflected = Partial** (every field surfaced, but type
  treatment is flat and a few fields are under-rendered/mislabeled).
- **Why GAP 1 is P1, not P0:** a flattened type doesn't make a user act on the
  *wrong* bead's state (P0), but `type` is a core board-meaning concept rendered
  with zero visual signal — the textbook P1 ("a board-meaning concept silently
  absent"). Highest-value single fix in this area.
- **Cross-section dependencies:** edge/`deps` rendering depth → area 2; `status`
  badge coloring for deferred/pinned/hooked → area 3; magic/gate labels → area 6;
  `mol_type`/`ephemeral` semantics → areas 5/7. Don't double-file those here —
  GAPS 5 and 8 are recorded as cross-refs.
- **`bd show --long --json` omits unset fields**, so `due`/`defer`/`context`/
  `spec_id`/`external_ref`/event fields simply don't appear when empty (correct
  behavior). The PARTIAL verdicts above are about how they render *when set*.
