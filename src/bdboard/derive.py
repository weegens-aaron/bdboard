"""Derive UI-shaped views (lanes / activity / counts) from raw bead snapshots.

All derivations are pure functions over the snapshot list — no I/O, no
caching. The Store handles freshness; this module just shapes data.

Lane assignment (mirrors bcc's lanes.go):
    - In-Progress : status == 'in_progress'
    - Blocked     : status == 'blocked' OR (status == 'open' AND has unmet
                    blocking dependency)
    - Ready       : status == 'open' AND no unmet blocking dependencies
    - Backlog     : everything else open-ish
    - Closed      : status in {closed, resolved, done}. Capped at
                    CLOSED_LANE_LIMIT and sorted by closed_at desc so the
                    most recent wins are most visible.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from heapq import heappop, heappush
from typing import Any

# Lane keys are stable identifiers used in template selectors.
# Order here is informational only — the template controls render order.
LANES = ("backlog", "ready", "in_progress", "blocked", "closed")

# Cap the closed lane so a project with thousands of closed beads doesn't
# tank page render. Recently-closed is what people actually want to see;
# anything older is best reached via search.
CLOSED_LANE_LIMIT = 50

_STATUS_META: dict[str, tuple[str, str]] = {
    "open": ("○", "Open"),
    "in_progress": ("▶", "In Progress"),
    "blocked": ("⛔", "Blocked"),
    "deferred": ("⏸", "Deferred"),
    "closed": ("✓", "Closed"),
    "resolved": ("✓", "Resolved"),
    "done": ("✓", "Done"),
}


def _is_epic(bead: dict[str, Any]) -> bool:
    return (bead.get("issue_type") or "").lower() == "epic"


def _is_closed(status: str) -> bool:
    return status in ("closed", "resolved", "done")


def _has_unmet_blocking_dep(bead: dict[str, Any], by_id: dict[str, dict]) -> bool:
    """A bead is functionally blocked if any of its `blocks` / `blocked-by`
    dependency targets are not yet closed."""
    deps = bead.get("deps") or bead.get("dependencies") or []
    for d in deps:
        dep_type = (d.get("type") or d.get("dependency_type") or "").lower()
        if dep_type not in ("blocks", "blocked-by", "blocked_by"):
            continue
        target_id = (
            d.get("depends_on_id")
            or d.get("target")
            or d.get("id")
            or d.get("dependsOnId")
        )
        target = by_id.get(target_id)
        if target is None:
            # unknown target — treat as unmet, conservative
            return True
        if not _is_closed(target.get("status", "")):
            return True
    return False


def _stable_key(bead: dict[str, Any]) -> tuple[float, str]:
    return (_epoch(bead.get("created_at")), bead.get("id") or "")


def _topo_component_order(
    nodes: set[str],
    succ: dict[str, set[str]],
    indegree: dict[str, int],
    by_id: dict[str, dict],
) -> list[dict[str, Any]]:
    """Topologically order a connected dependency component.

    Stable tie-break: created_at asc, then id asc. If a cycle exists, append
    remaining nodes by stable key so rendering stays deterministic.
    """
    local_in = {n: indegree.get(n, 0) for n in nodes}
    heap: list[tuple[float, str, str]] = []
    for n in nodes:
        if local_in[n] == 0:
            b = by_id[n]
            created, bead_id = _stable_key(b)
            heappush(heap, (created, bead_id, n))

    ordered_ids: list[str] = []
    while heap:
        _, _, n = heappop(heap)
        ordered_ids.append(n)
        for m in sorted(succ.get(n, ())):
            if m not in local_in:
                continue
            local_in[m] -= 1
            if local_in[m] == 0:
                b = by_id[m]
                created, bead_id = _stable_key(b)
                heappush(heap, (created, bead_id, m))

    if len(ordered_ids) != len(nodes):
        leftovers = sorted(
            (n for n in nodes if n not in ordered_ids),
            key=lambda n: _stable_key(by_id[n]),
        )
        ordered_ids.extend(leftovers)

    return [by_id[n] for n in ordered_ids]


def epic_lane(beads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the horizontal epic strip data.

    Rules:
    - Only issue_type=epic
    - Closed epics omitted
    - Wired epics are sequenced predecessor→successor left-to-right
    - Unwired epics appended after wired chains in stable order
    """
    active_epics = [
        b
        for b in beads
        if _is_epic(b) and not _is_closed((b.get("status") or "").lower())
    ]
    if not active_epics:
        return []

    by_id = {b.get("id"): b for b in active_epics if b.get("id")}
    succ: dict[str, set[str]] = {bid: set() for bid in by_id}
    indegree: dict[str, int] = {bid: 0 for bid in by_id}

    for b in active_epics:
        dep_list = b.get("deps") or b.get("dependencies") or []
        this_id = b.get("id")
        if not this_id:
            continue
        for dep in dep_list:
            dep_type = (dep.get("type") or dep.get("dependency_type") or "").lower()
            if dep_type not in ("blocks", "blocked-by", "blocked_by"):
                continue
            predecessor_id = (
                dep.get("depends_on_id")
                or dep.get("target")
                or dep.get("id")
                or dep.get("dependsOnId")
            )
            if predecessor_id not in by_id:
                continue
            # Current issue depends on predecessor: predecessor -> current.
            if this_id not in succ[predecessor_id]:
                succ[predecessor_id].add(this_id)
                indegree[this_id] += 1

    undirected: dict[str, set[str]] = {bid: set() for bid in by_id}
    for u, vs in succ.items():
        for v in vs:
            undirected[u].add(v)
            undirected[v].add(u)

    wired_components: list[set[str]] = []
    unwired: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bid in sorted(by_id, key=lambda k: _stable_key(by_id[k])):
        if bid in seen:
            continue
        stack = [bid]
        comp: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.add(cur)
            stack.extend(undirected[cur] - seen)
        edge_count = sum(len(succ[n]) for n in comp)
        if edge_count == 0:
            unwired.append(by_id[bid])
        else:
            wired_components.append(comp)

    wired_components.sort(key=lambda comp: min(_stable_key(by_id[n]) for n in comp))

    ordered: list[dict[str, Any]] = []
    for comp in wired_components:
        ordered.extend(_topo_component_order(comp, succ, indegree, by_id))

    unwired.sort(key=_stable_key)
    ordered.extend(unwired)

    out: list[dict[str, Any]] = []
    for b in ordered:
        status_key = (b.get("status") or "unknown").lower()
        icon, label = _STATUS_META.get(
            status_key, ("?", status_key.replace("_", " ").title())
        )
        enriched = dict(b)
        enriched["status_key"] = status_key
        enriched["status_icon"] = icon
        enriched["status_label"] = label
        out.append(enriched)
    return out


def lanes(beads: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bucket non-epic beads into swim lanes.

    Open lanes sorted by priority asc (P0 first) then updated_at desc.
    Closed lane sorted by closed_at desc (most recent first) and capped.
    """
    non_epics = [b for b in beads if not _is_epic(b)]
    by_id = {b.get("id"): b for b in non_epics if b.get("id")}
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in LANES}
    for b in non_epics:
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
            else:
                buckets["ready"].append(b)
        else:
            buckets["backlog"].append(b)

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
        if status in {"closed", "resolved", "done"}:
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
