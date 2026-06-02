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

## Quick start (fresh clone)

The full setup, in order. A fresh clone has **no bead database**, so
`bd bootstrap` comes *first* — skip it and `bdboard` renders an empty board
(see [Getting the bead history](#getting-the-bead-history-fresh-clone)).

```sh
git clone https://github.com/weegens-aaron/bdboard.git
cd bdboard
bd bootstrap --yes          # hydrate the bead DB (one-time; fresh clones ship none)
make install                # uv venv + editable install (resolves against public PyPI)
source .venv/bin/activate   # activate the venv (run once per shell session)
make test                   # optional: confirm the suite is green
bdboard                     # binds 127.0.0.1:7332 and opens a browser
```

The sections below break these steps out individually.

## Install (dev)

```sh
cd bdboard
make install           # uv venv + editable install (resolves against public PyPI)
source .venv/bin/activate   # activate the venv (run once per shell session)
```

Prefer the raw commands? They're equivalent:

```sh
cd bdboard
uv venv
uv pip install -e .
source .venv/bin/activate
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

From within a bd workspace (any directory containing `.beads/`):

```sh
bdboard                        # binds 127.0.0.1:7332 and opens a browser
```

Or use `make run` from the bdboard repo (runs against this repo's own
`.beads/` workspace):

```sh
cd bdboard
make run                       # equivalent to .venv/bin/bdboard
```

> bdboard only works inside a bd workspace. From a non-`.beads/` directory it
> reports "workspace not ready" — `cd` into one or pass `--dir /path/to/workspace`.

> **Fresh clone? Hydrate first.** A freshly-cloned bdboard workspace ships
> **no** bead database (`.beads/embeddeddolt/` is gitignored), so `bdboard`
> starts but renders an **empty board** until you run `bd bootstrap --yes`
> once. See [Getting the bead history (fresh clone)](#getting-the-bead-history-fresh-clone)
> for the one-time hydration step.

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

- **Lanes** — Deferred / Blocked / Ready / In-Progress / Closed are derived in-process from `bd list --json` snapshots
- **Activity** — derived from `updated_at` / `closed_at` / `created_at` because bd doesn't expose a global audit feed; rendered as a swim lane alongside the bead lanes
- **JSONL freshness** — bdboard reads bead state via the `bd list ... --json` CLI (the dolt-native, always-fresh path), using a **three-way split** rather than a single `--all` fetch (see [ADR 0004](docs/decisions/0004-runtime-source-of-truth-bd-cli-json.md)): (1) active issues via `bd list --no-pager --limit 0` (no `--all`, so closed are excluded) — the ~5 KB fast first-paint path; (2) the **board** Closed lane + header CLOSED KPI via `bd list --status closed --closed-after <iso> --sort closed --no-pager --limit 0`, **date-window-bounded** (`BOARD_CLOSED_WINDOW_DAYS`) — *not* count-capped — so the lane and KPI count the same set (bdboard-p8v); and (3) the **History** page via `bd list --status closed --sort closed --no-pager --limit 0 [--closed-after <iso>]`, which is **count-uncapped by design** so older closures never silently vanish (bdboard-a194) but is window-bounded when a range filter is active (bdboard-gp06). The closed lane is lazy-loaded as a second phase after the active lanes paint (`hx-trigger="load"`). We do NOT read `.beads/issues.jsonl` directly — per the upstream [COMMUNITY_TOOLS.md](https://github.com/gastownhall/beads/blob/main/docs/COMMUNITY_TOOLS.md), that path is deprecated and may be missing fields. A `watchfiles` watcher observes each dolt database's `noms/` directory (plus `.beads/` itself) **non-recursively** so any bd write triggers a refresh within ~250ms (debounced) + ~1s cooldown. We deliberately avoid recursively watching the whole `.beads/` tree: dolt's churning `noms/` object store would open a kqueue fd per directory on macOS and exhaust `RLIMIT_NOFILE`. SSE pushes a single `beads_changed` event only when the bead list actually changed (structural equality vs the previous cache). No `bd export` calls; bdboard never writes to `.beads/`.

## Getting the bead history (fresh clone)

Issue history is replicated off-machine using Dolt's git-compatible wire
protocol — it rides under `refs/dolt/data` on the **same** GitHub origin as the
code, **not** as a committed `issues.jsonl`. That custom ref is **not**
auto-fetched by a normal `git clone`, and the local Dolt DB itself
(`.beads/embeddeddolt/`) is gitignored — so a bare clone has **no bead
database at all**. Until you hydrate once, `bd list` reports `no beads database
found` and `bdboard` renders an **empty board**. (See
[`docs/decisions/0003-beads-sync-via-dolt-git-refs.md`](docs/decisions/0003-beads-sync-via-dolt-git-refs.md)
for the full rationale.)

After cloning, hydrate the bead database with a one-time `bd bootstrap`:

```sh
git clone https://github.com/weegens-aaron/bdboard.git
cd bdboard
bd bootstrap --yes        # auto-detects refs/dolt/data on the git origin and clones it
bd list                   # should now be non-empty — full issue history is local
```

`bd bootstrap` auto-detects the dolt data ref on the git `origin`. If your clone
somehow lacks the dolt remote, point it at the **code** origin (the same repo —
per ADR 0003 we do *not* use a separate dolt repo) before bootstrapping:

```sh
bd dolt remote add origin git+https://github.com/weegens-aaron/bdboard.git
bd bootstrap --yes
```

> **Gotcha — don't use `bd init` + `bd dolt pull` for a fresh clone.** `bd init`
> seeds an **independent** Dolt history, so a subsequent `bd dolt pull` fails
> with `Error 1105: no common ancestor`. Use `bd bootstrap`, which clones the
> remote history directly. (Hydration of ~200 issues takes ~40s; a raw
> pull-into-init can churn for minutes before erroring.)

## Backup (beads issue data)

Issue data **is** replicated off-machine. The Dolt remote `origin` points at
the same GitHub origin as the code (`weegens-aaron/bdboard.git`), and the full
issue history rides under `refs/dolt/data` there via Dolt's git-compatible wire
protocol — **not** as a committed `issues.jsonl`. See
[`docs/decisions/0003-beads-sync-via-dolt-git-refs.md`](docs/decisions/0003-beads-sync-via-dolt-git-refs.md)
for the full rationale, and [Getting the bead history](#getting-the-bead-history-fresh-clone)
for how a fresh clone hydrates.

To push local bead writes off-machine:

```sh
bd dolt push        # replicates issue history to refs/dolt/data on origin
```

The bead database lives in `.beads/embeddeddolt/` (gitignored) and is the
single source of truth, read at runtime through the `bd` CLI. `bd dolt pull`
brings remote changes back down on another machine.

> bdboard never writes to `.beads/` and never reads `.beads/issues.jsonl`; the
> canonical, runtime source of truth is the Dolt DB as read through the `bd` CLI.

> If any `bd` command hangs, you may have hit the stale `dolt sql-server`
> accumulation issue — run `pkill -9 -f 'dolt sql-server'` (see
> [Troubleshooting](#bead-detail-or-bd-itself-hangs)) and retry.

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

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev
setup and the checks CI enforces.

## License

Released under the [MIT License](LICENSE).
