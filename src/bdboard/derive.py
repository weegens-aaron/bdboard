"""Derive UI-shaped views (lanes / activity / counts) from raw bead snapshots.

All derivations are pure functions over the snapshot list — no I/O, no
caching. The Store handles freshness; this module just shapes data.

Lane assignment (mirrors bcc's lanes.go):
    - In-Progress : status == 'in_progress'
    - Blocked     : status == 'blocked' OR (status == 'open' AND has unmet
                    blocking dependency)
    - Ready       : status == 'open' AND no unmet blocking dependencies
    - Backlog     : everything else open (currently same as Ready when there
                    are no closed dep targets; we follow bd's own convention
                    that `bd ready` shows what's actionable — Ready is the
                    subset of open with all deps closed; Backlog is the rest
                    of open that isn't blocked)
    - Closed      : status in {closed, resolved, done}. Capped at
                    CLOSED_LANE_LIMIT and sorted by closed_at desc so the
                    most recent wins are most visible.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

# Lane keys are stable identifiers used in template selectors.
# Order here is informational only — the template controls render order.
LANES = ("backlog", "ready", "in_progress", "blocked", "closed")

# Cap the closed lane so a project with thousands of closed beads doesn't
# tank page render. Recently-closed is what people actually want to see;
# anything older is best reached via search.
CLOSED_LANE_LIMIT = 50


def _is_closed(status: str) -> bool:
    return status in ("closed", "resolved", "done")


def _has_unmet_blocking_dep(bead: dict[str, Any], by_id: dict[str, dict]) -> bool:
    """A bead is functionally blocked if any of its `blocks` / `blocked-by`
    dependency targets are not yet closed."""
    deps = bead.get("deps") or bead.get("dependencies") or []
    for d in deps:
        dep_type = (d.get("type") or "").lower()
        if dep_type not in ("blocks", "blocked-by", "blocked_by"):
            continue
        target_id = d.get("depends_on_id") or d.get("target") or d.get("id")
        target = by_id.get(target_id)
        if target is None:
            # unknown target — treat as unmet, conservative
            return True
        if not _is_closed(target.get("status", "")):
            return True
    return False


def lanes(beads: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bucket beads into the swim lanes. Open lanes sorted by priority asc
    (P0 first) then updated_at desc. Closed lane sorted by closed_at desc
    (most recent first) and capped at CLOSED_LANE_LIMIT."""
    by_id = {b.get("id"): b for b in beads if b.get("id")}
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in LANES}
    for b in beads:
        status = (b.get("status") or "").lower()
        if _is_closed(status):
            buckets["closed"].append(b)
            continue
        if status == "in_progress":
            buckets["in_progress"].append(b)
        elif status == "blocked":
            buckets["blocked"].append(b)
        elif status == "open":
            if _has_unmet_blocking_dep(b, by_id):
                buckets["blocked"].append(b)
            elif (b.get("dependency_count") or 0) == 0:
                buckets["ready"].append(b)
            else:
                # has deps but all closed — still ready
                buckets["ready"].append(b)
        else:
            buckets["backlog"].append(b)
    # Open lanes: priority-then-recency. Closed lane: recency only, then cap.
    for k in ("backlog", "ready", "in_progress", "blocked"):
        buckets[k].sort(
            key=lambda x: (x.get("priority", 99), -_epoch(x.get("updated_at")))
        )
    buckets["closed"].sort(
        key=lambda x: -_epoch(x.get("closed_at") or x.get("updated_at"))
    )
    buckets["closed"] = buckets["closed"][:CLOSED_LANE_LIMIT]
    return buckets


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
        if status == "closed" or status == "resolved" or status == "done":
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
    """Top-of-page counts shown in the masthead."""
    by_status: dict[str, int] = defaultdict(int)
    for b in beads:
        by_status[(b.get("status") or "unknown").lower()] += 1
    return dict(by_status)


def _epoch(ts: str | None) -> float:
    """Parse an ISO timestamp (with optional Z) to a float epoch. 0 on miss."""
    if not ts:
        return 0.0
    try:
        s = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return 0.0


def humanize_ts(ts: str | None) -> str:
    """Render an ISO timestamp as e.g. '14m ago' / '2h ago' / 'May 19'."""
    if not ts:
        return "—"
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ts
    delta = datetime.now(timezone.utc) - dt
    sec = int(delta.total_seconds())
    if sec < 60:
        return f"{sec}s ago"
    if sec < 3600:
        return f"{sec // 60}m ago"
    if sec < 86400:
        return f"{sec // 3600}h ago"
    if sec < 604800:
        return f"{sec // 86400}d ago"
    return dt.strftime("%b %d")
