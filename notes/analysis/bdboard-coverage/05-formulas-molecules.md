# Formulas & Molecules — Coverage Findings

> Owner bead: bdboard-whjh. Field-guide chapter: `field-guide-05-formulas-and-molecules.html` (chapter 5).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `formulas-molecules`                           |
| Field-guide ref  | `field-guide-05-formulas-and-molecules.html` (chapter 5) |
| bdboard owner    | `bdboard-whjh`                                 |
| Primary sources  | `templates/partials/formula_list.html`, `formula_form.html`, `formula_pour_result.html`; `src/bdboard/app.py` (`api_formulas`, `api_formula_form`, `api_formula_pour`, `_pour_counts`, `_short_pour_id`); `src/bdboard/bd.py` (`list_formulas`, `read_formula_detail`, `read_formula_variables`, `pour_formula`, `rename_bead`); `src/bdboard/derive/lanes.py` (`_is_molecule`, `lanes`); `docs/catalog/pour-formula.md`; `docs/decisions/0007-formula-pour-ui-write-surface.md`; `docs/design/bdboard-ain.2/grouping-node-display-decision.md` |
| Status           | `done`                                         |

---

## 1. AVAILABLE — what the field guide documents

Chapter 5's rendered prose ships as the same ~2.9 MB compressed React/`__bundler`
base64 payload as chapters 3 & 4 (verified: `head -c` shows the
`#__bundler_thumbnail` splash and the title is even mislabelled "Anatomy of a
Bead" — the prose is **not** extractable from the HTML). Per the methodology
note recorded for `03`/`04`, the surface below is therefore sourced from the
**installed `bd` binary's own `--help`** (`bd mol --help`, `bd mol pour --help`,
`bd mol wisp --help`, `bd swarm --help`) and `bd formula list --json` — a
stronger citation than un-renderable slide text.

**The molecule metaphor (verbatim from `bd mol --help`):**

- A **proto** is an uninstantiated template (reusable work pattern) — an epic
  carrying the `template` label that defines a **DAG** of work.
- A **formula** is the on-disk proto template (`.beads/formulas/*.formula.json`).
  `bd formula list --json` returns `name`, `type` (e.g. `"workflow"`),
  `description`, `source` (absolute path), `steps` (count), `vars` (count).
- **Spawning** a proto creates a **molecule** (real issues). Variables
  (`{{key}}`) are substituted at spawn time (`--var key=value`).
- **Bonding** combines protos/molecules into compounds; **distilling** extracts
  a proto from an ad-hoc epic; **squash/burn** condense/discard.

**Phase (the work/wisp axis — verbatim from `bd mol pour|wisp --help`):**

| Phase  | Verb           | Storage                                              | Use |
| ------ | -------------- | --------------------------------------------------- | --- |
| solid  | (proto)        | the `*.formula.json` template                        | reusable pattern |
| liquid | `bd mol pour`  | **persistent** in `.beads/`, **synced via git**      | "work" — features, reviews, anything with audit value |
| vapor  | `bd mol wisp`  | **ephemeral** (`Ephemeral=true`), local-only, **NOT git-synced**, auto-`gc` | release loops, health checks, recurring ops — no audit value |

- A formula can declare `phase:"vapor"` to **recommend** wisp usage. *"If you
  pour a vapor-phase formula, you'll get a warning"* (verbatim) — but it still
  pours (warning on stderr, **exit 0**).
- `bd mol pour … --json` **cooks inline** (no separate `bd cook`), mutates the
  workspace, and is **atomic** (a failed pour rolls back to zero new beads). The
  result JSON carries `new_epic_id` (the `molecule`-typed wrapper that parents
  the whole tree), `id_mapping` (stepId → real bead id), and `created` (raw node
  count).

**The mol-type taxonomy (work / patrol / swarm / wisp) — what each really is:**

- **work** = a persistent (liquid) molecule poured from a workflow formula. This
  is the default and the only kind bdboard creates.
- **wisp** = the vapor/ephemeral molecule above. A distinct lifecycle (auto-gc,
  not git-synced), not just a label.
- **patrol** = a recurring **operational** molecule (the `bd mol show`
  `--parallel` help uses `bd-patrol` as its canonical example) — typically run
  as a wisp/vapor loop (health checks, recurring cycles).
- **swarm** = a **structured-epic parallel-coordination** molecule with its own
  top-level command group (`bd swarm create|list|status|validate`). Swarms are
  the subject of **chapter 7 / `07-swarms.md`** — cross-referenced here, **not**
  re-audited, to avoid double-counting.

So "mol-type" is really two orthogonal things: a **phase** (liquid vs vapor) and
a **kind/intent** (work vs patrol vs swarm). bd encodes phase structurally
(`Ephemeral`), but work/patrol are largely **conventions** over the same
liquid/vapor mechanics; swarm is a genuinely separate command surface.

## 2. REFLECTED — what bdboard actually displays

bdboard ships a single molecule affordance: a **"+ Pour Formula"** masthead
button opening a native `<dialog>` two-step flow (picker → variable form →
result). This is bdboard's **second write surface** (ADR 0007), reusing the
ADR 0006 mutate/CSRF/SSE/cache plumbing. It reflects **one** mol verb (`pour`,
liquid only).

**Picker — FAITHFUL.** `BdClient.list_formulas()` (`bd.py:624`) shells
`bd formula list --json`; `api_formulas` (`app.py:796`) renders
`formula_list.html` as a `<select>` of `name` + (truncated) `description`. bd
failure degrades to a friendly inline message rather than 500-ing the swap
(`app.py:805-814`). Empty workspace → a hint to add a formula under
`.beads/formulas/` (`formula_list.html`).

**Variable form — FAITHFUL, with a documented gotcha worked around.**
`api_formula_form` (`app.py:824`) reads `BdClient.read_formula_detail(source)`
(`bd.py:675`), which **parses the `*.formula.json` file directly** because the
CLI does not expose this any other way: `formula list`'s `description` is
truncated, `formula show --json` omits `variables`, and the `vars` count is
unreliable (`bd.py:650-708`; ADR 0007 alt D). `formula_form.html` renders one
text input per variable (name=label, description=`aria-describedby` help,
default prefilled, no-default → `required` + red `*` + sr-only "(required)"),
plus a **collapsed `<details>` step disclosure** (title/type/description per
step, `bdboard-078p`). "This formula takes no variables." when the block is
empty.

**Pour — FAITHFUL, incl. count honesty + partial-pour guard.**
`api_formula_pour` (`app.py:882`) CSRF-guards, **server-side pre-flights**
required vars (mirrors the form `required` so a crafted POST can't skip it,
`app.py:945-956`), then `BdClient.pour_formula()` (`bd.py:772`) shells
`bd mol pour <name> --var k=v … --json` (30 s timeout, serialized on the
subprocess gate, **surfaces bd's stderr verbatim** on non-zero exit because
`--dry-run` can't catch every pour-blocker). `formula_pour_result.html`
acknowledges the outcome; the board updates via `store.refresh()` →
SSE `beads_changed` (refresh-before-broadcast, `bdboard-dfl`). Two genuinely
good fidelity touches:
- **Count honesty:** `_pour_counts` (`app.py:762`) reports `created - 1` (the
  hidden molecule wrapper is subtracted) so "N beads added" matches what the
  board actually shows.
- **Partial-pour guard:** when `len(id_mapping) != created`, the result renders
  a  "Partial pour … some steps did not land" alert instead of dressing a
  shortfall up as success (`app.py:788`, `formula_pour_result.html`).

**Grouping-node display — Option A (FAITHFUL to a recorded decision).**
`bd mol pour` mints **two** structural nodes: a `molecule`-typed wrapper
(`new_epic_id`) and the formula's own `epic`-typed root step. Per
`docs/design/bdboard-ain.2/grouping-node-display-decision.md` (Option A) and
ADR 0007: the wrapper is **hidden from the swim lanes** (`_is_molecule`,
`lanes.py:101`; excluded in `lanes()`, `lanes.py:322`), and the epic root step
is **renamed** to `"<formula> <short-id>"` at pour time (`rename_bead`,
`bd.py:837`; `_short_pour_id` reuses bd's own suffix, `app.py:748`) so repeat
pours are distinguishable in the epic strip. The rename is best-effort — a
failure soft-warns ("poured, but couldn't rename …") rather than losing the
atomic pour (`app.py:970-981`).

**Per-bead parent traceability — REFLECTED in the detail modal.** A poured
child's `parent-child` edge is labelled "child of" / "parent of" in the bead
detail field rows (`app.py:75`, `_dep_label`). So you can trace one bead to its
parent epic by opening it — there just isn't a board-level rollup (see 2.1).

### 2.1 NOT reflected (explicit)

- **Phase is entirely invisible; the pour UI is liquid-only.** Grep for
  `phase`/`ephemeral`/`wisp`/`vapor`/`patrol`/`swarm` across `src/bdboard/*.py`
  + templates returns **zero** functional matches (only an unrelated "vapor-pour
  regression" code comment and watcher "refresh phase" comments). There is no
  `bd mol wisp` affordance and no phase selector. (GAP 1, GAP 4.)
- **A vapor-phase formula's warning is swallowed.** `pour_formula` only reads
  stderr on **non-zero** exit (`bd.py:825-827`); `bd mol pour` prints the
  "you poured a vapor-phase formula" warning on stderr with **exit 0**, so
  bdboard discards it. A user pours **persistent, git-synced** work that the
  formula author meant to be **ephemeral**, with no signal. (GAP 1.)
- **No molecule-as-a-unit rollup.** After a pour the epic root step lands in the
  epic strip while the child tasks scatter across **status** swim lanes
  (`lanes.py:322-345`), with no visual grouping back to their parent and no
  child-count / progress rollup. The wrapper — the *true* single parent — is
  hidden. The poured molecule's structure is legible only one bead at a time via
  the modal's parent edge. (GAP 2.)
- **No mol-type/kind distinction.** Even if a wisp or patrol molecule exists
  (created via CLI), bdboard renders its beads as ordinary cards — consistent
  with the flat per-type treatment recorded in `bdboard-anatomy-type-flat`
  (all types render as identical uppercase grey `.bead-type` text). (GAP 3.)
- **Only `pour` is surfaced.** `bond`, `squash`, `burn`, `distill`, `progress`,
  `current`, `seed`, `stale`, `last-activity`, `ready` — none are in the UI.
  `bd mol progress` in particular would directly answer the rollup gap. (GAP 5.)

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | **Write-surface misrepresentation:** pouring a `phase:"vapor"` formula via bdboard silently creates **persistent, git-synced** beads — bd's "you poured a vapor formula" warning rides stderr on **exit 0** and `pour_formula` only reads stderr on failure (`bd.py:825-827`), so the user never sees it. | P2 | File a bead: capture pour stderr even on success and surface a "this formula recommends wisp (ephemeral) — poured as persistent" notice in `formula_pour_result.html`. |
| 2   | **Molecule structure not legible as a unit:** poured children scatter across status lanes with no grouping/progress rollup back to the parent epic, and the true parent (molecule wrapper) is hidden (`lanes.py:322`). Structure is traceable only one bead at a time via the modal. | P2 | File a bead: add an epic→children rollup (count/progress) on the epic strip, optionally backed by `bd mol progress <id> --json`. |
| 3   | **mol-type/phase blindness:** a wisp/patrol molecule (created via CLI) is indistinguishable from plain "work" on the board — no ephemeral/phase marker (consistent with the flat per-type treatment, `bdboard-anatomy-type-flat`). | P3 | File a bead: surface `Ephemeral`/phase as a card chip if/when bd exposes it in `--json`; otherwise track upstream. |
| 4   | **No wisp/ephemeral pour option:** the UI only does `bd mol pour` (liquid). Vapor/ephemeral workflows can't be spawned from the dashboard. Deliberate per ADR 0007 scope, but unsurfaced. | P3 | Optional: add a "pour as ephemeral (wisp)" toggle routing to `bd mol wisp` once the write model is generalized. |
| 5   | **Other mol verbs unsurfaced** (`bond`, `squash`, `distill`, `progress`, `current`, …). Read-mostly posture makes this acceptable, but `bd mol progress` would directly close GAP 2. | P3 | Optional: surface `bd mol progress <id>` as the rollup data source for the epic strip (see GAP 2). |
| 6   | **NO ACTION — Option A wrapper hiding is correct.** The molecule wrapper is the true single parent but has no `blocks` edges and no board value; hiding it (with the epic-root rename) is a recorded, sound decision (grouping-node decision §2–3; ADR 0007). Recorded so synthesis doesn't file a phantom "show the wrapper" gap. | P4 | None — keep Option A. A wrapper-rename failure already soft-warns (`app.py:979`). |
| 7   | **NO ACTION — swarm belongs to area 7.** `bd swarm` (structured-epic coordination) is its own command surface and is audited in `07-swarms.md`; not re-counted here. | P4 | None — cross-reference only; see `07-swarms.md`. |

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

- **Overall verdict: SOLID write-surface, two real blind spots, no P0/P1.** The
  pour flow is one of bdboard's more careful surfaces — it works around three
  documented bd CLI gotchas (truncated description, omitted `variables`, bogus
  `vars` count) by parsing `*.formula.json`, pre-flights required vars
  server-side, surfaces real stderr, reports an **honest** visible count, and
  guards **partial** pours. The two findings worth a follow-up are conceptual,
  not display-correctness bugs: **phase** (GAP 1 — vapor-as-persistent, the one
  genuine write-surface misrepresentation) and **molecule rollup** (GAP 2 — the
  poured tree isn't legible as a unit).
- **Headline reframing of the bead's GAP prompt:** "is a patrol/swarm/wisp
  visually distinct from plain work?" → **No, and mostly by design.** Phase is
  invisible (GAP 3) and the pour UI is liquid-only (GAP 4); *patrol* is a
  convention, *swarm* is area 7, and *wisp* is a lifecycle bdboard can neither
  create nor mark. The actionable slice of that question is GAP 1 (vapor warning
  swallowed), which is a write-surface issue, not a display-distinctness one.
- **Cross-section:** swarms → `07-swarms.md`; the flat per-type rendering that
  underlies GAP 3 is the subject of `01-anatomy.md` / `bdboard-anatomy-type-flat`
  (don't re-file the "types look identical" gap here — it's a board-wide finding,
  surfaced here only as it touches phase).
- **Methodology note:** AVAILABLE sourced from the installed `bd` binary
  (`mol`/`pour`/`wisp`/`swarm` `--help` + `formula list --json`) because
  chapter 5's HTML is an un-extractable base64/React bundle — same constraint
  recorded for chapters 3 & 4.
