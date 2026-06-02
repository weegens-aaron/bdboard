"""In-memory cache of bead snapshots with change detection.

bdboard is read-mostly: every /api/lanes, /api/counts, and / render
needs the bead list. Re-fetching via subprocess on every request
would burn ~700ms per HTTP call and pile up against the bd dolt
single-writer lock. Instead, Store keeps the last-known good list in
memory and only re-fetches when the watcher in app.py reports that
.beads/ changed.

Snapshot contents (bdboard-zdz, bdboard-0yy, bdboard-p8v):
The Store maintains THREE caches:
  1. Active snapshot: open, in_progress, blocked, deferred issues (~5KB)
  2. Board-closed snapshot: closed issues bounded by the board's date
     window (BOARD_CLOSED_WINDOW_DAYS). Powers the Closed lane AND the
     header CLOSED KPI so the two numbers agree.
  3. History-closed snapshot: the closed record for the long-window History
     page. Never *count*-capped (anything older than a static cap would be
     unreachable, bdboard-a194) but *window*-bounded: the active range /
     custom-date lower bound is pushed down to the bd query via
     --closed-after so a narrow range fetches only its beads instead of
     slurping the whole closed table (bdboard-gp06). The 'all' range stays a
     genuine full-table read by design. The cache is window-aware — a wider
     cached window already covers any narrower sub-window.

This split enables lazy-loading of the closed lane (bdboard-0yy):
  - First paint: /api/lanes fetches active-only (~5KB, fast)
  - Background: /api/lanes/closed loads after initial render

The masthead CLOSED count and the Closed lane both reflect the same
date-bounded board set; the History page surfaces older closed work.

Access patterns:

  * snapshot_active() — active issues only. Fast path for initial paint.
    Lazy-loads on first call. ~5KB typical payload.

  * snapshot_closed() — board-closed issues only (date-bounded). Background
    load for the Closed lane. Lazy-loads on first call.

  * snapshot() — active + board-closed issues. Powers the header counts and
    the cached bead-lookup fallback. Lazy-loads on first call.

  * snapshot_history(closed_after) — active + history-closed issues bounded
    by the active range/custom-date lower bound. For the History page only.
    Lazy-loads (and re-queries on an uncovered, wider window) on first call.

  * refresh() — what the watcher calls. Pulls fresh data for ALL caches,
    compares against previous, returns True iff something changed.
    Drives broadcast dedup.

Why structural equality (==):
bd list --json returns a deterministically-sorted list of dicts.
Python's == compares lists/dicts structurally, so prev == new directly
answers "did any issue field change". O(n) and cheap for expected
workspace sizes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bdboard.bd import BdClient

log = logging.getLogger(__name__)


@dataclass
class _Snapshot:
    beads: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]  # pre-indexed for O(1) bead(id) lookups


class Store:
    """Caches the bead list. Refreshed by the watcher; read by HTTP routes."""

    def __init__(self, bd: BdClient) -> None:
        self.bd = bd
        self._active_snap: _Snapshot | None = None
        self._closed_snap: _Snapshot | None = None
        self._history_snap: _Snapshot | None = None
        # The closed_at lower bound the cached history snapshot was fetched
        # with (None == unbounded "all" fetch). Tracked so the window-aware
        # cache can answer "does the cached set already cover this narrower
        # request?" without re-querying bd (bdboard-gp06).
        self._history_cutoff: datetime | None = None
        # Last dolt revision signature (manifest root hashes) we refreshed at.
        # Lets refresh() skip the expensive `bd list` when the watcher fired
        # only because our OWN read jiggled the noms/ files (bdboard-ywep).
        self._last_revision: frozenset[tuple[str, bytes]] | None = None
        # Serializes refresh() so a burst of watcher events (or a watcher
        # event landing concurrently with a lazy snapshot load) results in
        # exactly one bd list call — not N parallel ones piling up against
        # bd's dolt lock.
        self._refresh_lock = asyncio.Lock()

    async def snapshot_active(self) -> list[dict[str, Any]]:
        """Return active issues only. Fast path for initial paint (~5KB).

        Lazy-loads via bd.list_active() on first call. Subsequent calls
        return the in-memory cache. This is the hot path for /api/lanes.
        """
        if self._active_snap is None:
            await self._load_active()
        return self._active_snap.beads if self._active_snap else []

    async def snapshot_closed(self) -> list[dict[str, Any]]:
        """Return closed issues only. Background load for closed lane.

        Lazy-loads via bd.list_closed() on first call. Subsequent calls
        return the in-memory cache. This is the background path for
        /api/lanes/closed.
        """
        if self._closed_snap is None:
            await self._load_closed()
        return self._closed_snap.beads if self._closed_snap else []

    async def snapshot(self) -> list[dict[str, Any]]:
        """Return all issues (active + closed). For full-data needs.

        Lazy-loads both caches on first call. Used by History page and
        SSE refresh. Subsequent calls return the in-memory cache.
        """
        if self._active_snap is None or self._closed_snap is None:
            await self.refresh()
        active = self._active_snap.beads if self._active_snap else []
        closed = self._closed_snap.beads if self._closed_snap else []
        return active + closed

    async def snapshot_history(self, closed_after: datetime | None = None) -> list[dict[str, Any]]:
        """Return active + history-closed issues, bounded by ``closed_after``.

        For the History page only. The History page is a long-window
        retrospective surface (7d/30d/90d/All), so it is NOT count-capped
        (anything older than a static cap would be unreachable, bdboard-a194).
        It IS, however, bounded by the active filter *window*: ``closed_after``
        (the range / custom-date lower bound resolved by the route) is pushed
        down to the bd query via ``--closed-after`` so a narrow range fetches
        only the beads closed inside it instead of slurping every closed bead
        into memory on every snapshot (bdboard-gp06). ``closed_after=None`` is
        the unbounded ``all`` view and stays a genuine full-table read by
        design.

        The history cache is window-aware: a cached snapshot fetched with a
        lower (or absent) bound already covers any narrower sub-window, so we
        only re-query bd when the request reaches further back than what we
        hold (:meth:`_history_covers`). Lazy-loads the active cache and the
        history-closed cache on the first/uncovered call.
        """
        if self._active_snap is None:
            await self._load_active()
        if not self._history_covers(closed_after):
            await self._load_history(closed_after)
        active = self._active_snap.beads if self._active_snap else []
        history = self._history_snap.beads if self._history_snap else []
        return active + history

    def _history_covers(self, requested_cutoff: datetime | None) -> bool:
        """Does the cached history snapshot already cover ``requested_cutoff``?

        The cache was fetched with ``--closed-after self._history_cutoff``
        (None == unbounded). A request for closed-after ``requested_cutoff``
        is satisfiable from cache iff the cache reaches at least as far back:

          * an unbounded cache (cutoff None) covers any request;
          * a bounded cache covers a request only when the request also has a
            lower bound AND that bound is no earlier than the cache's
            (``self._history_cutoff <= requested_cutoff``) — i.e. the request
            is a sub-window of what we already hold;
          * an unbounded request (None) is NOT covered by a bounded cache.

        Returns False when nothing is cached yet. The in-memory derive layer
        re-applies the exact bounds, so serving a wider superset is correct
        — it just avoids a redundant bd query (bdboard-gp06).
        """
        if self._history_snap is None:
            return False
        if self._history_cutoff is None:
            return True
        if requested_cutoff is None:
            return False
        return self._history_cutoff <= requested_cutoff

    async def _load_active(self) -> None:
        """Load active issues into cache. Called on first snapshot_active()."""
        async with self._refresh_lock:
            if self._active_snap is not None:
                return  # another coroutine loaded while we waited
            try:
                fresh = await self.bd.list_active()
            except Exception:
                log.exception("store: bd list_active failed; active cache stays empty")
                return
            self._active_snap = _Snapshot(
                beads=fresh,
                by_id={b["id"]: b for b in fresh if isinstance(b.get("id"), str)},
            )

    async def _load_closed(self) -> None:
        """Load closed issues into cache. Called on first snapshot_closed()."""
        async with self._refresh_lock:
            if self._closed_snap is not None:
                return  # another coroutine loaded while we waited
            try:
                fresh = await self.bd.list_closed()
            except Exception:
                log.exception("store: bd list_closed failed; closed cache stays empty")
                return
            self._closed_snap = _Snapshot(
                beads=fresh,
                by_id={b["id"]: b for b in fresh if isinstance(b.get("id"), str)},
            )

    async def _load_history(self, closed_after: datetime | None = None) -> None:
        """Load history-closed issues into cache, bounded by ``closed_after``.

        Called on the first snapshot_history() or whenever the request reaches
        further back than the cached window. The fetch is never *count*-capped
        (anything older than a static cap would be unreachable, bdboard-a194)
        but IS *window*-bounded: ``closed_after`` pushes the active range's
        lower bound down to the bd query so a narrow range fetches only its
        beads rather than the whole closed table (bdboard-gp06). Records the
        cutoff the snapshot was fetched with so :meth:`_history_covers` can
        reuse it for narrower sub-windows."""
        async with self._refresh_lock:
            if self._history_covers(closed_after):
                return  # another coroutine loaded a covering window while we waited
            try:
                fresh = await self.bd.list_closed_history(closed_after=closed_after)
            except Exception:
                log.exception("store: bd list_closed_history failed; history cache stays empty")
                return
            self._history_snap = _Snapshot(
                beads=fresh,
                by_id={b["id"]: b for b in fresh if isinstance(b.get("id"), str)},
            )
            self._history_cutoff = closed_after

    async def refresh(self) -> bool:
        """Re-fetch from bd and update both caches. Returns True iff the
        bead list actually changed (drives the SSE broadcast dedup).

        On bd-list failure, leaves the existing cache in place — better
        to serve stale data than to flash empty on a transient bd hiccup.

        Self-feedback skip (bdboard-ywep): a read-only `bd list` itself
        mutates the watched noms/ dir, so the watcher fires for our own read
        and calls us again. We compare the dolt manifest root-hash signature
        against the last one we refreshed at; if it is unchanged (and we
        already hold a populated cache) the database content cannot have
        changed, so we skip the subprocess entirely and report "no change".
        This is what stops the refresh→read→event→refresh loop from spinning
        forever and starving real updates. An EMPTY signature means "no
        dolt signal available" (legacy JSONL-only workspace) — we never skip
        in that case so behavior is unchanged there.
        """
        async with self._refresh_lock:
            revision = self.bd.revision_signature()
            already_loaded = self._active_snap is not None and self._closed_snap is not None
            if revision and already_loaded and revision == self._last_revision:
                # Watcher fired but the committed dolt state is byte-identical
                # to our last refresh — this is our own read echoing back, or
                # unrelated FS churn. Skip the subprocess; nothing changed.
                return False
            try:
                fresh_active = await self.bd.list_active()
                fresh_closed = await self.bd.list_closed()
            except Exception:
                # We're noisy here on purpose: an empty dashboard with no
                # explanation is worse than a log line the operator can
                # grep for. Cache is preserved by NOT mutating snapshots.
                log.exception("store: bd list failed; keeping previous snapshot")
                return False

            prev_active = self._active_snap.beads if self._active_snap else None
            prev_closed = self._closed_snap.beads if self._closed_snap else None

            active_changed = prev_active is None or prev_active != fresh_active
            closed_changed = prev_closed is None or prev_closed != fresh_closed

            if not active_changed and not closed_changed:
                # Watcher fired but no issue state changed (e.g. dolt
                # internal write, or memory-only `bd remember`). No
                # broadcast needed. Still record the revision so the next
                # identical-state event can take the cheap skip path above.
                self._last_revision = revision
                return False

            if active_changed:
                self._active_snap = _Snapshot(
                    beads=fresh_active,
                    by_id={b["id"]: b for b in fresh_active if isinstance(b.get("id"), str)},
                )
            if closed_changed:
                self._closed_snap = _Snapshot(
                    beads=fresh_closed,
                    by_id={b["id"]: b for b in fresh_closed if isinstance(b.get("id"), str)},
                )

            # The History page's closed cache is a separate, window-bounded
            # data path (bdboard-p8v, bdboard-gp06). Only refresh it if it was
            # already lazy-loaded — no point paying for a long-window fetch
            # nobody has asked for yet — and re-fetch with the SAME cutoff the
            # cache currently holds so the refreshed set stays the same window
            # the page is viewing (not silently widened to unbounded).
            if self._history_snap is not None:
                try:
                    fresh_history = await self.bd.list_closed_history(
                        closed_after=self._history_cutoff
                    )
                except Exception:
                    log.exception("store: bd list_closed_history failed; keeping previous history")
                else:
                    if self._history_snap.beads != fresh_history:
                        self._history_snap = _Snapshot(
                            beads=fresh_history,
                            by_id={
                                b["id"]: b for b in fresh_history if isinstance(b.get("id"), str)
                            },
                        )

            # Bead-detail caches are now stale wrt the new world. Drop
            # them so the next modal click hits fresh bd show / bd history
            # output instead of serving cached pre-mutation values.
            self.bd.invalidate_caches()
            self._last_revision = revision
            return True

    def bead(self, bead_id: str) -> dict[str, Any] | None:
        """Find a single bead in the cached snapshot by id. Sync because
        callers (the bead modal fallback path) are already inside an async
        handler that has awaited snapshot() upstream."""
        # Check active first (more common), then closed
        if self._active_snap is not None:
            bead = self._active_snap.by_id.get(bead_id)
            if bead is not None:
                return bead
        if self._closed_snap is not None:
            return self._closed_snap.by_id.get(bead_id)
        return None
