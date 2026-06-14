"""Store tests for sustained-refresh-failure staleness tracking (bdboard-75rq).

The board serves the last-good snapshot when ``bd list`` fails
(serve-stale-on-failure). Previously a sustained outage was invisible: only a
log line. The Store now counts CONSECUTIVE refresh failures and exposes a
``staleness()`` value object so the UI can surface a stale banner once the
failures are clearly sustained — while a single transient hiccup stays below
threshold and never trips it.

These tests pin:
  - a fresh Store is not stale
  - a single failure does NOT mark the board stale (no banner flash)
  - STALE_FAILURE_THRESHOLD consecutive failures DO mark it stale
  - a successful refresh resets the streak (banner clears on recovery)
  - the revision-unchanged skip path counts as a healthy sync
  - last_success is stamped on a healthy sync and survives later failures

We stub the BdClient so no real bd subprocess runs and we can flip it between
healthy and failing at will.
"""

from __future__ import annotations

import asyncio
from typing import Any

from bdboard.store import STALE_FAILURE_THRESHOLD, Store


class _FakeBd:
    """A BdClient stub whose list calls can be made to fail on demand."""

    def __init__(self, beads: list[dict[str, Any]]) -> None:
        self._beads = beads
        self.fail = False
        # A non-empty, STABLE signature so refresh() can take the
        # revision-unchanged skip path once a cache is loaded (mirrors a quiet
        # dolt state). Tests that want the full refetch path flip `fail` first.
        self._signature: frozenset[tuple[str, bytes]] = frozenset({("root", b"v1")})

    async def list_active(self) -> list[dict[str, Any]]:
        if self.fail:
            raise RuntimeError("bd list_active boom")
        return [b for b in self._beads if b.get("status") != "closed"]

    async def list_closed(self) -> list[dict[str, Any]]:
        if self.fail:
            raise RuntimeError("bd list_closed boom")
        return [b for b in self._beads if b.get("status") == "closed"]

    def invalidate_caches(self) -> None:  # pragma: no cover - trivial
        pass

    def revision_signature(self) -> frozenset[tuple[str, bytes]]:
        return self._signature


def _store() -> tuple[Store, _FakeBd]:
    fake = _FakeBd([{"id": "a", "status": "open"}, {"id": "z", "status": "closed"}])
    return Store(fake), fake  # type: ignore[arg-type]


def test_fresh_store_is_not_stale() -> None:
    store, _ = _store()
    state = store.staleness()
    assert state.stale is False
    assert state.consecutive_failures == 0
    assert state.last_success is None


def test_single_failure_does_not_flash_banner() -> None:
    # A transient single failure must NOT mark the board stale (bdboard-75rq):
    # that would flash a banner on every routine dolt write hiccup.
    store, fake = _store()
    fake.fail = True

    asyncio.run(store.refresh())

    state = store.staleness()
    assert state.consecutive_failures == 1
    assert state.stale is False
    assert STALE_FAILURE_THRESHOLD > 1  # the guarantee that makes the above true


def test_sustained_failures_mark_stale() -> None:
    store, fake = _store()
    fake.fail = True

    for _ in range(STALE_FAILURE_THRESHOLD):
        asyncio.run(store.refresh())

    state = store.staleness()
    assert state.consecutive_failures == STALE_FAILURE_THRESHOLD
    assert state.stale is True


def test_successful_refresh_resets_streak() -> None:
    # Sustained failure -> stale; one healthy refresh clears it (banner drops).
    store, fake = _store()
    fake.fail = True
    for _ in range(STALE_FAILURE_THRESHOLD):
        asyncio.run(store.refresh())
    assert store.staleness().stale is True

    fake.fail = False
    asyncio.run(store.refresh())

    state = store.staleness()
    assert state.stale is False
    assert state.consecutive_failures == 0
    assert state.last_success is not None


def test_lazy_load_stamps_last_success() -> None:
    # A successful lazy snapshot load is a healthy sync and stamps last_success.
    store, _ = _store()
    asyncio.run(store.snapshot_active())

    state = store.staleness()
    assert state.consecutive_failures == 0
    assert state.last_success is not None


def test_revision_unchanged_skip_counts_as_healthy() -> None:
    # Once loaded with a stable signature, a watcher event that finds the dolt
    # revision unchanged skips the subprocess — but it DID confirm we are in
    # sync, so it must reset the failure streak and stamp last_success.
    store, fake = _store()
    # Prime both caches via a full refresh (records the revision).
    asyncio.run(store.refresh())
    # Manufacture a failure streak, then let the skip path heal it.
    store._mark_refresh_failure()
    store._mark_refresh_failure()
    assert store.staleness().consecutive_failures == 2

    # Same signature + already-loaded => skip path returns False but heals.
    changed = asyncio.run(store.refresh())
    assert changed is False
    state = store.staleness()
    assert state.consecutive_failures == 0
    assert state.last_success is not None
