"""In-memory cache of bead snapshots with change detection.

bdboard is read-mostly: every /api/lanes, /api/counts, and / render
needs the bead list. Re-fetching via subprocess on every request
would burn ~700ms per HTTP call and pile up against the bd dolt
single-writer lock. Instead, Store keeps the last-known good list in
memory and only re-fetches when the watcher in app.py reports that
.beads/ changed.

Snapshot contents (bdboard-zdz, bdboard-0yy):
The Store maintains TWO caches:
  1. Active snapshot: open, in_progress, blocked, deferred issues (~5KB)
  2. Closed snapshot: CLOSED_LANE_LIMIT most recently closed issues

This split enables lazy-loading of the closed lane (bdboard-0yy):
  - First paint: /api/lanes fetches active-only (~5KB, fast)
  - Background: /api/lanes/closed loads after initial render

The masthead closed count reflects the capped value; for accurate
totals see the History page or bd status.

Access patterns:

  * snapshot_active() — active issues only. Fast path for initial paint.
    Lazy-loads on first call. ~5KB typical payload.

  * snapshot_closed() — closed issues only. Background load for closed lane.
    Lazy-loads on first call. Capped at CLOSED_LANE_LIMIT.

  * snapshot() — all issues (active + closed). For History page and SSE
    refresh. Lazy-loads on first call by calling refresh().

  * refresh() — what the watcher calls. Pulls fresh data for BOTH caches,
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

    async def refresh(self) -> bool:
        """Re-fetch from bd and update both caches. Returns True iff the
        bead list actually changed (drives the SSE broadcast dedup).

        On bd-list failure, leaves the existing cache in place — better
        to serve stale data than to flash empty on a transient bd hiccup.
        """
        async with self._refresh_lock:
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
                # broadcast needed.
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

            # Bead-detail caches are now stale wrt the new world. Drop
            # them so the next modal click hits fresh bd show / bd history
            # output instead of serving cached pre-mutation values.
            self.bd.invalidate_caches()
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
