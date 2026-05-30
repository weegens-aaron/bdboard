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
