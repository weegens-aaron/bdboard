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
- **JSONL freshness** — bdboard reads bead state via the `bd list ... --json` CLI (the dolt-native, always-fresh path), using two queries rather than a single `--all` fetch: active issues via `bd list --no-pager --limit 0` (no `--all`, so closed are excluded), and the closed lane lazy-loaded/capped via `bd list --status closed --sort closed --no-pager --limit <cap>`. We do NOT read `.beads/issues.jsonl` directly — per the upstream [COMMUNITY_TOOLS.md](https://github.com/gastownhall/beads/blob/main/docs/COMMUNITY_TOOLS.md), that path is deprecated and may be missing fields. A `watchfiles` watcher observes each dolt database's `noms/` directory (plus `.beads/` itself) **non-recursively** so any bd write triggers a refresh within ~250ms (debounced) + ~1s cooldown. We deliberately avoid recursively watching the whole `.beads/` tree: dolt's churning `noms/` object store would open a kqueue fd per directory on macOS and exhaust `RLIMIT_NOFILE`. SSE pushes a single `beads_changed` event only when the bead list actually changed (structural equality vs the previous cache). No `bd export` calls; bdboard never writes to `.beads/`.

## Backup (beads issue data)

This project is **local-only**: there is no git or dolt remote, so issue data
is not synced or pushed anywhere off this machine. The bead database lives in
`.beads/` and is the single source of truth, read at runtime through the `bd`
CLI.

If you want an off-machine backup, copy the `.beads/` directory with your
regular file-backup tooling. (`bd` does support a git-compatible remote sync
protocol, but it is not configured or used here.)

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
