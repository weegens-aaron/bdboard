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

## flowdoc-generate

Generate feature/flow documentation for a repo **from scratch**, FlowDoc-style
— document what the code *does* (features, flows, endpoints, views, concepts),
not a file inventory. Replaces the old `flowdoc` / `flowdoc-user` agent-loop.

Unlike the fixed-shape formulas above, this one **fans out at runtime**: it
spawns a 3-step skeleton (epic → `discover` → `finalize`), and the `discover`
step surveys the repo, scaffolds the docs tree, then creates **one doc bead per
manifest item** (count is repo-dependent). `finalize` is gated on every
spawned doc via `waits_for: children-of(discover)`, so it only becomes ready
once the whole fan-out is closed.

**Audience variable.** This is the first formula here to declare a variable:

| `--var audience=` | Docs dir | Voice |
|---|---|---|
| `maintainer` (default) | `__docs/` | developer-facing: file paths, mermaid, API/View tables |
| `user` | `_docs/` | end-user-facing: no code, no source paths, task/outcome oriented |

**Run it (recommended — persistent / pour):**

```bash
bd mol pour flowdoc-generate --var audience=maintainer  # developer docs in __docs/
bd mol pour flowdoc-generate --var audience=user        # end-user docs in _docs/
```

> [!IMPORTANT]
> **`--var audience=` is mandatory on bd 1.0.4.** The variable carries a
> declared `default` of `maintainer`, but bd 1.0.4's `mol pour` requires an
> explicit value for every `{{var}}` referenced in the template and does **not**
> apply the formula's default — running `bd mol pour flowdoc-generate` with no
> `--var` errors with *"missing required variables: audience"*. Always pass
> `--var audience=maintainer` (or `=user`). The `default` is kept in the schema
> as forward-looking intent for when bd honors it. (Verified bdboard-mol-iuv.)

Use `--dry-run` (with the `--var`) to preview the 4 skeleton issues (proto +
epic + `discover` + `finalize`) — the per-item doc beads are created when
`discover` actually runs, so they don't appear in the dry run. Poured from
within whatever repo needs docs, so the repo is implicit.

### Note on phase / the vapor↔pour gotcha

Same approach as the others: **no `phase:vapor`**, **top-level `pour:true`**
kept as a safety net so a stray `bd mol wisp` still materializes the full
skeleton instead of a silently-empty root.

## flowdoc-maintain

Audit an **existing** FlowDoc doc set for drift and apply fixes, one item per
loop/judge cycle. Replaces the old `flowdoc-maintainer` /
`flowdoc-user-maintainer` agent-loop. **Precondition:** the matching
`DOCS_DIR/_Manifest.md` must already exist — run `flowdoc-generate` first.

Like `flowdoc-generate`, it **fans out at runtime**: a 3-step skeleton (epic →
`audit` → `finalize`); `audit` detects drift, scores each finding by impact,
writes `_UpdateQueue.md`, then spawns **one fix bead per queue item**
(UPDATE / NEW / REMOVE / VERIFY / LEAKAGE). `finalize` is gated via
`waits_for: children-of(audit)` and archives the queue into `_AuditLog.md`.

| `--var audience=` | Docs dir | Scoring lens |
|---|---|---|
| `maintainer` (default) | `__docs/` | engineer/maintainer impact |
| `user` | `_docs/` | end-user impact + developer-leakage scan |

**Run it (recommended — persistent / pour):**

```bash
bd mol pour flowdoc-maintain --var audience=maintainer
bd mol pour flowdoc-maintain --var audience=user
```

> [!IMPORTANT]
> Same bd 1.0.4 gotcha as `flowdoc-generate`: **`--var audience=` is
> mandatory** — bd ignores the variables-block default. Use `--dry-run` (with
> the `--var`) to preview the 4-issue skeleton; the per-finding fix beads are
> created when `audit` runs, so they don't appear in the dry run.

Same phase approach as the others: **no `phase:vapor`**, **top-level
`pour:true`** kept as a safety net.

## flowdoc-html

Build the static HTML documentation site(s) from the FlowDoc markdown using the
`md-to-html` skill — a standalone capability (replaces the old `DocsToHTML` /
`HTMLSiteBuild` flow). Pour it **after** a generate or maintain pass. It spawns
a 2-step skeleton (epic → `build`); the `build` child converts `__docs/` →
`docs/maintainer/` and/or `_docs/` → `docs/user/` and refreshes the top-level
`docs/index.html` landing page.

| `--var target=` | Builds |
|---|---|
| `both` (default) | maintainer (`__docs/`→`docs/maintainer/`) **and** user (`_docs/`→`docs/user/`) |
| `maintainer` | maintainer site only |
| `user` | user site only |

**Run it (recommended — persistent / pour):**

```bash
bd mol pour flowdoc-html --var target=both
bd mol pour flowdoc-html --var target=maintainer
bd mol pour flowdoc-html --var target=user
```

> [!IMPORTANT]
> Same bd 1.0.4 gotcha: **`--var target=` is mandatory** — bd ignores the
> variables-block default. Use `--dry-run` (with the `--var`) to preview the
> 3-issue skeleton (proto + epic + `build`).

Same phase approach as the others: **no `phase:vapor`**, **top-level
`pour:true`** kept as a safety net.

> [!NOTE]
> **Skill portability (audit gap H1/H2).** The `md-to-html` skill is *preferred
> but optional*. The `build` step resolves it in order — `<repo>/skills/…`,
> `<repo>/.beads/skills/…`, the flowdoc toolkit checkout — and if none is found
> falls back to an **explicit build contract** so the site still builds on an
> arbitrary poured repo. That contract pins the carry-over items that used to be
> left implicit: mermaid rendering, `[!NOTE]/[!TIP]/[!WARNING]` callout boxes,
> per-section `index.html` pages, a shared `style.css`, and `.md`→`.html`
> relative-link rewriting. The VERIFY gate fails the build if any are missing.
