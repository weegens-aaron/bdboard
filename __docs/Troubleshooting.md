# bdboard — Troubleshooting (maintainer edition)

> Audience: **maintainers**. A symptom → cause → fix index distilled from the
> edge cases, error scenarios, failure-handling, and debugging notes surfaced
> while documenting bdboard. Each entry links to the deep dive that explains the
> *why* in full. Start with the symptom that matches what you're seeing; most
> entries point at a regression bead (`bdboard-…`) so you can read the original
> context.
>
> Quick orientation: bdboard is read-mostly, the `bd` CLI is the single runtime
> source of truth, and the live UI is *filesystem change → debounced refresh →
> SSE `beads_changed` → HTMX re-fetch*. Most "it's stuck / it's wrong" symptoms
> are one of: the watcher/refresh half stalled, the SSE half dropped, or a
> derive-layer scope being misread. See [Architecture](./Architecture.md).

## How to read this page

Each entry is **Symptom → Likely cause → Where to look → Fix / expected
behaviour**. "Where to look" names the log line, test, or `curl` recipe that
isolates the half at fault. Before filing a bug, confirm the behaviour isn't a
documented, intentional tradeoff (several "bugs" below are by design).

---

## 1. The board stops updating (live refresh)

### 1.1 Board frozen until I restart bdboard

- **Likely cause:** the self-feedback loop returned — a read-only `bd list`
  itself re-touches `journal.idx`/`manifest` inside the watched `noms/` dir, so
  the watcher fires for bdboard's *own* read ~1.3 s later and an in-flight
  refresh gets cancelled by the event it triggered (regression `bdboard-ywep`).
- **Where to look:** tail the syslog while making a `bd` write. Look for
  `store: bd list failed; keeping previous snapshot` or a refresh that never
  completes. Check the live-status pill: `live · push` with no update means the
  watcher/refresh half is the suspect (not the SSE socket).
- **Fix / expected behaviour:** two guards must both hold —
  `notify()` must never cancel an **in-flight** refresh (only the cancellable
  debounce/cooldown sleep), and `Store.refresh()` must skip `bd list` when the
  dolt `revision_signature()` is byte-identical to last time. See
  [Flow: Live-refresh pipeline](./Flows/live-refresh-pipeline.md) and
  [Concept: Watcher scheduling](./Concepts/watcher-scheduling.md).

### 1.2 A single isolated `bd update` doesn't show up

- **Likely cause:** the *last* event of a burst has no successor, so a write
  landing inside the cooldown window was dropped on the assumption "a later
  event will retrigger" (regression `bdboard-xbc7` #1).
- **Fix / expected behaviour:** the scheduler must **wait out the remaining
  cooldown and then refresh**, never discard a trailing/isolated event. Covered
  by `tests/test_watcher_scheduler.py::test_trailing_event_after_cooldown_still_refreshes`.

### 1.3 Board stops firing after the db is replaced / re-cloned

- **Likely cause:** macOS kqueue watches **inodes, not paths**; a dolt-replaced
  `noms/` dir or a brand-new db silently stops firing events
  (regression `bdboard-xbc7` #2).
- **Fix / expected behaviour:** `_rescan_targets` detects the signature change
  and re-enters `awatch` with fresh targets — no process restart. See
  [Concept: Watcher scheduling](./Concepts/watcher-scheduling.md).

### 1.4 One transient `bd list` failure wedges all future syncs

- **Likely cause:** a failed refresh advanced the cooldown clock, so the next
  real event got swallowed by a cooldown the system "earned" without ever
  syncing (regression `bdboard-xbc7` #3).
- **Fix / expected behaviour:** the cooldown clock advances **only after a
  successful refresh**; a hiccup self-heals on the next event and the previous
  snapshot is served stale rather than flashing empty.

### 1.5 Every tab re-fetches constantly for no visible change

- **Likely cause:** the SSE broadcast is firing unconditionally on watcher
  events. Pure dolt-internal churn and memory-only `bd remember` writes change
  no bead state.
- **Fix / expected behaviour:** the broadcast is **gated on `store.refresh()`
  returning `True`** — structural equality of the cached snapshot is the dedup.
  See [Feature: Live auto-refresh](./Features/live-auto-refresh.md).

> [!WARNING]
> Any change to the refresh path must preserve the `revision_signature()` skip
> and the "don't cancel in-flight refresh" rule, or the self-feedback loop
> (`bdboard-ywep`) returns and the board freezes until relaunch.

---

## 2. Startup, workspace & port problems

### 2.1 bdboard crashes on launch in an iCloud / Documents / Desktop folder

- **Likely cause:** macOS TCC blocks `os.getcwd()` in synced folders, and a
  default arg like `os.environ.get("BDBOARD_WORKSPACE", os.getcwd())` runs
  `getcwd()` on **every** import (Python evaluates default args eagerly) even
  when the env var is set.
- **Fix / expected behaviour:** use the `or` short-circuit so `_safe_cwd()` runs
  only when the env var is genuinely absent; with no `--dir` the CLI falls back
  to `$PWD`. See [Flow: Server startup](./Flows/server-startup.md).

### 2.2 The app points at a different directory than the CLI chose

- **Likely cause:** a second `getcwd()`/`--dir` read crept into the app module
  or `BdClient`, re-deriving the workspace (especially under uvicorn `--reload`,
  where the reloader re-imports the module).
- **Fix / expected behaviour:** workspace identity is decided **once** in
  `_resolve_workspace` and propagated by the `BDBOARD_WORKSPACE` env var — the
  env var is the contract. Confirm with the workspace name in the dashboard
  shell or by inspecting `BDBOARD_WORKSPACE` in the server env.

### 2.3 `uvicorn bdboard.app:app --reload` (or a bare import) crashes

- **Likely cause:** `bd.validate()` was moved to import time or into `lifespan`
  to "fail fast", which crashes every test that merely imports the module in a
  directory without `.beads/`.
- **Fix / expected behaviour:** validation must stay **request-time and lazy**
  (`_validate_or_warn`). A non-bd dir renders `error.html` (which echoes the
  exact path it tried), not a traceback.

### 2.4 bdboard started on an unexpected port

- **Likely cause:** the default port `7332` was busy, so it auto-scanned
  `7332..7351`. Watch stdout for `port 7332 busy — using 7333 instead`.
- **Fix / expected behaviour:** this is intentional. To force a port and fail
  loudly instead of hopping, use `--strict-port`. List listeners with
  `lsof -iTCP -sTCP:LISTEN`. See [`cli.py`](../src/bdboard/cli.py).

---

## 3. Formula pour problems

### 3.1 Success message reports one more bead than I can see

- **Likely cause:** `bd`'s raw `created` count includes the hidden molecule
  wrapper that bdboard deliberately excludes from the board, so reporting it raw
  over-counts by one.
- **Fix / expected behaviour:** always route the count through `_pour_counts`,
  which returns `created - 1` (floored at 0) as the visible count. See
  [Feature: Formula pour](./Features/formula-pour.md) and
  [Flow: Formula pour fan-out](./Flows/formula-pour-fanout.md).

### 3.2 Poured beads don't appear until I manually refresh

- **Likely cause:** the optimistic `bus.broadcast("beads_changed")` raced ahead
  of the watcher→refresh cycle and clients re-fetched a stale snapshot
  (regression `bdboard-dfl`).
- **Fix / expected behaviour:** `store.refresh()` MUST run **before**
  `bus.broadcast("beads_changed")` on the pour route — the filesystem watcher
  alone is too slow/debounced to rely on here.

### 3.3 The pour form shows no variables (or wrong/blank ones)

- **Likely cause:** variables were read from `bd formula show --json` (omits the
  `variables` block) or `bd formula list --json` (truncated description, `vars`
  count always `0`).
- **Fix / expected behaviour:** read variables and the untruncated description
  from the on-disk `*.formula.json` file via the `source` path bd reports. (If a
  future bd release exposes variables through `formula show --json`, switch and
  drop the file read.)

### 3.4 Empty wrapper epics piling up / a pour silently half-completed

- **Likely cause:** `len(id_mapping) != created` — not every node landed (a
  bd-layer vapor-pour, or a formula that lost its top-level `pour: true`), and
  the mismatch was masked as success.
- **Fix / expected behaviour:** surface a partial-pour **warning** (advising to
  check `pour: true` and remove the incomplete epic) and `log.warning` the
  shortfall — never report it as a clean success. Inspect what bd actually
  created by hand with
  `bd mol pour <name> --var … --json` and compare `len(id_mapping)` to `created`.

### 3.5 Pour "fails" but the beads were actually created

- **Likely cause:** the wrapper **rename** failed *after* the atomic pour
  already succeeded. Rename is best-effort.
- **Fix / expected behaviour:** a rename failure appends a *soft warning* (the
  tree shows under the formula name) and never undoes the pour. Look for
  `pour rename of <id> failed: …` in the syslog.

> [!CAUTION]
> Do not "simplify" the reported count to bd's raw `created`, and do not mask an
> `id_mapping`/`created` mismatch as success. Both defeat the count-honesty and
> partial-pour guarantees and let empty wrapper epics accumulate invisibly.

---

## 4. Inline bead editing problems

### 4.1 A field edit refuses to save (403 / 400 / 409)

- **Likely cause(s):** the edit hit a server-side gate —
  - `403` — failed CSRF, **or** the bead is `in_progress`/closed
    (`_bead_is_editable` is false: locked beads are read-only).
  - `400` — the field isn't whitelisted in `_FIELD_REGISTRY`, or an empty
    `notes` append was submitted.
  - `409` — optimistic-lock conflict: the bead's `updated_at` moved since the
    form was rendered ("this bead changed since you opened it").
- **Where to look:** the route logs each gated rejection
  (`locked field edit rejected: …`, `stale field edit rejected: … expected=…
  live=…`). Reproduce with the curl recipe in
  [Endpoint: Bead field-edit API](./Endpoints/bead-field-edit-api.md#curl-example).
- **Fix / expected behaviour:** these gates are intentional and enforced
  **server-side**, not just in the UI. See
  [Flow: Field-edit write path](./Flows/field-edit-write-path.md).

### 4.2 A failed save wiped / blanked the row

- **Likely cause:** something bypassed the client error-routing. Error bodies
  are HTML fragments with `role="alert"`, not JSON; HTMX won't swap non-2xx.
- **Fix / expected behaviour:** the `htmx:beforeSwap` handler in
  [`base.html`](../src/bdboard/templates/base.html) cancels the row swap on
  4xx/5xx and routes the message into the per-row `data-edit-feedback` aria-live
  region — a failed save **never wipes the row**; the edit form stays open.

### 4.3 An edit silently clobbered another writer

- **Likely cause:** the optimistic-lock precondition used a cached read (up to
  `SUCCESS_TTL_S = 10s` old), reporting a stale `updated_at`/status.
- **Fix / expected behaviour:** the precondition MUST use
  `show_long(bead_id, fresh=True)` — the freshness bypass is the whole point.

### 4.4 Adding a note replaced the whole notes field / nuked history

- **Likely cause:** `notes` was edited with a replace-style flag. `bd update
  --notes` *replaces* the field and destroys append-only audit/verification
  history.
- **Fix / expected behaviour:** never edit `notes` with a replace flag, and
  never call `bd update --notes` by hand. The registry pins `notes` to
  `--append-notes` and marks it `append_only`; the route rejects empty appends
  and the template offers only an "Add a note" box. This is the documented
  anti-pattern.

### 4.5 A crafted POST tried to write `status` / `parent` / `story_points`

- **Likely cause:** an attempt to widen what's writable from the client side.
- **Fix / expected behaviour:** the endpoint is **field-scoped, not
  bead-scoped** — the client supplies only a field *name*; the server pulls
  `spec.flag` from `_FIELD_REGISTRY` and rejects any non-whitelisted field. A
  new editable field is **one entry** in the registry (open/closed + DRY).

### 4.6 A field bd added recently doesn't show in the modal

- **Likely cause / expected behaviour:** this should **not** happen.
  `_ordered_fields` walks `_FIELD_ORDER` first then appends any unlisted keys
  alphabetically, so a new bd field renders at the bottom (read-only until
  whitelisted) instead of vanishing. If it's missing, that guardrail regressed.
  See [Endpoint: Bead detail API](./Endpoints/bead-detail-api.md).

### 4.7 The bead detail modal shows a "Cached snapshot" banner

- **Likely cause / expected behaviour:** the live `bd show` failed, so the modal
  fell back to the cached snapshot and flipped `source` to `"Cached snapshot"`
  rather than 404-ing. Only a genuinely-unknown bead 404s. Not a bug — a
  graceful degradation.

---

## 5. History page problems

### 5.1 KPI cells seem to contradict each other

- **Likely cause / expected behaviour:** two KPI scopes look alike but aren't.
  **Total** and **Closed (all time)** come from bd's workspace-global
  `status_summary()` and do **not** react to the range control; **Avg lead**,
  **Closed (range)**, **Median lead**, and **Throughput** are range-scoped. Each
  cell carries an info-icon popover spelling out its scope. See
  [Feature: History & trends](./Features/history-and-trends.md).

### 5.2 The two global KPI cells disappeared

- **Likely cause / expected behaviour:** `status_summary()` returned `None` (any
  `bd status` hiccup), so the two global cells are omitted and the range-derived
  KPIs remain — graceful degradation, not an error.

### 5.3 Chart, KPIs, and closed list disagree on the window (off-by-one)

- **Likely cause:** the window bound was re-derived separately per metric.
- **Fix / expected behaviour:** the window is resolved **once** from a single
  `now`, and that `(cutoff, ceiling)` drives the `--closed-after` fetch bound
  *and* every in-memory derive slice (`bdboard-gp06`). Never re-derive per
  metric.

### 5.4 Old closures are missing from the history list

- **Likely cause / expected behaviour:** check the window, not a count cap.
  History is uncapped on count (`--limit 0`) so the long tail stays reachable
  (`bdboard-a194`); it's bounded only by the window. `range=all` and a
  `to_date`-only custom window resolve `cutoff=None` (genuine unbounded read).
  Note: the **board** Closed lane *is* date-bounded (3 days) — see §6.2.

### 5.5 A live refresh snapped the history view back to the 30d default

- **Likely cause:** the SSE re-fetch hit a bare `/api/history` with no query
  params.
- **Fix / expected behaviour:** `base.html` reads the active range/custom window
  + persisted page size from the live DOM and re-injects them on the SSE refresh
  (`bdboard-li44`).

### 5.6 A bead is missing from a chart series

- **Likely cause / expected behaviour:** beads with no parseable timestamp are
  excluded from the relevant series (no `closed_at` ⇒ off closed list/throughput;
  no `created_at` ⇒ off created series; no `started_at` ⇒ off cycle-time). Plus
  negative/zero durations are dropped from lead/cycle stats (clock skew). Both
  are intentional — a single bad row can't poison the medians.

> [!CAUTION]
> Do **not** add per-param `4xx` validation to `/api/history` "to be strict."
> The contract is graceful degradation: a tampered/stale query string must
> always paint *something* useful. Every clamp lives in the
> [derive layer](./Concepts/derive-layer.md) so the endpoint stays a thin, total
> function.

---

## 6. Board / lane / count discrepancies

### 6.1 A ready bead shows as "Blocked" on first paint, then fixes itself

- **Likely cause / expected behaviour:** `/api/lanes` fetches *active* issues
  only (the ~100× TTFP win, `bdboard-0yy`), so a bead whose sole blocker is
  already closed isn't in view — `_has_unmet_blocking_dep` conservatively
  treats the unknown target as unmet and renders **Blocked**. It corrects to
  **Ready** on the next SSE `refresh` (full snapshot). The Activity column has
  the same property. This is the accepted tradeoff, **not a bug** — do *not*
  widen `/api/lanes` to fetch the full snapshot to "fix" it. See
  [Feature: Swim-lane board](./Features/swim-lane-board.md).

### 6.2 The Closed lane / CLOSED count omits old closures

- **Likely cause / expected behaviour:** the board Closed set is **date-bounded
  at fetch time** (`BOARD_CLOSED_WINDOW_DAYS` / `bd.list_closed()` with
  `--closed-after now−3d`), not count-capped. The Closed lane and the masthead
  CLOSED KPI share the same 3-day window so they can never disagree
  (`bdboard-p8v`). For older closures use the
  [History page](./Views/history-page.md) (§5), which has its own unbounded path.

### 6.3 The CLOSED header count and the Closed lane drift at the window edge

- **Likely cause / expected behaviour:** this should **not** happen. The 12h/1d/3d
  filter is client-only: the server ships the full window once and
  `applyBoardFilter()` narrows it, feeding the **same** `visibleCount` into both
  the lane badge and the KPI via `syncMastheadClosedCount` (`bdboard-de4z`). Do
  *not* add a server-side `?window=` param — it reintroduces a client-now vs
  server-now skew. See [Endpoint: Lanes API](./Endpoints/lanes-api.md).

### 6.4 The In-Progress count cell is missing from the masthead

- **Likely cause / expected behaviour:** `in_progress` is **deliberately
  omitted** from `/api/counts`. bdboard is single-flight (one bead in progress
  at a time), so a 0/1 cell is noise — the In-Progress *lane* already surfaces
  the active bead. (`derive.counts`,
  `tests/test_derive_counts.py::test_counts_excludes_in_progress`.)

### 6.5 A bead vanished from the board entirely

- **Likely cause / expected behaviour:** this should **not** happen.
  `lanes()` routes any unknown status (bd built-ins like `hooked`/`pinned` or
  custom statuses) into the **Deferred** catch-all so nothing silently
  disappears (`bdboard-yed`), and `_topo_component_order` appends unplaceable
  nodes (a dependency cycle) in stable order rather than dropping epics. A
  molecule wrapper *is* intentionally hidden (its human name rides the epic root
  step). If a normal bead is gone, that fall-through regressed.

> [!CAUTION]
> Don't key the time-filter / count-sync JS off the visible label text in the
> counts strip — it's text-transformed and re-wordable. Target the stable
> `data-count-status` / `data-closed-at` / `data-closed-count` hooks instead. And keep the Ready/Blocked bucketing in the
> [derive layer](./Concepts/derive-layer.md), never in the template.

---

## 7. Memory page problems

### 7.1 Editing a memory created a second one instead of renaming

- **Likely cause:** the Key field was editable in the edit dialog. `bd remember
  --key K` is an upsert keyed on `K`, so changing the key creates a new memory
  and orphans the original.
- **Fix / expected behaviour:** the Key field is **read-only when editing**
  (`editMemory` sets `readonly`). To "rename," forget the old key and create a
  new one deliberately. See [Feature: Memory management](./Features/memory-management.md).

### 7.2 A phantom "schema_version" card appeared

- **Likely cause:** `bd memories --json` returns the flat key→body object **plus**
  a `schema_version` sentinel that is *not* a memory.
- **Fix / expected behaviour:** the wrapper strips the sentinel; a payload of
  *only* the sentinel (the empty/no-match shape) yields an empty list, not a
  phantom card.

### 7.3 Posting an existing key replaced its body with no "already exists" error

- **Likely cause / expected behaviour:** intentional. `POST /api/memory` is
  **upsert by key** — there's no separate edit endpoint; posting an existing key
  *replaces* its body by design (the dialog hint says so). Empty key/body are
  trimmed and rejected with a `400` before any subprocess runs.

### 7.4 A memory disappeared and degraded later agent sessions

- **Likely cause / expected behaviour:** `bd forget` is **irreversible** and
  memories feed `bd prime`, so a stray delete silently degrades every future
  agent session. The UI gates deletes behind a confirm-before-forget `<dialog>`
  ([`memory.html`](../src/bdboard/templates/memory.html)); scripts hitting
  `DELETE /api/memory/{key}` directly bypass that friction — handle with care.
  (DELETE accepts the token only via the `X-CSRF-Token` header.)

### 7.5 The memory list won't load

- **Likely cause / expected behaviour:** if `bd.memories()` raises, the GET
  handler logs a warning and returns a friendly **`200`** placeholder
  ("Couldn't load memories right now…") rather than a broken swap target. A
  transient bd hiccup degrades gracefully.

> [!CAUTION]
> Do **not** render memory bodies with `html=True` or bypass the `md` filter —
> bodies are authored content an agent may not have written; the `md` shim
> escapes raw HTML (`html=False`) to keep `<script>` out of the page (XSS on the
> very surface that feeds agent context). And don't re-implement the memory
> search filter client-side — the single source of truth is `bd memories <term>
> --json`. See [Endpoint: Memory API](./Endpoints/memory-api.md).

---

## 8. SSE / live-status problems

### 8.1 The live dot looks stalled behind a proxy / nginx

- **Likely cause:** the SSE response is being buffered, or cached.
- **Fix / expected behaviour:** the handler sets `Cache-Control: no-cache` (an
  SSE stream must never be cached) and `X-Accel-Buffering: no` (tells nginx not
  to buffer). Without the latter a proxied deployment can sit on events for
  seconds. See [Endpoint: SSE events](./Endpoints/sse-events.md).

### 8.2 The pill shows `reconnecting…`

- **Likely cause / expected behaviour:** the SSE socket dropped (server side).
  `EventSource`'s built-in exponential-backoff reconnect heals it. Contrast with
  §1.1 (`live · push` with no update = the watcher/refresh half is the suspect).
  Isolate the broadcast half with `curl -N http://127.0.0.1:7332/api/events` —
  you should see a `bootstrap` frame, a `beads_changed` line per change, and a
  `: heartbeat` every 15 s.

### 8.3 A slow tab missed an event

- **Likely cause / expected behaviour:** intentional. Events are
  **fire-and-forget and lossy by design** — each subscriber's bounded
  (`_QUEUE_SIZE = 16`) queue drops its oldest event on overflow so a slow tab
  can never back-pressure the watcher. Never build client logic that assumes it
  sees *every* `beads_changed` or a gap-free timestamp sequence; react by
  re-fetching whole regions, never by applying a delta.

### 8.4 `curl`-ing `/api/events` never returns

- **Likely cause / expected behaviour:** the stream **never terminates on its
  own** — `curl` hangs open by design until Ctrl-C or the server stops. Use
  `curl -N` to watch frames live. `EventBus.subscriber_count` is exposed for
  diagnostics (one per open tab).

> [!CAUTION]
> Do **not** widen `/api/events` to push bead *data* (lane HTML, JSON diffs)
> down the stream. It is a content-free `beads_changed` doorbell; the
> authoritative render always comes from a fresh partial fetch through the
> derive layer. Smuggling data through the event creates a second, divergent
> render path and defeats the single-source-of-truth posture (`bdboard-0yy`).

---

## 9. Endpoints behave oddly under `curl`

### 9.1 An endpoint returns bare markup with no `<html>` wrapper

- **Likely cause / expected behaviour:** intentional. The region endpoints
  ([`/api/lanes`, `/api/counts`, `/api/lanes/closed`](./Endpoints/lanes-api.md),
  [`/api/history`](./Endpoints/history-api.md),
  [`/api/memory`](./Endpoints/memory-api.md), and the
  [bead detail](./Endpoints/bead-detail-api.md) /
  [field-edit](./Endpoints/bead-field-edit-api.md) partials) return HTML
  **fragments** meant to be swapped into an existing DOM by HTMX — never full
  pages, never JSON. There is no content negotiation. For raw JSON read the bd
  CLI directly (`bd list --json`).

### 9.2 `/api/bead/{id}/raw` shape changed between bd versions

- **Likely cause / expected behaviour:** `/raw` is a **debug aid, not a stable
  API** — it returns whatever `bd show --long --json` currently emits. Don't
  build client code against it; consume the curated modal partial or the typed
  `BdClient` methods. It exists so a maintainer can see fields the modal hides.

### 9.3 The bead detail modal feels like it loads in two steps

- **Likely cause / expected behaviour:** intentional. `/api/bead/{id}` paints
  fast (one `bd show`, never blocks on history); the slower `bd history` read is
  deferred to `/audit`, fetched via `hx-trigger="load"` once the shell is on
  screen. One user action, two sequential fetches, two render targets — the
  modal is never a frozen click. The lifecycle timeline and audit trail share
  **one** `bd history` subprocess (single-writer Dolt gate). Only the "missing
  bead" case is a real `404`; every other failure degrades to `200` with a
  friendly partial.

---

## See also

- [Architecture](./Architecture.md) — the big picture and tech stack.
- [Manifest](./_Manifest.md) — index of every documented item.
- [Concept: bd CLI as runtime source of truth](./Concepts/bd-cli-source-of-truth.md)
- [Concept: Store snapshot cache & change detection](./Concepts/store-snapshot-cache.md)
- [Concept: Derive layer](./Concepts/derive-layer.md)
- [Concept: Watcher debounce/cooldown & self-feedback skip](./Concepts/watcher-scheduling.md)
- [Concept: HTMX + server-rendered partials](./Concepts/htmx-partials-architecture.md)