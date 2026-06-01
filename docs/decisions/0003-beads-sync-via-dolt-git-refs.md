# 0003 — Beads sync via Dolt git-refs (Approach A)

- **Status:** accepted
- **Date:** 2026-06-01
- **Relates to:** bdboard-6gp (spike), bdboard-9i7 (implementation), README
  "Backup (beads issue data)". Backfills audit item **M1**.

> Beads issue data is replicated off-machine using Dolt's git-compatible wire
> protocol (`bd dolt push`/`pull` to `refs/dolt/data` on the **existing** git
> origin) — **not** by committing `issues.jsonl`, and **not** via third-party
> Dolt hosting.

## Context

The real bead database lives in `.beads/embeddeddolt/` (Dolt embedded mode) and
is gitignored. Spike bdboard-6gp verified (bd 1.0.4) that:

- `.beads/issues.jsonl` is not tracked and `export.auto: false`.
- `bd dolt remote list` → "No remotes configured."
- `git ls-remote origin` showed **no** `refs/dolt/data`.

⇒ Issue history (then ~95 issues + the full audit trail) was **not replicated
off-machine at all**, and a fresh clone got zero issues. A single-machine
failure would have lost everything. We needed a way to version issue data
alongside the code.

> **Note on current deployment.** This repo is presently operated *local-only*
> (no remote configured) — see the README backup section. ADR 0003 records the
> chosen sync *mechanism* (the decision from bdboard-6gp/9i7) so that whenever
> off-machine sync is enabled, it uses Dolt git-refs and never the JSONL path.

## Decision

When syncing beads off-machine, use **Approach A — Dolt git-refs on the
existing origin**:

```bash
bd dolt remote add origin <existing git origin URL>
bd dolt push          # data rides under refs/dolt/data, separate from refs/heads/*
bd dolt pull          # fresh-clone hydration (one-time; hooks can automate)
```

Dolt data lives under `refs/dolt/data` on the **same** GitHub remote as the
code, fully separate from `refs/heads/*`. Dolt remains the canonical store; this
matches what bdboard reads at runtime (see ADR 0004).

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. `bd dolt push` to `refs/dolt/data` on the existing origin** | Documented bd "wire protocol"; cell-level structured merge, never collides with code branches; preserves full history/audit/lineage; first-class multi-machine sync; reuses existing GitHub creds | Fresh clone needs a one-time `bd dolt pull` (custom refspec not auto-fetched) | **CHOSEN** |
| B. Commit `.beads/issues.jsonl` on normal branches | File is "just there" in a clone | Frequent textual merge conflicts; lossy vs Dolt; trips the JSONL-as-truth + routine-`bd import` anti-patterns | Rejected |
| C. Third-party Dolt hosting (DoltHub etc.) | Purpose-built | Extra account/host/auth surface for zero benefit over reusing origin | Rejected |

## Consequences

- Issue history can survive loss of the local `.beads/embeddeddolt/` and a fresh
  clone can hydrate the full audit trail with one `bd dolt pull`.
- We never treat `issues.jsonl` as the sync channel or routinely `bd import`
  (both are declared anti-patterns); the local JSONL backup stays
  recovery-only.
- CI that only needs code is unaffected (won't fetch the dolt ref); CI that
  needs issues runs `bd dolt pull` with the same creds as code.
- Revisit if bd changes its sync protocol or the project genuinely needs a
  hosted multi-tenant store.
