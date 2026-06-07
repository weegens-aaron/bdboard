"""Masthead counts + activity-feed derivations from raw bead snapshots.

Split out of :mod:`bdboard.derive.lanes` (which crossed the 600-line guideline
once graph-hygiene wiring landed). These two functions are a distinct concern
from lane *bucketing*: they shape the top-of-page KPI counts and the synthetic
activity stream, sharing only a few status constants with the lane module.

Pure functions over the snapshot list — no I/O, no caching.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from bdboard.derive.lanes import (
    CLOSED_STATUSES,
    HIDDEN_BOARD_STATUSES,
    _is_gate,
)
from bdboard.derive.timeutil import _epoch


def activity(beads: list[dict[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    """Build an activity feed from updated_at / closed_at / created_at.

    We don't have a real audit feed across all beads — bd doesn't expose one
    — so we synthesize 'current state as event': each bead becomes one entry
    using its most recent timestamp, with a verb inferred from current status.
    """
    items: list[dict[str, Any]] = []
    for b in beads:
        ts_str = b.get("closed_at") or b.get("updated_at") or b.get("created_at")
        if not ts_str:
            continue
        status = (b.get("status") or "").lower()
        if status in CLOSED_STATUSES:
            verb = "closed"
        elif status == "in_progress":
            verb = "in progress"
        elif status == "blocked":
            verb = "blocked"
        elif ts_str == b.get("created_at"):
            verb = "created"
        else:
            verb = "updated"
        items.append(
            {
                "id": b.get("id"),
                "title": b.get("title"),
                "actor": b.get("assignee") or b.get("created_by") or "—",
                "verb": verb,
                "ts": ts_str,
                "ts_epoch": _epoch(ts_str),
                "priority": b.get("priority"),
            }
        )
    items.sort(key=lambda x: -x["ts_epoch"])
    return items[:limit]


def counts(beads: list[dict[str, Any]]) -> dict[str, int]:
    """Top-of-page counts shown in the masthead.

    Always returns a fixed set of statuses in a stable order to prevent
    layout jitter when counts reach zero. Zero-value counts are included
    to maintain consistent header geometry — including `in_progress`, which
    is a first-class KPI: bdboard is a general-purpose multi-WIP board, so
    any number of beads may be in progress concurrently (the lanes render
    N>1 cleanly). The cell must be present whether the count is 0, 1, or
    many, and must match the skeleton so the masthead never reflows on
    hydration.
    """
    # Fixed status order for stable header layout. `in_progress` sits in
    # lifecycle order between open and blocked so the skeleton reserves the
    # same cell count (5) — no 5th-cell jitter when live counts hydrate.
    status_order = ["open", "in_progress", "blocked", "deferred", "closed"]

    # Count actual beads by status, skipping bd-internal machinery statuses
    # (e.g. `hooked`) so the masthead never shows a count without a matching
    # lane — those beads are hidden from the board entirely (bdboard-m5bm).
    # Non-closed gates are counted under a synthetic `gate` key (not their raw
    # `open` status) so the masthead KPI matches the gate lane and a pending
    # wait is never tallied as actionable Open work (audit FB-3).
    by_status: dict[str, int] = defaultdict(int)
    for b in beads:
        status = (b.get("status") or "unknown").lower()
        if status in HIDDEN_BOARD_STATUSES:
            continue
        if _is_gate(b) and status not in CLOSED_STATUSES:
            by_status["gate"] += 1
            continue
        by_status[status] += 1

    # Build ordered dict with all statuses, including zeros
    result = {status: by_status.get(status, 0) for status in status_order}

    # Include any non-standard statuses that actually exist (e.g. `pinned`,
    # which has its own lane). Hidden statuses were already filtered above.
    for status, count in by_status.items():
        if status not in result and count > 0:
            result[status] = count

    return result
