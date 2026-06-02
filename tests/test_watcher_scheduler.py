"""Regression tests for the live-sync refresh scheduler (bdboard-xbc7).

The Board page stopped reflecting bd writes that happened while it was open:
a single isolated ``bd update`` (or the trailing write of a burst) never
refreshed until a manual full-page reload. Root cause: the old
``_settle_task`` returned EARLY when its debounce timer fired inside the
post-refresh cooldown window — dropping the event WITHOUT scheduling a
catch-up. Compounded by a transient ``bd list`` failure still advancing the
cooldown clock, which then let the next real event get swallowed too.

These tests pin the fixed contract of ``RefreshScheduler``:

  * an event landing inside cooldown is NOT dropped — it waits out the
    remaining cooldown and then refreshes (the headline bug);
  * a burst collapses to a single refresh (debounce still works);
  * ``refresh()`` returning False (nothing changed) suppresses the
    broadcast;
  * a ``refresh()`` that RAISES does not advance the cooldown clock and the
    NEXT event still refreshes (transient failure can't wedge live-sync).

We use tiny debounce/cooldown values so the suite stays fast while still
exercising real asyncio timing.
"""

from __future__ import annotations

import asyncio

from bdboard.watcher import RefreshScheduler

# Fast timings: long enough to be robust on a loaded CI box, short enough to
# keep the whole module well under a second.
_DEBOUNCE = 0.02
_COOLDOWN = 0.08


class _Recorder:
    """Counts refresh()/broadcast() calls; refresh() is configurable."""

    def __init__(self, changed: bool = True) -> None:
        self.refresh_calls = 0
        self.broadcast_calls = 0
        self._changed = changed
        # Optional list of side-effects (exception instances or bool) consumed
        # one per refresh call; falls back to self._changed when exhausted.
        self.script: list[object] = []

    async def refresh(self) -> bool:
        self.refresh_calls += 1
        if self.script:
            outcome = self.script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return bool(outcome)
        return self._changed

    async def broadcast(self) -> None:
        self.broadcast_calls += 1


def test_isolated_event_refreshes_and_broadcasts() -> None:
    """A single isolated event must produce exactly one refresh + broadcast."""

    async def scenario() -> _Recorder:
        rec = _Recorder(changed=True)
        sched = RefreshScheduler(
            rec.refresh, rec.broadcast, debounce_s=_DEBOUNCE, cooldown_s=_COOLDOWN
        )
        await sched.settle_now()
        return rec

    rec = asyncio.run(scenario())
    assert rec.refresh_calls == 1
    assert rec.broadcast_calls == 1


def test_trailing_event_after_cooldown_still_refreshes() -> None:
    """THE bug: an event whose settle lands inside the post-refresh cooldown
    window must NOT be dropped — it waits out the remainder and refreshes.

    The old code returned early here, so the second (trailing) write was
    lost until some unrelated future write happened to land outside cooldown.
    """

    async def scenario() -> _Recorder:
        rec = _Recorder(changed=True)
        sched = RefreshScheduler(
            rec.refresh, rec.broadcast, debounce_s=_DEBOUNCE, cooldown_s=_COOLDOWN
        )
        # First write: refreshes, arms the cooldown clock.
        await sched.settle_now()
        # Trailing write lands immediately (well within cooldown). Under the
        # OLD logic this returned early with no refresh and no catch-up.
        await sched.settle_now()
        return rec

    rec = asyncio.run(scenario())
    assert rec.refresh_calls == 2, "trailing in-cooldown event was dropped"
    assert rec.broadcast_calls == 2


def test_burst_collapses_to_single_refresh() -> None:
    """Debounce still coalesces a rapid burst into ONE refresh — a single
    logical bd write spans several FS batches and must not fan out."""

    async def scenario() -> _Recorder:
        rec = _Recorder(changed=True)
        sched = RefreshScheduler(
            rec.refresh, rec.broadcast, debounce_s=_DEBOUNCE, cooldown_s=_COOLDOWN
        )
        # Fire a tight burst of notifications; each cancels the previous
        # pending settle before its debounce elapses.
        for _ in range(6):
            sched.notify()
        # Let the final settle run to completion.
        await asyncio.sleep(_DEBOUNCE + _COOLDOWN + 0.05)
        return rec

    rec = asyncio.run(scenario())
    assert rec.refresh_calls == 1
    assert rec.broadcast_calls == 1


def test_no_change_suppresses_broadcast() -> None:
    """refresh() reporting no change must NOT fire an SSE broadcast (dedup)."""

    async def scenario() -> _Recorder:
        rec = _Recorder(changed=False)
        sched = RefreshScheduler(
            rec.refresh, rec.broadcast, debounce_s=_DEBOUNCE, cooldown_s=_COOLDOWN
        )
        await sched.settle_now()
        return rec

    rec = asyncio.run(scenario())
    assert rec.refresh_calls == 1
    assert rec.broadcast_calls == 0


def test_transient_refresh_failure_does_not_wedge_live_sync() -> None:
    """A transient refresh failure must not permanently wedge live-sync:
    the next event still syncs (refreshes + broadcasts).

    Root cause #3: the old code advanced the cooldown clock even on failure,
    so the next real event got swallowed by the cooldown bug. The fixed
    scheduler leaves the clock untouched on failure and retries on the next
    event.
    """

    async def scenario() -> _Recorder:
        rec = _Recorder()
        # First refresh blows up (transient bd list failure); second succeeds.
        rec.script = [RuntimeError("bd list boom"), True]
        sched = RefreshScheduler(
            rec.refresh, rec.broadcast, debounce_s=_DEBOUNCE, cooldown_s=_COOLDOWN
        )
        await sched.settle_now()  # raises internally, swallowed, no broadcast
        await sched.settle_now()  # next change syncs
        return rec

    rec = asyncio.run(scenario())
    assert rec.refresh_calls == 2
    assert rec.broadcast_calls == 1, "live-sync stayed wedged after transient failure"


def test_failure_does_not_advance_cooldown_clock() -> None:
    """After a failed refresh the cooldown clock stays where it was, so the
    follow-up event is not forced to wait out a cooldown it never earned."""

    async def scenario() -> float:
        rec = _Recorder()
        rec.script = [RuntimeError("boom"), True]
        sched = RefreshScheduler(
            rec.refresh, rec.broadcast, debounce_s=_DEBOUNCE, cooldown_s=_COOLDOWN
        )
        await sched.settle_now()  # fails
        start = asyncio.get_event_loop().time()
        await sched.settle_now()  # should only pay the debounce, not cooldown
        return asyncio.get_event_loop().time() - start

    elapsed = asyncio.run(scenario())
    # If the failure had armed the cooldown, the second settle would have
    # waited ~cooldown on top of debounce. Assert it did NOT.
    assert elapsed < _DEBOUNCE + _COOLDOWN, "failure wrongly armed the cooldown clock"
