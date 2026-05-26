"""Tiny in-process pub/sub for SSE fanout.

One EventBus instance owns N subscriber queues (one per open SSE connection).
broadcast() pushes the same event onto every queue. Each subscriber pulls
from its own queue at its own pace via subscribe()'s async generator.

Why not a single shared queue? With one queue you can't fan out — only one
consumer per item. Per-subscriber queues let every browser tab see every
event independently. The cost is O(N) push per broadcast, which is fine
for the scale we actually have (dozens of tabs, not thousands).

Backpressure policy: bounded queue per subscriber, drop oldest on overflow.
A slow client should NOT be able to block the broadcaster — better to lose
an event than to back up the watcher task. The next event will trigger the
same UI re-fetch anyway, so dropped events are not a correctness problem,
just a freshness blip.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

log = logging.getLogger(__name__)

# Per-subscriber queue size. Small intentionally — if a client falls more
# than this many events behind, they're disconnected enough that one stale
# refresh trigger is the right level of catch-up.
_QUEUE_SIZE = 16


class EventBus:
    """In-process broadcaster. One instance per app."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    async def broadcast(self, event: str) -> None:
        """Push `event` to every subscriber. Non-blocking per subscriber —
        if a queue is full, the oldest item is dropped to make room."""
        async with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest, push newest. Lossy but safe.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    log.warning("event bus subscriber queue is hot; event lost")

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[str]]:
        """Context-manage subscription so connection cleanup is automatic.
        Use as `async with bus.subscribe() as q: async for e in iter_q(q): ...`."""
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        async with self._lock:
            self._subscribers.add(q)
        try:
            yield q
        finally:
            async with self._lock:
                self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        """For diagnostics / status endpoint."""
        return len(self._subscribers)
