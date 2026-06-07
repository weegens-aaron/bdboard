# 0001 — Record architecture decisions (use ADRs)

- **Status:** accepted
- **Date:** 2026-06-01
- **Relates to:** bdboard-jdd (ADR process gap), audits in
  `notes/tasks/bdboard-mol-c09/` and `notes/tasks/bdboard-mol-7up/`

> We record significant architectural and process decisions as numbered ADRs
> in `notes/decisions/`. This is ADR 0001 — it both establishes the practice and
> backfills the missing `0001` slot (process gap X1).

## Context

bdboard's `notes/decisions/` directory began at `0002-dashboard-architecture.md`
— there was never a `0001`, no ADR template, and no index. Worse, decisions had
**two competing homes** with no rule for which to use:

- `notes/decisions/NNNN-*.md` — formal ADRs (a single one existed).
- `notes/design/<bead-id>/*-decision.md` — bead-scoped decision docs.

Two successive decision-coverage audits (bdboard-mol-c09, then bdboard-mol-7up)
found that, because there was no frictionless canonical path, architectural
decisions kept landing in bead notes, design docs, and code comments. The
second audit's headline finding: **nothing from the first audit was ever
written down.** The missing template/index/home (gap X2) was the root cause.

## Decision

1. **`notes/decisions/` is the canonical home for architectural decisions.**
   We use the lightweight Nygard-style ADR format captured in
   [`0000-template.md`](0000-template.md).
2. **Numbering is monotonic and zero-padded** (`0001`, `0002`, …); numbers are
   never reused, and ADRs are **immutable once accepted** — superseding a
   decision means writing a *new* ADR and adding a "Superseded by" pointer to
   the old one.
3. **The split between ADRs and design docs is defined** in
   [`README.md`](README.md): durable/cross-cutting architectural contracts →
   ADR; exploratory, bead-scoped working material → `notes/design/<bead-id>/`.
   A decision born in a spike gets distilled into an ADR *and* linked from its
   design doc.
4. This ADR occupies the previously-missing `0001` slot, closing gap X1.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Lightweight numbered ADRs + index + template (this)** | Low friction; immutable record; standard, widely understood format; one canonical home kills the "where does this go?" ambiguity | A little upfront structure to maintain | **CHOSEN** |
| B. Keep decisions in bead notes only | Zero new files | Not discoverable from the repo; audits already proved decisions evaporate; bead notes are append-only logs, not curated records | Rejected — this *is* the status quo that failed twice |
| C. One big `DECISIONS.md` log | Single file to grep | Grows unbounded; merge-conflict magnet; no per-decision immutability/supersession story | Rejected |

## Consequences

- New significant decisions **must** be recorded here; reviewers can ask "where's
  the ADR?" as a normal part of review.
- The four decisions the audits flagged as missing are backfilled as ADRs
  0003–0006; design docs that an ADR supersedes get forward-pointers.
- Maintaining the index table in `README.md` is a small ongoing cost, accepted
  in exchange for discoverability.
- Revisit only if the team adopts a different ADR tool; the *practice* of
  recording decisions is not expected to change.
