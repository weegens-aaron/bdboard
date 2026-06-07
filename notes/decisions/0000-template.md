# NNNN — <short, present-tense decision title>

- **Status:** proposed | accepted | superseded by [NNNN](NNNN-….md) | deprecated
- **Date:** YYYY-MM-DD
- **Relates to:** <bead id(s), spike/design docs, README sections this replaces>
- **Supersedes / Superseded by:** <link, if any>

> One-sentence summary of the decision. The rest of the file is the *why*.

## Context

What forces are at play? What problem, constraint, or pressure makes a
decision necessary? Keep it factual — the situation as it actually is, not the
solution. Link to the bead(s)/spike(s) where the investigation happened.

## Decision

The decision, stated in the active voice ("We do X"). Be specific and
load-bearing — a future reader should be able to tell *exactly* what was
chosen.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. <chosen>** | … | … | **CHOSEN** |
| B. <rejected> | … | … | Rejected |

Recording the rejected paths (and *why* they lost) is the whole point of an
ADR — it stops the next person from re-litigating a settled question.

## Consequences

What becomes easier? What becomes harder? What new constraints does this
impose? What would have to be true for us to revisit this decision?

---

<!--
HOW TO USE THIS TEMPLATE
1. Copy to docs/decisions/NNNN-kebab-title.md using the NEXT free number
   (zero-padded, monotonically increasing; never reuse a number).
2. Fill every section. Delete a section only if it is genuinely N/A and say so.
3. ADRs are immutable once accepted. To change a decision, write a NEW ADR that
   supersedes the old one, and add a "Superseded by" pointer to the old file —
   do not rewrite history.
4. See README.md in this directory for when an ADR is warranted vs a design doc.
-->
