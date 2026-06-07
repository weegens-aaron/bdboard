# Architecture Decision Records (ADRs)

This directory is the **canonical home for architectural decisions** in
bdboard. If a choice shapes the architecture, the data flow, the runtime
contract, or a process that the whole project relies on, it gets an ADR here —
not a bead note, not a code comment, not a one-off design doc.

> **Why this file exists.** Two successive audits
> (`notes/tasks/bdboard-mol-c09/` and `notes/tasks/bdboard-mol-7up/`) found that
> architectural decisions kept landing in bead notes / design docs / code
> comments because there was no frictionless, canonical ADR path. This index +
> the [template](0000-template.md) *are* the fix (bdboard-jdd). When in doubt,
> write the ADR — friction here was the root cause of every prior gap.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions (use ADRs) | accepted |
| [0002](0002-dashboard-architecture.md) | Dashboard architecture: Python + FastAPI + HTMX | accepted |
| [0003](0003-beads-sync-via-dolt-git-refs.md) | Beads sync via Dolt git-refs (Approach A) | accepted |
| [0004](0004-runtime-source-of-truth-bd-cli-json.md) | Runtime source of truth is the `bd` CLI JSON | accepted |
| [0005](0005-live-refresh-architecture.md) | Live-refresh architecture (watcher → Store.refresh → SSE) | accepted |
| [0006](0006-manual-field-editing-model.md) | Manual field-editing model (registry, whitelist, append-only) | accepted |
| [0007](0007-formula-pour-ui-write-surface.md) | UI-triggered formula pour (workspace-mutating write surface via `bd mol pour`) | accepted |

> Keep this table in sync when you add an ADR. The number is the next free,
> zero-padded, monotonically increasing integer — never reuse one.

## When do I write an ADR vs. a design doc?

There are two decision homes in this repo and they have **distinct jobs**.
Use this rule:

### `notes/decisions/NNNN-*.md` — **ADRs (this directory)**

Write an ADR when the decision is **durable, cross-cutting, and architectural**:

- It shapes the architecture, data flow, or a runtime/process *contract* the
  whole project depends on (e.g. "the source of truth is the `bd` CLI", "beads
  sync over Dolt git-refs").
- A future contributor reading *only the code* could not reconstruct *why* it
  is the way it is, and getting it wrong would be expensive.
- It rejects a tempting obvious alternative that someone will otherwise try to
  "simplify" back to later.

ADRs are **short, numbered, and immutable**. To change one, write a new ADR
that supersedes it (add a "Superseded by" pointer to the old one).

### `notes/design/<bead-id>/*.md` — **design docs & spike outputs**

Write/keep a design doc when the artifact is **exploratory or scoped to one
piece of work**:

- A spike's findings, an editability matrix, UI/UX option exploration, a
  feature's detailed design — the *working material* behind a bead.
- It is tied to a specific bead's lifecycle (named after the bead id) and may
  contain more breadth/detail than a crisp decision record.

A `notes/design/<bead-id>/*-decision.md` file is fine as the **deliverable of a
single bead**, but if the decision it records is architectural and durable,
**also distil it into an ADR here** and have the design doc point at the ADR.
When an ADR supersedes the assumptions in a design doc, add a "Superseded by"
note to the design doc so the stale doc points forward (see
`notes/design/bdboard-ace/cadence-invoker-decision.md`).

### TL;DR

| Question | Answer → home |
|---|---|
| Durable architectural/process contract? | **ADR** (`notes/decisions/`) |
| Working material / spike output for one bead? | **design doc** (`notes/design/<bead-id>/`) |
| Both (architectural decision born in a spike)? | ADR + design doc that **links to** the ADR |
