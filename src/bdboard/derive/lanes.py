"""Lane / activity / counts derivations from raw bead snapshots.

Pure functions over the snapshot list — no I/O, no caching. The Store handles
freshness; this module just shapes data for the board view.

Lane assignment rules:
    - In-Progress : status == 'in_progress'
    - Blocked     : status == 'blocked' OR (status == 'open' AND has unmet
                    blocking dependency)
    - Ready       : status == 'open' AND no unmet blocking dependencies
    - Deferred    : everything else open-ish
    - Closed      : status in {closed, resolved, done}. Bounded by the
                    board's date window (see BOARD_CLOSED_WINDOW_DAYS) at
                    fetch time and sorted by closed_at desc so the most
                    recent wins are most visible.
"""

from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush
from typing import Any

from bdboard.derive.timeutil import _epoch

# Lane keys are stable identifiers used in template selectors.
# Order here is informational only — the template controls render order.
LANES = ("deferred", "ready", "in_progress", "blocked", "closed")

# Statuses that represent closed/completed work
CLOSED_STATUSES = frozenset(["closed", "resolved", "done"])

# The board is a *recent-activity* surface. Its time-filter strip caps at
# 12h / 1d / 3d (see templates/base.html BOARD_TIME_WINDOWS), so the closed
# set is bounded by the WIDEST of those windows at fetch time rather than by
# a static count cap. This keeps the header CLOSED KPI and the Closed lane
# count consistent (bdboard-p8v): both reflect the same date-bounded set,
# narrowed further client-side to the user's selected window. Anything older
# than this window lives on the History page, not the board.
BOARD_CLOSED_WINDOW_DAYS = 3

# The History page is the long-window retrospective surface (7d/30d/90d/All).
# It keeps a count-capped closed fetch so its behaviour is unchanged by the
# board's switch to a date-bounded closed set (bdboard-p8v).
HISTORY_CLOSED_LIMIT = 50

_STATUS_META: dict[str, tuple[str, str]] = {
    "open": ("○", "Open"),
    "in_progress": ("▶", "In Progress"),
    "blocked": ("⛔", "Blocked"),
    "deferred": ("⏸", "Deferred"),
    "closed": ("✓", "Closed"),
    "resolved": ("✓", "Resolved"),
    "done": ("✓", "Done"),
}


# ----- Dependency field access helpers -----


def get_dependency_list(bead: dict) -> list[dict]:
    """Extract dependency list from a bead, normalizing field name variations.

    bd beads may store dependencies under 'deps' or 'dependencies'.
    Returns an empty list if neither field is present.
    """
    return bead.get("deps") or bead.get("dependencies") or []


def get_dependency_type(dep: dict) -> str:
    """Extract dependency type, normalizing field name variations.

    Dependency type may be stored as 'type' or 'dependency_type'.
    Returns normalized lowercase string, or empty string if not found.
    """
    return (dep.get("type") or dep.get("dependency_type") or "").lower()


def get_dependency_target_id(dep: dict) -> str | None:
    """Extract target ID from a dependency dict with fallback chain.

    Target ID may be stored under multiple field names:
    - depends_on_id (preferred)
    - target
    - id
    - dependsOnId (legacy camelCase)

    Returns the first non-None value found, or None if all fields are missing.
    """
    return dep.get("depends_on_id") or dep.get("target") or dep.get("id") or dep.get("dependsOnId")


# ----- Lane assignment logic -----


def _is_epic(bead: dict[str, Any]) -> bool:
    return (bead.get("issue_type") or "").lower() == "epic"


def _is_molecule(bead: dict[str, Any]) -> bool:
    """True for a formula-pour grouping WRAPPER (issue_type == 'molecule').

    `bd mol pour` creates a `molecule`-typed wrapper (the returned
    `new_epic_id`) that parents the whole poured tree, PLUS the formula's own
    `epic`-typed root step. Per the grouping-node display decision (Option A),
    the human-readable `<formula> <id>` name is carried by
    the epic root step (which already surfaces in the epic strip), so the bare
    wrapper is redundant on the board. We hide it from the swim lanes rather
    than render it as a stray ready-lane card. See the grouping-node
    display decision under docs/design/.
    """
    return (bead.get("issue_type") or "").lower() == "molecule"


def _is_closed(status: str) -> bool:
    return status in CLOSED_STATUSES


def _has_unmet_blocking_dep(bead: dict[str, Any], by_id: dict[str, dict]) -> bool:
    """A bead is functionally blocked if any of its `blocks` / `blocked-by`
    dependency targets are not yet closed."""
    deps = get_dependency_list(bead)
    for d in deps:
        dep_type = get_dependency_type(d)
        if dep_type not in ("blocks", "blocked-by", "blocked_by"):
            continue
        target_id = get_dependency_target_id(d)
        target = by_id.get(target_id)
        if target is None:
            # unknown target — treat as unmet, conservative
            return True
        if not _is_closed(target.get("status", "")):
            return True
    return False


def _stable_key(bead: dict[str, Any]) -> tuple[float, str]:
    return (_epoch(bead.get("created_at")), bead.get("id") or "")


def _epic_lane_rank(bead: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> int:
    """Priority rank for which epic should lead the strip.

    Lower is better:
      0: actively in progress
      1: next-ready (open with no unmet blocking dependency)
      2: blocked (explicit blocked status or open with unmet blocker)
      3: deferred
      4: anything else
    """
    status = (bead.get("status") or "").lower()
    if status == "in_progress":
        return 0
    if status == "open":
        return 2 if _has_unmet_blocking_dep(bead, by_id) else 1
    if status == "blocked":
        return 2
    if status == "deferred":
        return 3
    return 4


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
        b for b in beads if _is_epic(b) and not _is_closed((b.get("status") or "").lower())
    ]
    if not active_epics:
        return []

    # Build by_id from all beads (not just active epics) so closed dependencies
    # can be correctly identified when checking _has_unmet_blocking_dep.
    by_id = {b.get("id"): b for b in beads if b.get("id")}
    # Build dependency graph structures only for active epics.
    active_ids = {b.get("id") for b in active_epics if b.get("id")}
    succ: dict[str, set[str]] = {bid: set() for bid in active_ids}
    indegree: dict[str, int] = {bid: 0 for bid in active_ids}

    for b in active_epics:
        dep_list = get_dependency_list(b)
        this_id = b.get("id")
        if not this_id:
            continue
        for dep in dep_list:
            dep_type = get_dependency_type(dep)
            if dep_type not in ("blocks", "blocked-by", "blocked_by"):
                continue
            predecessor_id = get_dependency_target_id(dep)
            # Only wire up dependencies between active epics. We keep by_id
            # comprehensive for _has_unmet_blocking_dep checks, but the
            # topology graph only includes active epics.
            if predecessor_id not in active_ids:
                continue
            # Current issue depends on predecessor: predecessor -> current.
            if this_id not in succ[predecessor_id]:
                succ[predecessor_id].add(this_id)
                indegree[this_id] += 1

    undirected: dict[str, set[str]] = {bid: set() for bid in active_ids}
    for u, vs in succ.items():
        for v in vs:
            undirected[u].add(v)
            undirected[v].add(u)

    wired_components: list[set[str]] = []
    unwired: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bid in sorted(active_ids, key=lambda k: _stable_key(by_id[k])):
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

    # Ensure position 0 is the active epic, or the next-ready epic if no
    # epic is currently in progress. Keep relative order stable for all
    # remaining epics.
    if ordered:
        anchor = min(
            ordered,
            key=lambda b: (_epic_lane_rank(b, by_id), *_stable_key(b)),
        )
        ordered = [anchor] + [b for b in ordered if b is not anchor]

    out: list[dict[str, Any]] = []
    for b in ordered:
        raw_status = (b.get("status") or "unknown").lower()
        # Derive effective status: if status is open (not yet started) but has
        # unmet blocking dependencies, display as blocked. Don't override
        # in_progress — if work is already underway, show it as such.
        if raw_status == "open" and _has_unmet_blocking_dep(b, by_id):
            status_key = "blocked"
        else:
            status_key = raw_status
        icon, label = _STATUS_META.get(status_key, ("?", status_key.replace("_", " ").title()))
        enriched = dict(b)
        enriched["status_key"] = status_key
        enriched["status_icon"] = icon
        enriched["status_label"] = label
        out.append(enriched)
    return out


def lanes(beads: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bucket non-epic beads into swim lanes.

    Open lanes sorted by priority asc (P0 first) then updated_at desc.
    Closed lane sorted by closed_at desc (most recent first). The closed
    set is bounded by the board's date window at FETCH time (see
    BOARD_CLOSED_WINDOW_DAYS / bd.list_closed), not by a static count here —
    so the header CLOSED KPI and the lane count agree (bdboard-p8v).
    """
    # Exclude epics (they live in the strip) AND molecule wrappers (the
    # redundant formula-pour grouping node — Option A). The
    # wrapper still parents the tree in bd; it just doesn't earn a card here.
    non_epics = [b for b in beads if not _is_epic(b) and not _is_molecule(b)]
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
            buckets["deferred"].append(b)

    for k in ("deferred", "ready", "in_progress", "blocked"):
        buckets[k].sort(key=lambda x: (x.get("priority", 99), -_epoch(x.get("updated_at"))))
    buckets["closed"].sort(key=lambda x: -_epoch(x.get("closed_at") or x.get("updated_at")))
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
    to maintain consistent header geometry.

    Note: in_progress is intentionally omitted. bdboard is a single-flight
    workflow tool — only one item is in-progress at a time, so displaying
    0 or 1 is noise that clutters the header. The In Progress swim lane
    already surfaces the one active bead.
    """
    # Fixed status order for stable header layout
    status_order = ["open", "blocked", "deferred", "closed"]

    # Count actual beads by status
    by_status: dict[str, int] = defaultdict(int)
    for b in beads:
        by_status[(b.get("status") or "unknown").lower()] += 1

    # Build ordered dict with all statuses, including zeros
    result = {status: by_status.get(status, 0) for status in status_order}

    # Include any non-standard statuses that actually exist
    for status, count in by_status.items():
        if status not in result and count > 0:
            result[status] = count

    return result
