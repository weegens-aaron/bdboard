# bdboard

A Python + FastAPI + HTMX dashboard for [bd (beads)](https://github.com/gastownhall/beads) workspaces.

`cd` into any directory containing `.beads/`, run `bdboard`, and a browser tab
opens with a live view of swim lanes, activity, and **bead detail with every
field bd exposes**.

**Who it's for:** developers using `bd` who want an at-a-glance, always-fresh
web view of a workspace's beads without leaving their terminal-driven workflow.

## Prerequisites

| Tool | Why | Notes |
| --- | --- | --- |
| **`bd` (beads)** | **Required at runtime** — bdboard shells out to the `bd` binary for every bead read (see `src/bdboard/bd.py`). Without it on `PATH`, the board comes up but every lane/detail/memory/history view fails. | [install from upstream](https://github.com/gastownhall/beads); confirm with `bd --version` |
| **Python ≥ 3.11** | runtime | `pyproject.toml` `requires-python` |
| **uv** | venv + installer | `uv --version` |
| Node + `npx` | only for `make duplication` (jscpd) | bundled toolchains skip this |
| `lychee` | only for `make links` | `brew install lychee` |

## Install (dev)

```sh
cd bdboard
make install           # uv venv + editable install (resolves against public PyPI)
```

Prefer the raw commands? They're equivalent:

```sh
cd bdboard
uv venv
uv pip install -e .
```

> **Behind a private package mirror?** `make install` reads two optional
> environment variables and passes them through to `uv` — nothing is
> hard-coded, so the public default stays clean:
>
> ```sh
> export PY_INDEX_URL=https://mirror.example.com/simple
> export PY_TRUSTED_HOST=mirror.example.com   # only if the mirror is self-signed
> make install
> ```

## Run

```sh
cd /path/to/repo-with-.beads   # MUST be a bd workspace (a dir containing .beads/)
bdboard                        # binds 127.0.0.1:7332 and opens a browser
```

> bdboard only works inside a bd workspace. From a non-`.beads/` directory it
> reports "workspace not ready" — `cd` into one or pass `--dir /path/to/workspace`.

## Test

```sh
make test              # runs the full pytest suite against this repo's own .beads workspace
```

## Code health (CI gates)

The mechanical, deterministic code-health checks run on every push/PR via
`.github/workflows/code-health.yml` and gate merges. Run the exact same set
locally with:

```sh
make code-health      # lint + format-check + dead-code + tests + duplication + audit
make outdated         # advisory only (dependency staleness)
```

These checks live in CI rather than a bd formula by design — see
[`docs/decisions/0002-dashboard-architecture.md`](docs/decisions/0002-dashboard-architecture.md).

| Gate | Tool | Make target | Config |
| --- | --- | --- | --- |
| Lint + unused-import/dead-code (F401, F811, F841) | ruff | `make lint` | `[tool.ruff]` in `pyproject.toml` |
| Format check (no rewrites) | ruff | `make fmt-check` (`make fmt` rewrites) | `[tool.ruff]` in `pyproject.toml` |
| Dead-code sweep (≥80% confidence) | vulture | `make dead-code` | inline flag |
| Tests | pytest | `make test` | — |
| Copy-paste duplication | jscpd | `make duplication` | `.jscpd.json` |
| Dependency CVE scan | pip-audit | `make audit` | — |
| Outdated deps (advisory, never fails) | uv | `make outdated` | — |

## Flags

| Flag | Default | Notes |
| --- | --- | --- |
| `--addr` | `127.0.0.1:7332` | HTTP listen address |
| `--no-browser` | off | Don't auto-launch a browser |
| `--bd` | `bd` | Path to the `bd` binary |
| `--dir` | cwd | Workspace to run in |
| `--strict-port` | off | Fail if the requested port is taken instead of auto-incrementing (default scans 20 ports from the start port) |

## Behavior highlights

- **Lanes** — Deferred / Ready / In-Progress / Blocked / Closed are derived in-process from `bd list --json` snapshots
- **Activity** — derived from `updated_at` / `closed_at` / `created_at` because bd doesn't expose a global audit feed; rendered as a swim lane alongside the bead lanes
- **JSONL freshness** — bdboard reads bead state via `bd list --all --no-pager --limit 0 --json` (the dolt-native, always-fresh path). We do NOT read `.beads/issues.jsonl` directly — per the upstream [COMMUNITY_TOOLS.md](https://github.com/gastownhall/beads/blob/main/docs/COMMUNITY_TOOLS.md), that path is deprecated and may be missing fields. A `watchfiles` watcher observes each dolt database's `noms/` directory (plus `.beads/` itself) **non-recursively** so any bd write triggers a refresh within ~250ms (debounced) + ~1s cooldown. We deliberately avoid recursively watching the whole `.beads/` tree: dolt's churning `noms/` object store would open a kqueue fd per directory on macOS and exhaust `RLIMIT_NOFILE` (see bdboard-3sf). SSE pushes a single `beads_changed` event only when the bead list actually changed (structural equality vs the previous cache). No `bd export` calls; bdboard never writes to `.beads/`.

## Backup & cross-machine sync (beads issue data)

The real bead database lives in `.beads/embeddeddolt/`, which is **gitignored** —
so your code branches (`refs/heads/*`) carry *none* of the issue history. To keep
the 95+ issues and their audit trail safe off-machine, beads replicates the Dolt
database over its git-compatible wire protocol to a separate ref
(`refs/dolt/data`) on the **same GitHub origin** you already push code to. This is
the project-blessed "Approach A" (see bead `bdboard-6gp`); we deliberately do
**not** commit `.beads/issues.jsonl` as the sync channel and do **not** use any
third-party Dolt host.

### One-time setup (already done on this repo)

```sh
bd dolt remote add origin https://github.com/weegens-aaron/bdboard.git
bd dolt push        # creates refs/dolt/data on origin
```

Verify the off-machine backup exists:

```sh
git ls-remote origin 'refs/dolt/*'
# c5ea0469...   refs/dolt/data
```

### Routine backup

After a batch of bead changes, push them off-machine:

```sh
bd dolt commit      # flush any pending working-set changes (no-op if clean)
bd dolt push        # replicate to refs/dolt/data on origin
```

Auth uses the **same GitHub HTTPS/PAT credentials as your code pushes** — no
extra secret to manage. CI that only builds code is unaffected (it never fetches
the `refs/dolt/data` ref); CI that needs issues runs `bd dolt pull`.

### Fresh-clone hydration (verified)

The Dolt remote config is stored *inside* the gitignored `.beads/embeddeddolt/`
database, so a brand-new `git clone` does **not** inherit the remote and the
installed `post-checkout` / `post-merge` hooks will **not** auto-hydrate issue
data on their own. Worse, a fresh clone has **no local Dolt database at all** —
so `bd dolt remote add` fails with `Error: no beads database found` until you
create one. The correct order is: `bd init` (creates the empty local DB), *then*
re-add the remote, *then* pull:

```sh
git clone https://github.com/weegens-aaron/bdboard.git
cd bdboard
bd init                                                              # create the local .beads/embeddeddolt/ DB (required before any bd dolt command)
bd dolt remote add origin https://github.com/weegens-aaron/bdboard.git
bd dolt pull        # hydrates .beads/embeddeddolt/ from refs/dolt/data
bd ready            # confirm issues are present
```

> If any `bd dolt` step hangs, you've hit the stale `dolt sql-server`
> accumulation issue — run `pkill -9 -f 'dolt sql-server'` (see
> [Troubleshooting](#bead-detail-or-bd-itself-hangs)) and retry.

> The local-only Dolt archive backup in `.beads/backup/` (gitignored, a set of
> `.darc` archive files) is a belt-and-suspenders recovery export **only** —
> never the wire protocol and never the source of truth. (bd can also emit a
> JSONL export to `.beads/issues.jsonl`, but bdboard never reads it.) The
> canonical, runtime source of truth is the Dolt DB as read through the `bd` CLI.

## Troubleshooting

### Bead detail (or bd itself) hangs

bd embeds dolt; each `bd` invocation can leave a `dolt sql-server` subprocess
running. Over weeks of use these accumulate and start fighting each other for
locks. Symptom: bd commands hang, bdboard's bead-detail panel times out, etc.

Fix:

```sh
pkill -9 -f 'dolt sql-server'
```

Then bd — and bdboard — will be snappy again. If you see this happen often,
file an issue upstream against bd.

### bdboard says "workspace not ready"

You're not in a directory with `.beads/`.
`cd` to a bd workspace or pass `--dir /path/to/workspace`.
