# bd formulas (shipped)

Formulas in this directory are **active** — they show up in `bd formula list`
and can be referenced by name (`bd cook <name>`, `bd mol pour <name>`,
`bd mol wisp <name>`). Don't drop scratch/sketch formulas here; keep those in
`docs/design/` until they're intentionally promoted (see bdboard-zda spike).

## docs-validation

A documentation validation pass that spawns an epic + 4 task children
(README accuracy, stale setup steps, broken-link sweep, ADR coverage).
File one bead per defect found — the value is consistency + a per-finding
audit trail, not running checks (formulas spawn work; they don't run it).

**Run it (recommended — persistent / pour):**

```bash
bd mol pour docs-validation
```

`pour` is persistent (recorded in the local bead database with a full audit
trail) and is the recommended path for
this formula — docs drift is worth a permanent record. Use `--dry-run` first to
preview the 6 issues without creating them. The formula declares no variables,
so no `--var` flags are needed; it's poured from within whatever repo needs it,
so the repo is implicit.

### Invocation policy

- Invoked **manually** via `bd mol pour` (lowest-friction starting point; no
  scheduler dependency). How often to run it is an operational choice, not
  baked into the formula text.
- Automation / invoker was **decided in bdboard-ace**: stay manual for now, no
  scheduler shipped, with explicit revisit triggers. See the full rationale,
  runbook, and revisit criteria in
  `docs/design/bdboard-ace/cadence-invoker-decision.md`.

### Note on phase / the vapor↔pour gotcha

This formula deliberately **omits `phase:vapor`** (so the recommended `pour`
path doesn't emit a "use wisp instead" warning) but **keeps top-level
`pour:true`** as a safety net.

Per memory `formula-vapor-pour-gotcha`: a formula run as a **wisp**
materializes ONLY the root issue unless **top-level `pour:true`** is set
(step-level `pour:` is ignored). Keeping `pour:true` means that even if someone
later runs `bd mol wisp docs-validation`, the full epic + 4 children still
materialize instead of a silently-empty root. Verified: both
`bd mol pour ... --dry-run` and `bd mol wisp ... --dry-run` report 6 issues.

## code-health-audit

A code-health audit that spawns an epic + 4 task children
(DRY triage, SOLID review, dead-code triage, dependency-hygiene triage).

The key design point (bdboard-jyf): the **mechanical** pass/fail checks
(ruff/vulture, jscpd, pip-audit) already run in CI — see
`.github/workflows/code-health.yml` (shipped in bdboard-ndm). The formula
children therefore **TRIAGE the CI output** — they do NOT re-run the tools.
Formulas spawn judgment work; CI runs the checks. The lone exception is the
**SOLID review** child, which is genuinely a human/agent assessment with no
mechanical CI equivalent.

File one bead per finding via the Bug Discovery Protocol — don't fix inline
unless blocking.

**Run it (recommended — persistent / pour):**

```bash
bd mol pour code-health-audit
```

Use `--dry-run` first to preview the 6 issues (proto + epic + 4 children)
without creating them — bd counts the formula root proto alongside the
epic and its 4 task children. The formula declares no variables, so no `--var`
flags are needed; it's poured from within whatever repo needs it, so the repo
is implicit.

### Invocation policy

- Invoked **manually** via `bd mol pour` — same policy as `docs-validation`.
  How often to run it is an operational choice, not baked into the formula
  text. Automation / invoker was **decided in bdboard-ace** (stay manual, no
  scheduler; revisit triggers documented in
  `docs/design/bdboard-ace/cadence-invoker-decision.md`).

### Note on phase / the vapor↔pour gotcha

Same approach as `docs-validation`: **no `phase:vapor`**, but **top-level
`pour:true`** kept as a safety net so a stray `bd mol wisp` still materializes
the full tree instead of a silently-empty root. Verified: both
`bd mol pour ... --dry-run` and `bd mol wisp ... --dry-run` report 6 issues.
