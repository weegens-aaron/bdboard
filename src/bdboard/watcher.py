"""Filesystem-event → store-refresh scheduling (debounce + cooldown).

Extracted from app.py so the tricky timing logic is unit-testable without
spinning up FastAPI, watchfiles, or a real bd workspace (bdboard-xbc7).

The watcher in app.py turns raw ``watchfiles`` batches into a *single*
``store.refresh()`` per logical bd mutation, then broadcasts an SSE
``beads_changed`` event iff the bead list actually changed. Two timing
controls shape that:

  * DEBOUNCE — a single ``bd update`` writes 3-5 files inside
    ``.beads/embeddeddolt/`` in quick succession (manifest, journal.idx,
    lock, ...). A trailing quiet-window collapses that burst into one
    refresh. ~250ms is comfortably longer than the burst yet far shorter
    than human perception.

  * COOLDOWN — after a refresh *completes*, suppress the NEXT refresh for a
    short window so a sustained write storm (dolt commit + auto-export
    fan-out + git-add hook) cannot chain-fire refreshes at full FS speed.

The bug this module fixes (bdboard-xbc7, root cause #1 + #3):

The OLD ``_settle_task`` returned EARLY when an event's debounce timer
fired inside the cooldown window — WITHOUT refreshing AND WITHOUT
scheduling a catch-up. Its comment assumed "a later FS event will
retrigger", but the LAST event of a burst (or a single isolated write)
has no later event. That trailing change was silently lost until some
unrelated future write happened to land outside a cooldown. Worst case
for a single ``bd update`` while the board sits open: it never refreshes.

The compounding failure (#3): when ``store.refresh()`` *failed* (transient
``bd list`` error), the old code still advanced ``_last_refresh_at`` into
cooldown, so the very next real event got swallowed by the bug above —
permanently wedging live-sync until an out-of-cooldown write appeared.

The fix here: a settle that lands inside cooldown does NOT drop the event;
it *waits out the remaining cooldown* and then refreshes. Newer events
simply cancel and reschedule, so trailing/isolated writes ALWAYS produce a
refresh within ~debounce+cooldown of the write. And the cooldown clock is
only advanced after a refresh that *succeeded* (no exception), so a
transient failure cannot wedge the next change.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

# Defaults preserved from the original app.py constants.
DEFAULT_DEBOUNCE_S = 0.25
DEFAULT_COOLDOWN_S = 1.0


class RefreshScheduler:
    """Coalesce a stream of FS-change notifications into deduped refreshes.

    Call :meth:`notify` for every batch of filesystem events. The scheduler
    debounces them, runs ``refresh()`` once the writes settle (honoring a
    post-refresh cooldown), and calls ``broadcast()`` iff ``refresh()``
    reported a real change.

    ``refresh`` must return ``True`` when the bead list changed (drives the
    broadcast), ``False`` when nothing changed. If ``refresh`` *raises*, the
    cooldown clock is NOT advanced and the exception is logged — so the next
    notify retries promptly instead of being swallowed by cooldown.
    """

    def __init__(
        self,
        refresh: Callable[[], Awaitable[bool]],
        broadcast: Callable[[], Awaitable[None]],
        *,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        cooldown_s: float = DEFAULT_COOLDOWN_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._refresh = refresh
        self._broadcast = broadcast
        self._debounce_s = debounce_s
        self._cooldown_s = cooldown_s
        self._monotonic = monotonic
        self._last_refresh_at: float = 0.0
        self._pending: asyncio.Task | None = None

    def notify(self) -> None:
        """Record an FS-change batch. Cancels any in-flight settle and starts
        a fresh one, so a continuous event stream keeps pushing the actual
        refresh out until the writes finally stop."""
        if self._pending is not None and not self._pending.done():
            self._pending.cancel()
        self._pending = asyncio.create_task(self._settle())

    async def settle_now(self) -> None:
        """Run a single settle cycle inline (for tests). Production uses
        :meth:`notify`, which wraps this in a cancellable task."""
        await self._settle()

    async def _settle(self) -> None:
        """Debounce, wait out any cooldown remainder, then refresh+broadcast.

        Cancellation (a newer event arrived) at ANY sleep point silently
        aborts this cycle — the newer event owns the next refresh.
        """
        try:
            await asyncio.sleep(self._debounce_s)

            # Cooldown handling — the heart of the bdboard-xbc7 fix.
            # Instead of DROPPING an event that lands inside the cooldown
            # window (the old bug), we wait out the *remaining* cooldown and
            # then refresh. A trailing/isolated write therefore still
            # refreshes, just slightly later. If a newer event arrives during
            # this wait, we get cancelled and it reschedules — exactly what
            # we want.
            elapsed = self._monotonic() - self._last_refresh_at
            remaining = self._cooldown_s - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            return

        try:
            changed = await self._refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do NOT advance the cooldown clock on failure: leaving it where
            # it was means the next notify retries promptly rather than being
            # swallowed by a cooldown we "earned" without actually syncing.
            # This is what stops a transient `bd list` hiccup from
            # permanently wedging live-sync (bdboard-xbc7 root cause #3).
            log.exception("watcher: refresh raised; will retry on next change")
            return

        # Only a *successful* refresh advances the cooldown clock.
        self._last_refresh_at = self._monotonic()
        if changed:
            await self._broadcast()
