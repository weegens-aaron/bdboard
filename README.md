# bdboard

A Python + FastAPI + HTMX dashboard for [bd (beads)](https://github.com/gastownhall/beads) workspaces.

Drop-in replacement for the Go `bcc` (beads-mission-control). `cd` into any
directory containing `.beads/`, run `bdboard`, and a browser tab opens with a
live view of swim lanes, activity, and **bead detail with every field bd exposes**.

## Why Python (vs Go)

- Better Code Puppy / Pydantic AI integration (agents native-extend the dashboard)
- HTMX over the wire instead of React-on-CDN → smaller cold-start, no bundle download
- Faster iteration (save file, refresh — no recompile)
- All-Python stack alignment with the broader beadwork tooling

See `docs/decisions/0002-dashboard-architecture.md` for context.

## Run

```sh
cd /path/to/repo-with-.beads
bdboard                # binds 127.0.0.1:7332 and opens a browser
```

## Install (dev)

```sh
cd bdboard
uv venv
uv pip install -e .
```

## Flags

| Flag | Default | Notes |
| --- | --- | --- |
| `--addr` | `127.0.0.1:7332` | HTTP listen address |
| `--no-browser` | off | Don't auto-launch a browser |
| `--bd` | `bd` | Path to the `bd` binary |
| `--dir` | cwd | Workspace to run in |

## What's different from bcc

| Concern | bcc (Go) | bdboard (Python) |
| --- | --- | --- |
| Bead detail | Misses fields (acceptance criteria, notes, external_ref, …) | Renders every field bd exposes via `bd show --long --json` |
| Bead audit / history | Shells out, fragile (the main user complaint) | Async load with graceful timeout + cache, never blocks the modal |
| Frontend | React from CDN + esbuild bundle | HTMX over the wire, server-rendered fragments |
| Extension | Recompile to add a panel | Edit a template, refresh |

## Heuristics (inherited from bcc, ported faithfully)

- **Lanes** — Backlog / Ready / In-Progress / Blocked / Closed are derived in-process from `.beads/issues.jsonl`
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

You're not in a directory with `.beads/`, or `bd export` has never run there.
`cd` to a bd workspace or pass `--dir /path/to/workspace`.
