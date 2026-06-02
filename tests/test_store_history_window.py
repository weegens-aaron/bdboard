"""Store tests for the window-bounded History cache (bdboard-gp06).

The History page is count-uncapped but window-bounded: ``snapshot_history``
pushes the active range / custom-date lower bound down to the bd query via
``closed_after`` so a narrow range fetches only the beads closed inside it
rather than slurping the entire closed table into memory on every snapshot.
``closed_after=None`` (the 'all' range) stays a genuine unbounded fetch.

These tests pin:
  - a narrow range issues a BOUNDED query (closed_after forwarded to bd)
  - range=all issues an UNBOUNDED query (closed_after=None forwarded to bd)
  - the window-aware cache reuses a wider cached window for narrower
    sub-windows (no redundant re-query) but re-queries when the request
    reaches further back than what is cached
  - refresh() re-fetches the SAME cached window, not a silently-widened one

We stub the BdClient methods so no real bd subprocess runs and we can assert
the exact ``closed_after`` arguments the Store forwards.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from bdboard.store import Store

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


class _FakeBd:
    """Records the closed_after each list_closed_history call received."""

    def __init__(self, active: list[dict[str, Any]], closed: list[dict[str, Any]]) -> None:
        self._active = active
        self._closed = closed
        self.history_calls: list[datetime | None] = []
        self.active_calls = 0

    async def list_active(self) -> list[dict[str, Any]]:
        self.active_calls += 1
        return self._active

    async def list_closed(self) -> list[dict[str, Any]]:
        return self._closed

    async def list_closed_history(
        self, limit: int | None = None, closed_after: datetime | None = None
    ) -> list[dict[str, Any]]:
        self.history_calls.append(closed_after)
        if closed_after is None:
            return self._closed
        return [b for b in self._closed if _closed_at(b) >= closed_after]

    def invalidate_caches(self) -> None:  # pragma: no cover - refresh() calls it
        pass

    def revision_signature(self) -> frozenset[tuple[str, bytes]]:
        # Empty == "no dolt signal": Store never takes the skip path, so these
        # history-window tests exercise the full refresh/refetch behavior
        # exactly as before the bdboard-ywep loop-breaker landed.
        return frozenset()


def _closed_at(bead: dict[str, Any]) -> datetime:
    return datetime.strptime(bead["closed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _bead(bead_id: str, *, days_ago: int) -> dict[str, Any]:
    ts = (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": bead_id, "status": "closed", "closed_at": ts, "created_at": ts}


def _store(closed: list[dict[str, Any]]) -> tuple[Store, _FakeBd]:
    fake = _FakeBd(active=[], closed=closed)
    return Store(fake), fake  # type: ignore[arg-type]


def test_narrow_range_issues_bounded_query() -> None:
    closed = [_bead("recent", days_ago=2), _bead("old", days_ago=300)]
    store, fake = _store(closed)
    cutoff = NOW - timedelta(days=7)

    result = asyncio.run(store.snapshot_history(closed_after=cutoff))

    # The lower bound was pushed down to bd: the query was bounded, not a slurp.
    assert fake.history_calls == [cutoff]
    # And the fetch is actually narrowed to the in-window bead.
    assert {b["id"] for b in result} == {"recent"}


def test_all_range_issues_unbounded_query() -> None:
    closed = [_bead("recent", days_ago=2), _bead("old", days_ago=300)]
    store, fake = _store(closed)

    result = asyncio.run(store.snapshot_history(closed_after=None))

    # The 'all' range stays a genuine unbounded fetch by design.
    assert fake.history_calls == [None]
    assert {b["id"] for b in result} == {"recent", "old"}


def test_wider_cached_window_covers_narrower_subwindow() -> None:
    # An unbounded (all) fetch already holds everything, so a subsequent
    # narrow range is served from cache with NO redundant bd re-query.
    closed = [_bead("recent", days_ago=2), _bead("old", days_ago=300)]
    store, fake = _store(closed)

    asyncio.run(store.snapshot_history(closed_after=None))
    asyncio.run(store.snapshot_history(closed_after=NOW - timedelta(days=7)))

    # Only the first (unbounded) query hit bd; the narrow request reused it.
    assert fake.history_calls == [None]


def test_narrower_cache_requery_for_wider_window() -> None:
    # A bounded cache does NOT cover a request that reaches further back: a
    # wider window must re-query bd with the lower (or absent) bound.
    closed = [_bead("recent", days_ago=2), _bead("old", days_ago=300)]
    store, fake = _store(closed)
    narrow = NOW - timedelta(days=7)
    wider = NOW - timedelta(days=90)

    asyncio.run(store.snapshot_history(closed_after=narrow))
    asyncio.run(store.snapshot_history(closed_after=wider))
    # And 'all' (None) is wider than any bounded cache too.
    asyncio.run(store.snapshot_history(closed_after=None))

    assert fake.history_calls == [narrow, wider, None]


def test_refresh_refetches_same_cached_window() -> None:
    # refresh() (the watcher path) must re-fetch the SAME window the cache
    # currently holds, not silently widen it to unbounded.
    closed = [_bead("recent", days_ago=2), _bead("old", days_ago=300)]
    store, fake = _store(closed)
    cutoff = NOW - timedelta(days=7)

    asyncio.run(store.snapshot_history(closed_after=cutoff))
    asyncio.run(store.refresh())

    # First the lazy load (cutoff), then refresh re-uses the same cutoff.
    assert fake.history_calls == [cutoff, cutoff]
