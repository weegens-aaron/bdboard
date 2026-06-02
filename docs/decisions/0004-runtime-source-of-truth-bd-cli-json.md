# 0004 — Runtime source of truth is the `bd` CLI JSON

- **Status:** accepted (amended 2026-06-02 — see *Amendment* below)
- **Date:** 2026-06-01
- **Relates to:** README "Behavior highlights" / "Backup", memory
  `stack-overview`, upstream `COMMUNITY_TOOLS.md`. Backfills audit item **M2**.
- **Amended by:** bdboard-e3rw (2026-06-02) — split read model. Cross-links
  bdboard-owz / bdboard-zdz / bdboard-y40 / bdboard-p8v / bdboard-a194 /
  bdboard-gp06.

> At runtime bdboard reads bead state **only** through the `bd` CLI's JSON
> output. It never reads `.beads/issues.jsonl` and never writes to `.beads/`.
> The read is **not** a single `--all` fetch — it is a three-way split
> (active / board-closed / history-closed); see the *Amendment* below.

## Context

There are two superficially available ways to learn bead state:

1. The `bd` CLI's JSON output — backed by the live Dolt DB.
2. The `.beads/issues.jsonl` passive export file sitting right there on disk.

Reading the JSONL file directly looks tempting (no subprocess, just read a
file), but upstream `COMMUNITY_TOOLS.md` declares that path **deprecated** and
warns it may be missing fields. The JSONL is a passive export, not the wire
protocol or the source of truth (it can be stale or absent depending on
`export.auto`).

## Decision

- **Reads** go exclusively through the `bd` CLI in JSON mode (`bd list … --json`,
  `bd show … --json`, etc.), wrapped by `BdClient` in `src/bdboard/bd.py`.
- All `bd` subprocess calls are serialized through one `asyncio.Semaphore(1)`
  (`_subprocess_gate`) because bd's embedded Dolt server is single-writer and
  lock-prone under concurrency.
- **bdboard never writes to `.beads/`** and **never reads `issues.jsonl`.** The
  canonical runtime source of truth is the Dolt DB *as read through the `bd`
  CLI*.

## Amendment (2026-06-02, bdboard-e3rw) — the read is split, not a single `--all` fetch

The original ADR documented a single `bd list --all --no-pager --limit 0 --json`
call as *the* read path. That was true when this ADR was written but is no
longer how the code works. There is **no `list_all` method**. The single fetch
was deliberately decomposed into **three purpose-built reads** in
`src/bdboard/bd.py`, each with a distinct payload-weight and count-honesty
contract:

| Method (`BdClient`) | `bd` invocation | Powers | Bounding |
|---|---|---|---|
| `list_active()` | `bd list --no-pager --limit 0 --json` | Active swim lanes + Activity column; the **fast first-paint path** (~5 KB vs. ~500 KB) | Active statuses only (open / in_progress / blocked / deferred) |
| `list_closed(window_days)` | `bd list --status closed --closed-after <iso> --sort closed --no-pager --limit 0 --json` | **Board** Closed lane **and** header CLOSED KPI | **Date-window-bounded** (`BOARD_CLOSED_WINDOW_DAYS`), *not* count-capped, so the lane and KPI count the **same** set (bdboard-p8v) |
| `list_closed_history(limit, closed_after)` | `bd list --status closed --sort closed --no-pager --limit 0 [--closed-after <iso>] --json` | **History** page | **Count-UNCAPPED by design** — a static cap would make older closures unreachable (bdboard-a194) — but **window-bounded** when a range/custom-date filter is active (bdboard-gp06); the `all` range passes `closed_after=None` for a genuine full-table read |

`bd show … --json` for single-bead detail is unchanged.

### Lazy-load first paint

The split exists to make first paint cheap. `src/bdboard/store.py` keeps **three
independent caches** — `_active_snap`, `_closed_snap`, `_history_snap` — exposed
via `snapshot_active()`, `snapshot_closed()`, and
`snapshot_history(closed_after)`, each lazy-loaded on first access (bdboard-zdz,
bdboard-y40):

1. **Phase 1 — active-only.** `/api/lanes` fetches `snapshot_active()` (~5 KB)
   so the board paints fast. With closed issues absent, a bead depending on a
   closed bead conservatively shows as blocked until the next refresh — an
   accepted trade-off for the ~100× payload reduction (bdboard-owz).
2. **Phase 2 — closed lane.** `/api/lanes/closed` (triggered by HTMX
   `hx-trigger="load"`) fetches `snapshot_closed()` and swaps the closed lane
   in after the active lanes are visible.

`refresh()` (the watcher's entry point) refreshes all three caches and the
`_history_snap` cache is **window-aware**: a wider cached window already covers
any narrower sub-window, so it re-queries bd only on an uncovered, wider request
(bdboard-gp06).

### Count-honesty consequences (do not "simplify" these away)

- **Board CLOSED is a date-bounded set, not a count-capped one.** The masthead
  CLOSED KPI and the Closed lane are deliberately fed by the *same*
  `list_closed` set so the number you read equals the cards you can see. Capping
  by count instead of date would desync them.
- **History is the count-uncapped retrospective.** It must never grow a static
  fetch cap, or older closures silently vanish (bdboard-a194); it bounds by the
  active filter *window* instead (bdboard-gp06).
- **Reverting to a single `--all` fetch would regress three things at once:**
  the payload-weight win, the lazy-load two-phase first paint, and the
  board-vs-history count-honesty trade-offs. None of these are reconstructible
  from the single-fetch prose, which is why they live here now.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Read via `bd … --json` CLI** (now via the split active/closed/history reads above) | Always-fresh, dolt-native; complete field set; the supported, future-proof interface; lets bd own locking/migrations; the split keeps first paint ~100× lighter | Subprocess cost per call (mitigated by caching + the serialization gate) | **CHOSEN** |
| A′. Single `bd list --all --no-pager --limit 0 --json` fetch | One call, simplest wiring | ~500 KB on the hot path → slow first paint; conflates the board's recent-activity window with the History retrospective; forces a single count-cap policy across two surfaces with opposite needs | **Superseded** by the split (this was the original form of this ADR; see the *Amendment*) |
| B. Read `.beads/issues.jsonl` directly | No subprocess; trivial file read | Upstream-deprecated; may be stale/absent; may be missing fields; couples us to an export format that can drift | Rejected |
| C. Talk to the embedded Dolt SQL server directly | Rich queries | Bypasses bd's contracts; brittle to schema changes; reimplements bd | Rejected |

## Consequences

- bdboard is correct-by-construction against whatever bd considers current; no
  staleness from a passive export.
- A read path always has subprocess overhead — accepted, and softened by
  in-process caches + the single subprocess gate. Cache invalidation after any
  mutation keeps reads fresh (see ADR 0005, ADR 0006).
- The three-way split is load-bearing for first-paint latency, the lazy-load
  contract, and count-honesty (see *Amendment*) — treat it as the contract, not
  an optimization to fold back into one fetch.
- We depend on the `bd` binary being on PATH (configurable via `--bd`); that's
  acceptable for a tool whose entire purpose is to visualize a `bd` workspace.
- Revisit only if upstream blesses a stable file/IPC contract faster than the
  CLI.
