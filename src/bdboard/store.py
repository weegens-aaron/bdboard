"""In-memory cache of `bd list --all --json` output with change detection.

bdboard is read-mostly: every /api/lanes, /api/counts, and / render
needs the full bead list. Re-fetching via subprocess on every request
would burn ~700ms per HTTP call and pile up against the bd dolt
single-writer lock. Instead, Store keeps the last-known good list in
memory and only re-fetches when the watcher in app.py reports that
.beads/ changed.

Two access patterns:

  * snapshot() — what HTTP handlers call. Returns the cached list,
    lazy-loading it on first call. Async because the lazy-load goes
    through bd.list_all(). Never blocks past the first call (~700ms
    cold; ~5µs warm).

  * refresh() — what the watcher calls. Pulls fresh data, compares
    against the cached list, returns True iff something actually
    changed. Drives broadcast dedup so a dolt-internal write that
    leaves issue state unchanged (e.g. a `bd remember` adding a
    memory) doesn't spam SSE.

Why structural equality (==) instead of sorted-line sha256:
bd list --json returns a deterministically-sorted list of dicts.
Python's == compares lists/dicts structurally, so prev == new is
exactly the question "did any issue field change". O(n) but n is
tiny (~50 beads on this workspace; would still be cheap at 10k).
The old sorted-line hash was a workaround for the JSONL exporter's
non-deterministic ordering, which we no longer touch.
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
        self._snap: _Snapshot | None = None
        # Serializes refresh() so a burst of watcher events (or a watcher
        # event landing concurrently with a lazy snapshot load) results in
        # exactly one bd list call — not N parallel ones piling up against
        # bd's dolt lock.
        self._refresh_lock = asyncio.Lock()

    async def snapshot(self) -> list[dict[str, Any]]:
        """Return the current bead list. Lazy-loads via bd list --json on
        first call. Subsequent calls return the in-memory cache."""
        if self._snap is None:
            await self.refresh()
        return self._snap.beads if self._snap else []

    async def refresh(self) -> bool:
        """Re-fetch from bd and update the cache. Returns True iff the
        bead list actually changed (drives the SSE broadcast dedup).

        On bd-list failure, leaves the existing cache in place — better
        to serve stale data than to flash empty on a transient bd hiccup.
        """
        async with self._refresh_lock:
            try:
                fresh = await self.bd.list_all()
            except Exception:
                # We're noisy here on purpose: an empty dashboard with no
                # explanation is worse than a log line the operator can
                # grep for. Cache is preserved by NOT mutating self._snap.
                log.exception("store: bd list --json failed; keeping previous snapshot")
                return False

            prev_beads = self._snap.beads if self._snap else None
            if prev_beads is not None and prev_beads == fresh:
                # Watcher fired but no issue state changed (e.g. dolt
                # internal write, or memory-only `bd remember`). No
                # broadcast needed.
                return False

            self._snap = _Snapshot(
                beads=fresh,
                by_id={b["id"]: b for b in fresh if isinstance(b.get("id"), str)},
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
        if self._snap is None:
            return None
        return self._snap.by_id.get(bead_id)
