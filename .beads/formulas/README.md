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
bd mol pour docs-validation --var repo=bdboard
```

`pour` is persistent (git-synced, audit trail) and is the recommended path for
this formula — docs drift is worth a permanent record. Use `--dry-run` first to
preview the 6 issues without creating them.

### Chosen cadence

- **Cadence: quarterly**, invoked **manually** via `bd mol pour` at the start of
  each quarter (lowest-friction starting point; no scheduler dependency).
- Automation / invoker is intentionally **out of scope** here and tracked
  separately in **bdboard-ace** (decide cadence + invoker for recurring
  maintenance formulas). Manual quarterly pour is the interim policy so adoption
  isn't blocked on building a scheduler.

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

A quarterly code-health audit that spawns an epic + 4 task children
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
bd mol pour code-health-audit --var repo=bdboard --var quarter=2026-Q2
```

Use `--dry-run` first to preview the 6 issues (proto + epic + 4 children)
without creating them — bd counts the formula root proto alongside the
epic and its 4 task children. Variables: `repo` (default `bdboard`), `quarter`
(default `this-cycle`).

### Chosen cadence

- **Cadence: quarterly**, invoked **manually** via `bd mol pour` — same
  interim policy as `docs-validation`. Automation/invoker is tracked
  separately in **bdboard-ace**.

### Note on phase / the vapor↔pour gotcha

Same approach as `docs-validation`: **no `phase:vapor`**, but **top-level
`pour:true`** kept as a safety net so a stray `bd mol wisp` still materializes
the full tree instead of a silently-empty root. Verified: both
`bd mol pour ... --dry-run` and `bd mol wisp ... --dry-run` report 6 issues.
