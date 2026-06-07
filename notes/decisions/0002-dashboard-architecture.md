# 0002 — Dashboard architecture: Python + FastAPI + HTMX

- **Status:** accepted
- **Date:** 2026-05-30
- **Relates to:** README onboarding audit (relocated this rationale out of the README)

> This ADR captures the *why* behind bdboard's stack and a couple of related
> implementation choices. It is the home for decision/rationale content that
> used to live inline in `README.md`. The README links here; it does not
> re-litigate these decisions.

## Context

bdboard is a local-first dashboard for `bd` (beads) workspaces. It needs to
start fast from a `cd` into any repo with `.beads/`, render rich bead detail,
and stay easy to extend — including by Code Puppy / Pydantic AI agents that
live in the broader beadwork tooling.

## Decision 1 — Python (vs Go)

We build bdboard in Python rather than Go.

- **Better Code Puppy / Pydantic AI integration** — agents native-extend the
  dashboard without a language boundary.
- **HTMX over the wire instead of React-on-CDN** — smaller cold-start, no
  bundle download.
- **Faster iteration** — save file, refresh; no recompile step.
- **All-Python stack alignment** with the broader beadwork tooling.

### Trade-offs accepted

- Python's runtime startup is heavier than a static Go binary, but the
  local-first, single-user usage pattern makes that immaterial.
- Distribution is a `uv`/pip install rather than a single binary; acceptable
  given the audience already runs `bd` and a Python toolchain.

## Decision 2 — Code-health checks live in CI, not a bd formula

The mechanical, deterministic code-health checks (lint, dead-code,
duplication, CVE audit) run in `.github/workflows/code-health.yml` and gate
merges — they are **not** packaged as a bd *formula*.

**Why CI and not a bd formula?** bd *formulas* spawn work; they do not run
checks. These deterministic pass/fail checks belong in CI gating every PR,
leaving the `code-health-audit` formula to **triage** CI output
rather than re-run the tools (see `notes/design/formula-spike/`).

## Consequences

- The README stays focused on *what bdboard is* and *how to run it*; the
  rationale for these choices lives here and is linked, not inlined.
- Future stack/tooling decisions should be recorded as additional ADRs in
  `notes/decisions/` rather than expanding the README.
