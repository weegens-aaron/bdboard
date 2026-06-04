# Troubleshooting (maintainer)

> Operational gotchas for running, developing, and debugging **bdboard**. Each
> entry is **Symptom → Cause → Fix**, with pointers into the code and the doc
> that explains the mechanism in depth. For the big picture start at
> [Architecture](./Architecture.md); for the full catalog see the
> [Manifest](./_Manifest.md).

---

## Startup & ports

### The browser opens on a port I didn't expect (not 7332)

- **Symptom:** You launch bdboard and the tab opens on `:7333`, `:7334`, …
  instead of the documented default `127.0.0.1:7332`.
- **Cause:** bdboard binds `127.0.0.1:7332` by default but **auto-increments to
  the next free port** when 7332 is already taken (e.g. a previous instance is
  still running). This is intentional — it lets you run several workspaces at
  once.
- **Fix:** Pass `--strict-port` to force 7332 and fail loudly if it's busy, or
  just read the actual URL from the startup log. To find/stop a stale instance,
  look for the prior `uvicorn` process. See
  [Flow: ServerStartup](./Flows/ServerStartup.md) and the CLI wiring in
  [`src/bdboard/cli.py`](../src/bdboard/cli.py).

### A browser tab opens when I don't want one (headless / CI / tmux)

- **Symptom:** Running bdboard pops a browser tab you didn't ask for.
- **Cause:** bdboard auto-opens the browser once the socket is live.
- **Fix:** Pass `--no-browser`. The server still binds normally; only the
  `webbrowser.open` call is suppressed. See
  [Flow: ServerStartup](./Flows/ServerStartup.md).

### bdboard points at the wrong workspace or the wrong `bd`

- **Symptom:** The board is empty, or shows beads from a different project.
- **Cause:** Workspace is resolved from `--dir` (or `$PWD`), and the `bd` binary
  from `--bd` (or `$PATH`). A surprising `$PWD` or a shadowed `bd` on `PATH`
  silently picks the wrong source.
- **Fix:** Run with explicit `--dir /path/to/repo` and, if needed,
  `--bd /path/to/bd`. Confirm `.beads/` exists under the chosen dir. See
  [Concept: bd CLI as runtime source of truth](./Concepts/BdCliSourceOfTruth.md)
  and [Flow: ServerStartup](./Flows/ServerStartup.md).

---

## Live refresh

### The board doesn't update when beads change

- **Symptom:** You run `bd update …` in a terminal but the open board doesn't
  move the card until you reload.
- **Cause:** The live-sync chain is
  `bd write → dolt mutates .beads/embeddeddolt/<db>/.dolt/noms/ →
  watchfiles.awatch → RefreshScheduler (debounce + cooldown) → store.refresh()
  → SSE broadcast → HTMX swap`. The watcher (`app._watch_beads`) is
  **non-recursive**, so writes landing outside the watched path won't trip it;
  and the debounce/cooldown deliberately coalesces bursts.
- **Fix:** Confirm your write lands in the watched `.beads/` tree (an
  in-memory or out-of-tree write won't trip the non-recursive watcher). Allow a
  moment for the debounce window to elapse. Verify the page's live-status dot is
  connected (an `EventSource` drop stops swaps). Deep dive:
  [Flow: LiveRefreshPipeline](./Flows/LiveRefreshPipeline.md),
  [Concept: WatcherScheduling](./Concepts/WatcherScheduling.md),
  [Feature: LiveAutoRefresh](./Features/LiveAutoRefresh.md).

### A read-only `bd list` seems to trigger a refresh loop

- **Symptom:** The board appears to refresh even when nothing "changed."
- **Cause:** Even read-only `bd` calls can perturb the Dolt working tree under
  `.beads/`, which would otherwise self-trigger the watcher.
- **Fix:** This is handled by the **self-feedback skip** in the scheduler — if
  you've disabled or bypassed it, refreshes can loop. Keep the skip in place;
  see [Concept: WatcherScheduling](./Concepts/WatcherScheduling.md) and
  [Concept: StoreSnapshotCache](./Concepts/StoreSnapshotCache.md) (the
  `revision_signature` oracle that decides whether a broadcast actually fires).

### My history filter keeps snapping back to the default 30-day window

- **Symptom:** You pick a custom range on `/history`, then a bead changes and
  the view jumps back to the 30-day default.
- **Cause:** `#history-region` carried `hx-trigger="load, refresh from:body"` on
  a **bare** `/api/history` (no params), so every SSE `beads_changed → refresh`
  re-fetched the server-default window and discarded the user's selection.
- **Fix:** This was addressed in `bdboard-li44`; the live re-fetch must preserve
  the active window params. If it regresses, check the `hx-trigger` /
  `hx-get` on `#history-region` and the `/api/history` query handling. See
  [View: HistoryPage](./Views/HistoryPage.md),
  [Endpoint: History API](./Endpoints/HistoryApi.md), and
  [Feature: HistoryAndTrends](./Features/HistoryAndTrends.md).

---

## History page

### The history page is slow / returns a huge result set

- **Symptom:** `/history` takes a while or returns far more closed beads than
  expected.
- **Cause:** The closed-bead source is **count-uncapped**:
  `BdClient.list_closed_history` shells `bd list --status closed --sort closed
  --limit 0`. There is **no hidden cap** — the page's range / custom-date /
  pagination controls are the only thing bounding the result set.
- **Fix:** Tighten the range or page size on the page itself; don't expect a
  server-side ceiling. See [Endpoint: History API](./Endpoints/HistoryApi.md),
  [View: HistoryPage](./Views/HistoryPage.md), and `list_closed_history` in
  [`src/bdboard/bd.py`](../src/bdboard/bd.py).

---

## Formula pour

### `bd formula pour` creates the wrong number of beads (only the root)

- **Symptom:** You pour a formula and get a single root issue instead of the
  full tree, or counts are off.
- **Cause:** A `phase:vapor` formula wisped via `bd mol wisp` materializes
  **only the root issue** unless the formula sets **top-level** `pour: true` — a
  **step-level** `pour:` is ignored.
- **Fix:** Set top-level `pour: true` in the formula. Validate the plan before
  applying (graph creation silently ignores `--dry-run`). See
  [Feature: Formula pour](./Features/FormulaPour.md) and
  [Flow: FormulaPourFanout](./Flows/FormulaPourFanout.md).

### Formula `{{var}}` substitutions don't take their defaults

- **Symptom:** A poured formula has empty/unsubstituted variables even though
  the formula declares defaults.
- **Cause:** `bd formula pour` requires `--var` for **every** `{{var}}`
  referenced in the template and **ignores the variables-block defaults**.
- **Fix:** Pass `--var key=value` for every referenced variable. See
  [Endpoint: Formulas API](./Endpoints/FormulasApi.md) and
  [Flow: FormulaPourFanout](./Flows/FormulaPourFanout.md).

### A poured "validate" task closes before the docs it should gate are written

- **Symptom:** A re-pour/validate task closes immediately, before generated
  output exists.
- **Cause:** A "Re-pour and run the X formula" task that runs `bd formula pour`
  **spawns a separate, disconnected generation epic**; the pour task closes on
  *pour*, not on doc completion. The real output is produced by the spawned
  epic's doc beads.
- **Fix:** After pouring, capture the spawned generation epic and its
  finalize/terminal task id, then add a dependency from the downstream
  *Validate* bead onto that finalize task (tasks can't block epics — depend on
  the terminal task). See [Flow: FormulaPourFanout](./Flows/FormulaPourFanout.md).

---

## Off-machine sync (Dolt)

### Bead changes don't show up on a fresh clone / on another machine

- **Symptom:** You committed bead writes locally but a teammate or fresh clone
  doesn't see them.
- **Cause:** Bead history rides Dolt's git-compatible wire protocol under
  `refs/dolt/data` on the **same** GitHub origin as the code.
  `.beads/issues.jsonl` is a passive export, **not** the wire protocol. A
  misconfigured Dolt remote (pointing at a separate repo) silently strands
  writes — this exact drift was resolved in `bdboard-calu` by repointing the
  Dolt `origin` at the code origin.
- **Fix:** After local `bd` writes + `git commit`, run **`bd dolt push`** to
  replicate. On a fresh clone, hydrate with `bd dolt pull` (or `bd bootstrap`).
  Verify the Dolt remote `origin` matches the code origin. See
  [Concept: bd CLI as runtime source of truth](./Concepts/BdCliSourceOfTruth.md).

---

## Tests & CI

### `uv run` fails in CI on public GitHub runners

- **Symptom:** CI on `ubuntu-latest` fails resolving packages from
  `pypi.ci.artifacts.walmart.com`.
- **Cause:** `uv run` auto-syncs from `uv.lock` **before** running; a lock
  pinned to the internal Walmart artifactory proxy DNS-fails on public runners.
- **Fix:** Use `uv run --no-sync` in CI so it uses the already-installed
  environment instead of re-resolving against the unreachable proxy.

### `uv pip install --system -e .` fails on GitHub runners

- **Symptom:** Install step errors with an externally-managed-environment
  (PEP 668) complaint.
- **Cause:** `--system` installs into the runner's managed Python, which refuses
  the write.
- **Fix:** Create and use a virtualenv (`uv venv` + activate) rather than
  `--system`.

### Local dev quick reference

- **Setup / run / test / lint** are make-driven:
  `make venv` → `make install` → `make dev`/`make run` → `make test` →
  `make lint`/`make fmt`. Linting is `ruff check --fix .` then `ruff format .`.
  See the dev notes in [Architecture](./Architecture.md).

---

## Related

- [Architecture](./Architecture.md) — system diagram, tech stack, API surface,
  and where the code lives.
- [Manifest](./_Manifest.md) — the full catalog of documented items.
- [Flow: ServerStartup](./Flows/ServerStartup.md) ·
  [Flow: LiveRefreshPipeline](./Flows/LiveRefreshPipeline.md) ·
  [Flow: FormulaPourFanout](./Flows/FormulaPourFanout.md) — the pipelines behind
  the startup, live-refresh, and pour gotchas above.
- [Concept: WatcherScheduling](./Concepts/WatcherScheduling.md) ·
  [Concept: StoreSnapshotCache](./Concepts/StoreSnapshotCache.md) ·
  [Concept: bd CLI as runtime source of truth](./Concepts/BdCliSourceOfTruth.md)
  — the timing, caching, and source-of-truth mechanics.
- [Endpoint: History API](./Endpoints/HistoryApi.md) ·
  [View: HistoryPage](./Views/HistoryPage.md) — the history filter/perf entries.
- [Feature: Live auto-refresh](./Features/LiveAutoRefresh.md) ·
  [Feature: Formula pour](./Features/FormulaPour.md) — the user-visible features
  whose failure modes are catalogued here.
- [Sections: Features](./Features/index.md) · [Flows](./Flows/index.md) ·
  [Endpoints](./Endpoints/index.md) · [Views](./Views/index.md) ·
  [Concepts](./Concepts/index.md)
