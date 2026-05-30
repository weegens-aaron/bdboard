# bdboard

A Python + FastAPI + HTMX dashboard for [bd (beads)](https://github.com/gastownhall/beads) workspaces.

`cd` into any directory containing `.beads/`, run `bdboard`, and a browser tab
opens with a live view of swim lanes, activity, and **bead detail with every
field bd exposes**.

**Who it's for:** developers using `bd` who want an at-a-glance, always-fresh
web view of a workspace's beads without leaving their terminal-driven workflow.

## Install (dev)

```sh
cd bdboard
uv venv
uv pip install -e .
```

## Run

```sh
cd /path/to/repo-with-.beads
bdboard                # binds 127.0.0.1:7332 and opens a browser
```

## Code health (CI gates)

The mechanical, deterministic code-health checks run on every push/PR via
`.github/workflows/code-health.yml` and gate merges. Run the exact same set
locally with:

```sh
make code-health      # lint + dead-code + duplication + audit
make outdated         # advisory only (dependency staleness)
```

These checks live in CI rather than a bd formula by design — see
[`docs/decisions/0002-dashboard-architecture.md`](docs/decisions/0002-dashboard-architecture.md).

| Gate | Tool | Make target | Config |
| --- | --- | --- | --- |
| Lint + format + unused-import/dead-code (F401, F811, F841) | ruff | `make lint` / `make fmt` | `[tool.ruff]` in `pyproject.toml` |
| Dead-code sweep (≥80% confidence) | vulture | `make dead-code` | inline flag |
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

## Behavior highlights

- **Lanes** — Deferred / Ready / In-Progress / Blocked / Closed are derived in-process from `bd list --json` snapshots
- **Activity** — derived from `updated_at` / `closed_at` / `created_at` because bd doesn't expose a global audit feed; rendered as a swim lane alongside the bead lanes
- **JSONL freshness** — bdboard reads bead state via `bd list --all --no-pager --limit 0 --json` (the dolt-native, always-fresh path). We do NOT read `.beads/issues.jsonl` directly — per the upstream [COMMUNITY_TOOLS.md](https://github.com/gastownhall/beads/blob/main/docs/COMMUNITY_TOOLS.md), that path is deprecated and may be missing fields. A `watchfiles` watcher walks `.beads/` recursively so any dolt write inside `.beads/embeddeddolt/` triggers a refresh within ~250ms (debounced) + ~1s cooldown. SSE pushes a single `beads_changed` event only when the bead list actually changed (structural equality vs the previous cache). No `bd export` calls; bdboard never writes to `.beads/`.

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
