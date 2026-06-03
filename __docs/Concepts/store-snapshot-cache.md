# Concept: Store snapshot cache & change detection

## What is it

The **Store** ([`src/bdboard/store.py`](../../src/bdboard/store.py)) is
bdboard's in-memory cache of the bead list: it holds the last-known-good output
of `bd list --json` so that HTTP routes read from RAM instead of spawning a
`bd` subprocess per request, and it owns the **change-detection** logic that
decides — on each watcher tick — whether anything actually changed and a
[live-refresh broadcast](../Flows/live-refresh-pipeline.md) is warranted.

## Why this approach

bdboard is *read-mostly*: every board render, every `/api/lanes`, `/api/counts`,
and bead-modal fallback needs the bead list. Going back to `bd list --json` on
every one of those would be ruinous on two axes:

- **Latency.** A `bd list` round-trip is ~700 ms on a real workspace. Paying
  that per HTTP request makes the board feel broken.
- **Lock contention.** `bd` writes through dolt's *single-writer* lock; piling
  N concurrent read subprocesses against it serializes everything and starves
  the writer that actually mutates state.

So the Store keeps the list in memory and only re-fetches when the
[watcher](watcher-scheduling.md) reports that `.beads/` changed — turning the
common case (read) into a dict lookup and reserving the expensive subprocess
for the rare case (write).

Two further design pressures shaped it into **three** caches rather than one:

- **Lazy-load the closed lane (bdboard-0yy).** The active set is ~5 KB; the
  full closed table can be ~500 KB. First paint fetches active-only and fast;
  the Closed lane loads in the background. So active and board-closed are
  *separate* caches with independent lazy-load.
- **History is a different shape (bdboard-p8v, bdboard-a194, bdboard-gp06).**
  The History page is a long-window retrospective. It must NOT be count-capped
  (anything older than a static cap would be permanently unreachable —
  bdboard-a194) but it MUST be *window*-bounded so a narrow range doesn't slurp
  the whole closed table into memory on every snapshot (bdboard-gp06). That is
  a third, window-aware cache.

Rejected alternatives: a single all-issues cache (couples the fast active path
to the slow closed slurp and kills lazy-loading); a fixed-size LRU keyed on
query (the bead universe is small and fully refetched on change, so structural
caching is simpler and exact); and periodic polling instead of watcher-driven
refresh (wastes `bd` invocations and adds latency — see the anti-patterns in [HTMX + server-rendered partials](htmx-partials-architecture.md)).

For change detection the Store relies on **structural equality** (`==`):
`bd list --json` returns a deterministically-sorted list of dicts, so
`prev == new` directly answers "did any issue field change?" in O(n) — cheap at
expected workspace sizes and exact (no hashing, no diff bookkeeping).

## How it works

The Store holds three `_Snapshot` records (each a `beads` list plus a pre-built
`by_id` index for O(1) `bead(id)` lookups), the dolt revision signature it last
refreshed at, the lower-bound cutoff its history snapshot was fetched with, and
an `asyncio.Lock` that serializes refreshes so a burst of watcher events
collapses into exactly one `bd list` rather than N parallel ones piling against
the dolt lock.

`refresh()` is the heart of change detection, and it does three things in
order: **(1)** take the cheap self-feedback skip when the committed dolt state
is byte-identical to last time, **(2)** re-fetch and structurally diff each
cache, **(3)** return `True` *only* if the bead list actually changed — which is
what de-dups the SSE broadcast.

The self-feedback skip is the subtle part. `refresh()` itself runs
`bd list --json`, and even a read-only `bd list` makes dolt re-touch the watched
`noms/` files — so the watcher fires for *our own read* and calls `refresh()`
again. To break that loop the Store compares
[`Bd.revision_signature()`](../../src/bdboard/bd.py) (the dolt manifest root
hash — content that flips IFF the database really changed) against the last
signature it refreshed at; if it is unchanged (and a populated cache already
exists) the content cannot have changed, so the subprocess is skipped and "no
change" is reported. An **empty** signature means "no dolt signal" (legacy
JSONL-only workspace) and is deliberately treated as "always refresh", never
"never refresh".

```python
# The change-detection core of Store.refresh() (src/bdboard/store.py, abridged).
async with self._refresh_lock:                       # one bd list per burst
    revision = self.bd.revision_signature()          # dolt manifest root hash
    already_loaded = self._active_snap is not None and self._closed_snap is not None
    if revision and already_loaded and revision == self._last_revision:
        return False                                 # our own read echoed back → skip

    fresh_active = await self.bd.list_active()        # the expensive part
    fresh_closed = await self.bd.list_closed()

    active_changed = prev_active is None or prev_active != fresh_active   # structural ==
    closed_changed = prev_closed is None or prev_closed != fresh_closed
    if not active_changed and not closed_changed:
        self._last_revision = revision               # record so next event takes skip path
        return False                                 # dolt-internal / memory-only write

    # ... swap in only the snapshots that changed, drop bead-detail caches ...
    self.bd.invalidate_caches()
    self._last_revision = revision
    return True                                      # gates the SSE broadcast
```

The History cache adds a **window-aware** wrinkle: a cached snapshot fetched
with a lower (or absent) bound already covers any narrower sub-window, so
`snapshot_history(closed_after)` only re-queries `bd` when the request reaches
further back than what is held (`_history_covers`). On `refresh()`, the history
cache is re-fetched only if it was already lazy-loaded, and with the *same*
cutoff it currently holds — so a watcher tick never silently widens the window
the page is viewing.

```mermaid
flowchart TD
    W["watcher fires Store.refresh()"] --> Sig{"revision_signature()<br/>== last && cache loaded?"}
    Sig -->|yes (own read echo)| Skip["skip bd list → return False"]
    Sig -->|no / empty sig| Fetch["bd list_active + list_closed"]
    Fetch --> Diff{"prev == fresh<br/>(structural ==)?"}
    Diff -->|equal| Rec["record revision → return False<br/>(no broadcast)"]
    Diff -->|differs| Swap["swap changed snapshots<br/>invalidate bd detail caches<br/>re-fetch history at same cutoff"]
    Swap --> True["record revision → return True<br/>(SSE broadcast fires)"]

    R1["/api/lanes"] --> SA["snapshot_active() (lazy, ~5KB)"]
    R2["/api/lanes/closed"] --> SC["snapshot_closed() (lazy, bg)"]
    R3["/history"] --> SH["snapshot_history(cutoff) (window-aware)"]
    R4["bead modal fallback"] --> SB["snapshot() + bead(id) O(1)"]
```

## Where used

| Consumer | How |
| --- | --- |
| [`app.py:_get_lanes`](../../src/bdboard/app.py) (`/api/lanes`) | `await store.snapshot_active()` — fast active-only path for first paint |
| [`app.py` closed lane](../../src/bdboard/app.py) (`/api/lanes/closed`) | `await store.snapshot_closed()` — background lazy-load of the Closed lane |
| [`app.py` history page](../../src/bdboard/app.py) (`/history`) | `await store.snapshot_history(closed_after=cutoff)` — window-bounded retrospective |
| [`app.py` counts / modal fallback](../../src/bdboard/app.py) | `await store.snapshot()` then `store.bead(id)` — full set + O(1) lookup when a live `bd show` fails |
| [`app.py:_watch_beads`](../../src/bdboard/app.py) | wires `store.refresh` as the [`RefreshScheduler`](watcher-scheduling.md)'s `refresh` callable; its `True`/`False` return gates the broadcast |
| [`app.py` field-edit write path](../../src/bdboard/app.py) | `await store.refresh()` *before* broadcasting so the acting tab's HTMX re-fetch sees post-mutation state |
| [`BdClient.revision_signature`](../../src/bdboard/bd.py) | supplies the manifest-root-hash fingerprint that powers the self-feedback skip |
| [`BdClient.invalidate_caches`](../../src/bdboard/bd.py) | called on a real change so stale `bd show`/`bd history` detail caches are dropped |
| [`derive.lanes` / `derive.history`](../../src/bdboard/derive/) | pure shaping over whatever the snapshot returns — the cache feeds the [derive layer](derive-layer.md), it does not shape data itself |

## Conventions

> [!IMPORTANT]
> When touching the Store, preserve these invariants:
> - **Refresh under `_refresh_lock`.** Every fetch path (`refresh`,
>   `_load_active`, `_load_closed`, `_load_history`) takes the lock and
>   re-checks its precondition after acquiring it (another coroutine may have
>   loaded while it waited). This collapses a watcher burst into one `bd list`
>   and avoids piling reads against the dolt single-writer lock.
> - **Diff structurally, return `True` only on a real change.** The SSE
>   broadcast de-dups on `refresh()`'s boolean. A dolt-internal write or a
>   memory-only `bd remember` must record the new revision but return `False`
>   (no broadcast).
> - **Record the revision even when nothing changed.** Storing
>   `self._last_revision = revision` on a no-op refresh is what lets the *next*
>   identical-state event take the cheap skip path. Forgetting it re-opens the
>   feedback loop.
> - **Treat an empty `revision_signature()` as "always refresh".** A legacy
>   JSONL-only workspace has no dolt manifest; "no signal" must never mean
>   "never refresh".
> - **On `bd list` failure, keep the previous snapshot.** Serving slightly
>   stale data beats flashing an empty board on a transient `bd` hiccup —
>   never null out a populated cache in the error path; log loudly instead.
> - **Re-fetch History at its current cutoff, only if already loaded.** Don't
>   pay for a long-window fetch nobody asked for, and never silently widen the
>   window the page is viewing to unbounded.
> - **Keep the `by_id` index in lock-step with `beads`.** Both are rebuilt
>   together whenever a snapshot is swapped so `bead(id)` can stay sync and O(1).

## Anti-patterns

> [!CAUTION]
> Mistakes that re-break the cache or live-sync — don't do these:
> - **Don't fetch `bd list` per HTTP request.** That's the ~700 ms-per-call,
>   dolt-lock-contending regression the Store exists to prevent. Read from the
>   cache; let the watcher refresh it.
> - **Don't compare manifest mtime/inode for the skip.** A read-only `bd list`
>   bumps both; only the manifest *content* (root hash) distinguishes a real
>   write from our own read echo. Compare bytes, not metadata.
> - **Don't advance `_last_revision` after a *failed* fetch.** Recording a
>   revision you never actually synced lets the next real event get swallowed
>   by the skip path.
> - **Don't broadcast on every refresh.** Returning `True` unconditionally
>   re-renders the board on dolt-internal churn and our own read echoes,
>   defeating the de-dup and hammering connected browsers.
> - **Don't collapse the three caches into one.** A single all-issues cache
>   couples the fast ~5 KB active path to the ~500 KB closed slurp and kills
>   lazy-loading of the Closed lane (bdboard-0yy).
> - **Don't count-cap the History cache.** A static "last N closed" cap makes
>   everything older permanently unreachable (bdboard-a194). Bound by *window*
>   (`closed_after`), not by count.
> - **Don't widen the History window on a watcher refresh.** Re-fetch with the
>   cutoff the cache holds; silently promoting it to unbounded slurps the whole
>   closed table behind the user's back (bdboard-gp06).
> - **Don't poll on a timer for freshness.** The watcher + signature-gated
>   refresh + SSE pipeline already delivers sub-second updates; an
>   `hx-trigger="every Ns"` would hammer `bd` for nothing (see the
>   [HTMX partials](htmx-partials-architecture.md) anti-patterns).

## Related

- [Concept: Watcher debounce/cooldown & self-feedback skip](watcher-scheduling.md)
- [Concept: bd CLI as runtime source of truth](bd-cli-source-of-truth.md)
- [Concept: Derive layer (pure view shaping)](derive-layer.md)
- [Concept: HTMX + server-rendered partials](htmx-partials-architecture.md)
- [Flow: Live-refresh pipeline](../Flows/live-refresh-pipeline.md)
- [Flow: Inline field-edit write path](../Flows/field-edit-write-path.md)
- [Endpoint: Lanes API (/api/lanes, /api/lanes/closed, /api/counts)](../Endpoints/lanes-api.md)
- [Endpoint: History API (/api/history)](../Endpoints/history-api.md)
- [Feature: Live auto-refresh](../Features/live-auto-refresh.md)
- [Architecture](../Architecture.md)
- Source: [`src/bdboard/store.py`](../../src/bdboard/store.py),
  [`src/bdboard/bd.py`](../../src/bdboard/bd.py),
  [`src/bdboard/app.py`](../../src/bdboard/app.py)
- Tests: [`tests/test_watcher_self_feedback.py`](../../tests/test_watcher_self_feedback.py)
  (revision-signature skip + change detection),
  [`tests/test_store_history_window.py`](../../tests/test_store_history_window.py)
  (window-aware History cache)
