# Concept: Watcher debounce/cooldown & self-feedback skip

## What is it

The **watcher scheduler** is the timing layer that turns the noisy stream of
filesystem events emitted while `bd` writes its dolt database into *exactly one*
`Store.refresh()` per logical mutation — and that refuses to chase its own tail
when a read-only `bd list` jiggles the very files it is watching. It is two
cooperating pieces: a debounce/cooldown coalescer
([`RefreshScheduler`](../../src/bdboard/watcher.py)) and a content-hash
**self-feedback skip** ([`Bd.revision_signature`](../../src/bdboard/bd.py) +
[`Store.refresh`](../../src/bdboard/store.py)).

## Why this approach

bdboard is a pure *observer* of dolt-native state: `bd` writes the dolt store,
files mutate under `.beads/embeddeddolt/<db>/.dolt/noms/`, `watchfiles` fires,
and the Store re-runs `bd list --json`. That naive loop has three failure modes,
each learned the hard way, that the scheduling design exists to defeat:

- **Write bursts (debounce).** A single `bd update` doesn't write one file — it
  rewrites `manifest`, `journal.idx`, a lock, and more inside the dolt `noms/`
  dir in quick succession, often spanning 2–3 `watchfiles` batches. Without a
  trailing quiet-window, one logical edit would trigger several `bd list`
  subprocesses. A **~250 ms debounce** is comfortably longer than the burst yet
  far below human perception.
- **Write storms (cooldown).** A `bd` mutation can fan out — dolt commit +
  auto-export + a git-add hook — into sustained FS activity. A **~1 s post-
  refresh cooldown** stops back-to-back refreshes from chain-firing at full
  filesystem speed.
- **Self-feedback (the subtle one).** `Store.refresh()` runs `bd list --json`,
  and *even a read-only* `bd list` makes dolt re-touch `journal.idx`/`manifest`
  inside the watched `noms/` dir — so the watcher fires for **our own read**
  ~1.3 s later. Naively, that re-trigger chains refreshes forever; worse,
  because `bd list` on a large `noms/` takes *longer* than the self-trigger
  latency, the old code cancelled each in-flight refresh before it finished and
  the board froze until relaunch (`bdboard-ywep`).

Rejected alternatives: a fixed periodic poll (wastes `bd` CLI invocations and
adds latency — see the anti-pattern in
[HTMX + server-rendered partials](htmx-partials-architecture.md)); a plain
debounce with no cooldown (lets storms chain-fire); and cancelling refreshes on
every event (the exact bug that wedged live-sync). The chosen design keeps
sub-second latency while making "one refresh per real change" an invariant.

## How it works

The scheduler runs a three-phase `_settle()` cycle per notification:

1. **Debounce sleep** (`debounce_s`) — collapses a multi-batch write burst.
2. **Cooldown remainder sleep** — if less than `cooldown_s` has elapsed since
   the last *successful* refresh, wait out only the remainder, then proceed.
   Critically, an event that lands inside cooldown is **not dropped** (the old
   `bdboard-xbc7` bug); it waits and refreshes, so trailing/isolated writes
   always sync.
3. **Refresh phase (non-cancellable)** — once `bd list` starts it runs to
   completion. A concurrent `notify()` during this phase does **not** cancel;
   it flips `_dirty` so the scheduler reconciles exactly once more afterward.

Two rules make it robust: the cooldown clock advances **only on a refresh that
succeeded** (a transient `bd list` error retries promptly instead of being
swallowed by an "earned" cooldown), and only the cancellable *sleep* phases may
be pre-empted by a newer event.

The self-feedback skip lives one layer down. `revision_signature()` reads each
dolt `manifest` (a ~150-byte file whose payload is the current **root hash**);
its content is identical across read-only churn and flips *only* on a real
write. `Store.refresh()` compares it to the last refreshed signature and skips
the `bd list` subprocess entirely when unchanged — severing the
refresh→read→event→refresh loop at the source.

```python
# Heart of the scheduler (src/bdboard/watcher.py, abridged).
async def _settle(self) -> None:
    try:
        await asyncio.sleep(self._debounce_s)          # 1. collapse the burst
        remaining = self._cooldown_s - (self._monotonic() - self._last_refresh_at)
        if remaining > 0:
            await asyncio.sleep(remaining)             # 2. wait out cooldown (don't drop!)
    except asyncio.CancelledError:
        return                                         # a newer event owns the next refresh

    self._refreshing = True                            # 3. refresh phase: NOT cancellable
    self._dirty = False
    try:
        changed = await self._refresh()                # runs `bd list --json`
    except Exception:
        log.exception("watcher: refresh raised; will retry on next change")
        return                                         # DON'T advance cooldown on failure
    finally:
        self._refreshing = False

    self._last_refresh_at = self._monotonic()          # only success advances the clock
    if changed:
        await self._broadcast()
    if self._dirty:                                    # an event overlapped the refresh
        self._pending = asyncio.create_task(self._settle())
```

```mermaid
flowchart TD
    FS["watchfiles batch"] --> N["scheduler.notify()"]
    N -->|refreshing?| D{"_refreshing"}
    D -->|yes| Dirty["set _dirty; return"]
    D -->|no| Cancel["cancel pending settle; start _settle"]
    Cancel --> Deb["sleep debounce_s"]
    Deb --> Cool["wait out cooldown remainder"]
    Cool --> Ref["refresh(): revision_signature unchanged?"]
    Ref -->|yes (own read echo)| Skip["skip bd list → return False"]
    Ref -->|no| List["bd list --json → diff snapshot"]
    List -->|changed| BC["broadcast beads_changed (SSE)"]
    List -->|no change| Done["record revision; no broadcast"]
    Skip --> ReDirty{"_dirty?"}
    BC --> ReDirty
    Done --> ReDirty
    ReDirty -->|yes| Cancel
    ReDirty -->|no| Idle["idle"]
```

## Where used

| Consumer | How |
| --- | --- |
| [`app.py:_watch_beads`](../../src/bdboard/app.py) | Constructs `RefreshScheduler(refresh=store.refresh, broadcast=…beads_changed, debounce_s=WATCHER_DEBOUNCE_S, cooldown_s=WATCHER_COOLDOWN_S)` and calls `scheduler.notify()` for every `awatch` batch |
| [`app.py` constants](../../src/bdboard/app.py) | `WATCHER_DEBOUNCE_S = 0.25`, `WATCHER_COOLDOWN_S = 1.0`, `WATCHER_RESCAN_S = 3.0` tune the timings |
| [`Store.refresh`](../../src/bdboard/store.py) | The `refresh` callable the scheduler drives; returns `True` iff the bead list changed (gates the broadcast) and applies the revision-signature skip |
| [`Bd.revision_signature`](../../src/bdboard/bd.py) | Content fingerprint (manifest root hash) that powers the self-feedback skip |
| [`Bd.watch_targets` / `watch_signature`](../../src/bdboard/bd.py) | Define *which* dirs are watched (non-recursive `noms/` dirs) and detect inode swaps / new dbs so `awatch` re-enumerates |
| [`EventBus.broadcast`](../../src/bdboard/events.py) | The `broadcast` callable; pushes `beads_changed` over SSE to connected browsers |

## Conventions

> [!IMPORTANT]
> When touching the watcher scheduling layer, preserve these invariants:
> - **Keep timing logic in `RefreshScheduler`, not `app.py`.** It was extracted
>   precisely so the tricky debounce/cooldown/self-trigger behavior is
>   unit-testable without FastAPI, `watchfiles`, or a real `bd` workspace
>   (`bdboard-xbc7`). Inject `monotonic`, `refresh`, and `broadcast` for tests.
> - **Advance the cooldown clock only after a *successful* refresh.** A refresh
>   that raises must leave `_last_refresh_at` untouched so the next event
>   retries promptly. This is what stops a transient `bd list` hiccup from
>   permanently wedging live-sync.
> - **Never cancel an in-flight refresh.** Only the cancellable debounce/cooldown
>   *sleep* may be pre-empted. While `_refreshing`, `notify()` sets `_dirty` and
>   the cycle reconciles once afterward — so a real write overlapping a refresh
>   is never lost, and the slow `bd list` subprocess can't be killed mid-flight.
> - **An event inside cooldown waits, it does not drop.** Trailing/isolated
>   writes (the last event of a burst, or a single `bd update`) must still
>   refresh within ~`debounce + cooldown`.
> - **Treat an empty `revision_signature()` as "always refresh."** A legacy
>   JSONL-only workspace has no dolt manifest; "no signal" must mean "don't
>   skip," never "never refresh."
> - **`refresh()` returns `True` only when the bead list actually changed.** The
>   SSE broadcast dedups on this; recording the revision without broadcasting is
>   correct for dolt-internal or memory-only writes.

## Anti-patterns

> [!CAUTION]
> Mistakes that re-break live-sync — don't do these:
> - **Don't cancel the refresh task on every event.** That was the original
>   `bdboard-ywep` defect: `bd list` itself touches `noms/`, so the watcher
>   fired for our own read and killed the refresh before it finished — on a
>   large `noms/` it *never* finished and the board froze until relaunch.
> - **Don't return early when an event lands inside cooldown.** The old
>   `_settle_task` skipped the refresh *and* scheduled no catch-up, assuming "a
>   later event will retrigger." The last event of a burst has no later event,
>   so that change was silently lost (`bdboard-xbc7` root cause #1).
> - **Don't advance the cooldown on failure.** Earning a cooldown without
>   actually syncing lets the next real event get swallowed (root cause #3).
> - **Don't watch `.beads/` recursively.** dolt's churning content-addressed
>   `noms/` store opens one kqueue fd per dir on macOS and exhausts
>   `RLIMIT_NOFILE`; once fds run out, `create_subprocess_exec` can't open
>   pipes and `bd list`/`bd show` crash with `OSError [Errno 24]`. Watch the
>   small fixed set of `noms/` dirs non-recursively (see `watch_targets`).
> - **Don't compare manifest mtime/inode for the skip.** Read-only churn bumps
>   both; only the manifest *content* (root hash) reliably distinguishes a real
>   write from our own read echo. Compare bytes, not metadata.
> - **Don't add a timer poll for live updates.** The debounce/cooldown +
>   SSE pipeline already delivers sub-second freshness; an `hx-trigger="every Ns"`
>   would hammer the `bd` CLI for nothing (see the
>   [HTMX partials](htmx-partials-architecture.md) anti-patterns).

## Related

- [Concept: Store snapshot cache & change detection](store-snapshot-cache.md)
- [Concept: bd CLI as runtime source of truth](bd-cli-source-of-truth.md)
- [Concept: Derive layer (pure view shaping)](derive-layer.md)
- [Concept: HTMX + server-rendered partials](htmx-partials-architecture.md)
- [Flow: Live-refresh pipeline](../Flows/live-refresh-pipeline.md)
- [Flow: Server startup & workspace resolution](../Flows/server-startup.md)
- [Endpoint: SSE events (/api/events)](../Endpoints/sse-events.md)
- [Feature: Live auto-refresh](../Features/live-auto-refresh.md)
- [Architecture](../Architecture.md)
- Source: [`src/bdboard/watcher.py`](../../src/bdboard/watcher.py),
  [`src/bdboard/bd.py`](../../src/bdboard/bd.py),
  [`src/bdboard/store.py`](../../src/bdboard/store.py),
  [`src/bdboard/app.py`](../../src/bdboard/app.py)
