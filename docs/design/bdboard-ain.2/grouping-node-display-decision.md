# Decision: how the formula grouping node shows on the board (molecule vs epic)

- **Bead:** bdboard-ain.2 (task / decision + minimal implementation)
- **Parent epic:** bdboard-ain — Add beads to the board from a formula via a UI element
- **Discovered from:** bdboard-9n4 (formula-to-board UI spike), §3.3
- **Status:** decided — **Option A**, with the derive-layer half shipped here
- **Date:** 2026-05-29

> Deliverable for bdboard-ain.2. Records the chosen approach for surfacing a
> formula-poured workflow's grouping node on the board, the options
> considered, and which half of the work ships in *this* bead vs. the UI bead
> (bdboard-ain.1).

---

## 1. Problem

`bd mol pour <formula>` creates **two** structural nodes for the grouping
(verified empirically in spike bdboard-9n4, §3.1):

| Node       | issue_type | title source           | role                          |
|------------|------------|------------------------|-------------------------------|
| wrapper    | `molecule` | bare formula name      | returned `new_epic_id`; parent of all |
| root step  | `epic`     | the root step's title  | the formula's own epic        |
| children   | `task`     | each step's title      | the actual work               |

`src/bdboard/derive/lanes.py::_is_epic` matches **only** `issue_type == "epic"`.
Consequences before this bead:

- The **molecule wrapper** does **not** appear in the epic strip — it falls
  through to `lanes()` and renders as a stray card in the **ready** lane.
- The **epic root step** **does** appear in the strip, but carries the *step*
  title (e.g. "Code-health audit: bdboard (Q2-2026)"), not the desired
  `<formula> <id>` disambiguator.

So out of the box the board shows a redundant molecule card AND an epic with
the wrong (non-unique) name. This bead decides how to fix that.

---

## 2. Options considered

### Option A — rename the epic root step; hide the molecule wrapper (CHOSEN)

- Locate the formula's epic root step via `id_mapping["<formula>.<rootStep>"]`
  (or the lone `issue_type == "epic"` child of the wrapper) and rename it to
  `<formula> <id>` at pour time.
- Hide the bare `molecule` wrapper from the swim lanes so it doesn't float as
  a redundant ready-lane card.

**Pros:** smallest change; the epic root step already surfaces in the strip
with zero changes to the epic-strip topology/sequencing logic or its
contrast/derive tests. **Cons:** the wrapper still exists in bd as the true
single parent — we just don't render it (acceptable; it has no board value).

### Option B — teach `_is_epic` + the epic strip + templates to surface molecule wrappers, and rename the wrapper

**Pros:** the wrapper is the genuine single parent of the tree, so surfacing
*it* is arguably more "correct". **Cons:** touches `derive` (epic sequencing,
the `blocks`/parent-child graph walk), templates, and a swathe of
contrast/derive tests. Molecule wrappers have no `blocks` edges among
themselves, so they'd always be unwired loners in the strip anyway — all cost,
little extra value over A.

**Spike recommendation (bdboard-9n4 §3.3): start with Option A**, and consider
hiding the bare molecule wrapper. We adopt exactly that.

---

## 3. Decision (TL;DR)

- **Option A.** The human-readable `<formula> <id>` name is carried by the
  formula's **epic root step** (renamed at pour time); the **molecule wrapper
  is hidden from the swim lanes**.
- **Unique id:** generated **by bdboard wrapping the pour**, never baked into
  the formula (formulas are reusable templates). Per spike §3.2, the
  lowest-risk option is to reuse the unique suffix bd already minted on
  `new_epic_id` (the segment after the last `-`); a freshly generated 6-char
  token is an acceptable alternative. The id-generation + rename is the UI
  bead's responsibility (bdboard-ain.1), since it happens in the pour route.

---

## 4. What ships in THIS bead

The derive-layer half of Option A — the part that is pure, testable, and
independent of the pour route:

- `derive/lanes.py::_is_molecule(bead)` — new helper, symmetric with
  `_is_epic`, matching `issue_type == "molecule"`.
- `lanes()` now excludes molecule wrappers (alongside epics) from the swim
  lanes, so a poured wrapper never renders as a stray ready-lane card.
- `_is_molecule` re-exported from `bdboard.derive` for test/back-compat
  symmetry with `_is_epic`.
- Tests: wrapper excluded from lanes, wrapper excluded from the epic strip,
  and the `_is_molecule` helper itself.

## 5. What belongs to the UI bead (bdboard-ain.1) — explicitly out of scope here

- Generating the short unique id and running
  `bd update <epic-root-step-id> --title "<formula> <id>"` after a successful
  pour (the rename happens in the pour route, which the UI bead builds).
- Locating the epic root step via `id_mapping["<formula>.<rootStep>"]`.

These were deliberately left to bdboard-ain.1 to keep this bead's change
test-light and free of new I/O (the spike's stated goal for Option A).
