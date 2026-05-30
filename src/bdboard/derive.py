"""Derive UI-shaped views (lanes / activity / counts) from raw bead snapshots.

All derivations are pure functions over the snapshot list — no I/O, no
caching. The Store handles freshness; this module just shapes data.

Lane assignment rules:
    - In-Progress : status == 'in_progress'
    - Blocked     : status == 'blocked' OR (status == 'open' AND has unmet
                    blocking dependency)
    - Ready       : status == 'open' AND no unmet blocking dependencies
    - Deferred    : everything else open-ish
    - Closed      : status in {closed, resolved, done}. Capped at
                    CLOSED_LANE_LIMIT and sorted by closed_at desc so the
                    most recent wins are most visible.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from heapq import heappop, heappush
from typing import Any

# Lane keys are stable identifiers used in template selectors.
# Order here is informational only — the template controls render order.
LANES = ("deferred", "ready", "in_progress", "blocked", "closed")

# Statuses that represent closed/completed work
CLOSED_STATUSES = frozenset(["closed", "resolved", "done"])

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
    return (
        dep.get("depends_on_id")
        or dep.get("target")
        or dep.get("id")
        or dep.get("dependsOnId")
    )


# ----- Lane assignment logic -----


def _is_epic(bead: dict[str, Any]) -> bool:
    return (bead.get("issue_type") or "").lower() == "epic"


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
        b
        for b in beads
        if _is_epic(b) and not _is_closed((b.get("status") or "").lower())
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
            buckets["deferred"].append(b)

    for k in ("deferred", "ready", "in_progress", "blocked"):
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
    """
    # Fixed status order for stable header layout
    status_order = ["open", "in_progress", "blocked", "deferred", "closed"]

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


# ----- History page derivations (bdboard-rrc design §4) -----
#
# All pure functions over the existing list_all snapshot — no new bd call,
# no persistence. They power the long-window History page (the complement
# to the board's 12h/1d/3d lane filter and 50-cap closed lane).

# Range presets the History page understands. "all" is the unbounded view.
# Mapping is to a timedelta cutoff measured back from "now"; "all" -> None.
HISTORY_RANGES: dict[str, timedelta | None] = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "all": None,
}

# Default range when none/invalid is supplied (matches the design's default).
DEFAULT_HISTORY_RANGE = "30d"

# Default page size for the paginated closed list (design §D5).
HISTORY_PAGE_SIZE = 100


def _range_to_cutoff(range_key: str, now: datetime | None = None) -> datetime | None:
    """Resolve a range preset to a UTC cutoff datetime (inclusive lower bound).

    Returns None for the unbounded ``"all"`` view. Unknown/empty keys fall
    back to :data:`DEFAULT_HISTORY_RANGE` so a bad query param degrades to a
    sensible window rather than erroring. ``now`` is injectable for
    deterministic tests.
    """
    key = (range_key or "").strip().lower()
    if key not in HISTORY_RANGES:
        key = DEFAULT_HISTORY_RANGE
    delta = HISTORY_RANGES[key]
    if delta is None:
        return None
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base - delta


def _parse_dt(ts: str | None) -> datetime | None:
    """Parse an ISO timestamp (optional trailing Z) to a tz-aware datetime.

    Naive timestamps are assumed UTC. Returns None on missing/invalid input
    so callers can skip beads lacking a usable timestamp.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _day_bucket(ts: str | None) -> str | None:
    """Bucket a timestamp into a local-calendar-day key (``YYYY-MM-DD``).

    Uses the server's local timezone (design §D6) so a user's "today" lines
    up with their wall clock rather than splitting across the UTC date line.
    Returns None when the timestamp is missing/unparseable.
    """
    dt = _parse_dt(ts)
    if dt is None:
        return None
    # astimezone() with no arg converts to the system local timezone.
    return dt.astimezone().strftime("%Y-%m-%d")


def _closed_in_window(
    beads: list[dict[str, Any]], cutoff: datetime | None
) -> list[dict[str, Any]]:
    """Closed beads whose closed_at is >= cutoff (all closed when cutoff None).

    A bead is "closed" by the same rule the board uses (:data:`CLOSED_STATUSES`).
    Beads with no parseable closed_at are excluded — they cannot be placed on
    a timeline.
    """
    out: list[dict[str, Any]] = []
    for b in beads:
        if not _is_closed((b.get("status") or "").lower()):
            continue
        closed = _parse_dt(b.get("closed_at"))
        if closed is None:
            continue
        if cutoff is not None and closed < cutoff:
            continue
        out.append(b)
    return out


def history_window(
    beads: list[dict[str, Any]],
    range_key: str = DEFAULT_HISTORY_RANGE,
    page: int = 1,
    page_size: int = HISTORY_PAGE_SIZE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Paginated list of closed beads within a range, newest-closed first.

    Returns a dict: ``{items, page, page_size, total, has_more}`` where
    ``items`` is the requested page (closed_at desc, then id for stability).
    ``total`` is the full count in the window (pre-pagination). Out-of-range
    pages yield an empty ``items`` with ``has_more=False``. This is a pure
    slice over the in-memory snapshot — no extra I/O per page (design §D5).
    """
    cutoff = _range_to_cutoff(range_key, now=now)
    windowed = _closed_in_window(beads, cutoff)
    windowed.sort(key=lambda b: (-_epoch(b.get("closed_at")), b.get("id") or ""))
    total = len(windowed)
    page = max(1, page)
    size = max(1, page_size)
    start = (page - 1) * size
    end = start + size
    items = windowed[start:end]
    return {
        "items": items,
        "page": page,
        "page_size": size,
        "total": total,
        "has_more": end < total,
    }


def throughput(
    beads: list[dict[str, Any]],
    range_key: str = DEFAULT_HISTORY_RANGE,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Closed-beads-per-day series within a range (design §D2).

    Buckets closed_at by local calendar day (:func:`_day_bucket`) and returns
    a gap-free ascending series ``[{"day": "YYYY-MM-DD", "count": int}, ...]``
    spanning the first through last day that has a close in the window. Days
    with zero closes inside that span are filled with ``count=0`` so the
    chart reads as a continuous timeline rather than a jagged one. Returns
    ``[]`` when nothing closed in the window.
    """
    cutoff = _range_to_cutoff(range_key, now=now)
    windowed = _closed_in_window(beads, cutoff)
    buckets: dict[str, int] = defaultdict(int)
    for b in windowed:
        day = _day_bucket(b.get("closed_at"))
        if day is not None:
            buckets[day] += 1
    if not buckets:
        return []
    days = sorted(buckets)
    first = datetime.strptime(days[0], "%Y-%m-%d")
    last = datetime.strptime(days[-1], "%Y-%m-%d")
    series: list[dict[str, Any]] = []
    cursor = first
    while cursor <= last:
        key = cursor.strftime("%Y-%m-%d")
        series.append({"day": key, "count": buckets.get(key, 0)})
        cursor += timedelta(days=1)
    return series


def _updated_in_window(
    beads: list[dict[str, Any]], cutoff: datetime | None
) -> list[dict[str, Any]]:
    """Beads whose updated_at is >= cutoff (all when cutoff is None).

    The churn/activity counterpart to :func:`_closed_in_window`: where the
    throughput/closed views filter by ``closed_at``, churn filters by
    ``updated_at`` (design D3 - 'the activity/churn views filter by
    updated_at'). Status is irrelevant: an *open* bead that was edited still
    counts as activity. Beads with no parseable ``updated_at`` are excluded -
    they cannot be placed on a timeline.
    """
    out: list[dict[str, Any]] = []
    for b in beads:
        updated = _parse_dt(b.get("updated_at"))
        if updated is None:
            continue
        if cutoff is not None and updated < cutoff:
            continue
        out.append(b)
    return out


def churn(
    beads: list[dict[str, Any]],
    range_key: str = DEFAULT_HISTORY_RANGE,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Activity-over-time: beads *touched* per day within a range (design 6, D).

    **Churn definition** (the open question deferred bead D was waiting on):
    a bead is 'churned' on the calendar day of its ``updated_at`` - i.e. the
    day it was last mutated. ``churn`` counts how many beads were last touched
    on each day in the window, regardless of status (an edited *open* bead is
    activity just as much as a freshly *closed* one). This complements
    :func:`throughput` (which counts *closes* by ``closed_at``): throughput
    answers 'how much did we finish?', churn answers 'how much moved?'.

    Returns a gap-free ascending series
    ``[{\"day\": \"YYYY-MM-DD\", \"count\": int}, ...]`` spanning the first
    through last day with activity in the window, zero-filling quiet days so
    the chart reads as a continuous timeline. Returns ``[]`` when nothing was
    touched in the window. Pure over the snapshot - no extra I/O.

    Caveat: ``updated_at`` reflects only the *latest* mutation bd retained in
    the current Dolt-compacted snapshot, so a bead edited many times shows as
    a single day of churn (its most recent touch), not one per edit. A true
    per-edit feed would need per-bead ``bd history`` (deferred bead E); that
    is intentionally out of scope here (design 3 / 6).
    """
    cutoff = _range_to_cutoff(range_key, now=now)
    windowed = _updated_in_window(beads, cutoff)
    buckets: dict[str, int] = defaultdict(int)
    for b in windowed:
        day = _day_bucket(b.get("updated_at"))
        if day is not None:
            buckets[day] += 1
    if not buckets:
        return []
    days = sorted(buckets)
    first = datetime.strptime(days[0], "%Y-%m-%d")
    last = datetime.strptime(days[-1], "%Y-%m-%d")
    series: list[dict[str, Any]] = []
    cursor = first
    while cursor <= last:
        key = cursor.strftime("%Y-%m-%d")
        series.append({"day": key, "count": buckets.get(key, 0)})
        cursor += timedelta(days=1)
    return series


def _percentile(sorted_vals: list[float], pct: float) -> float | None:
    """Linear-interpolated percentile of an already-sorted list.

    ``pct`` in [0, 100]. Returns None for an empty list. Single-element lists
    return that element. Matches the common "linear interpolation between
    closest ranks" definition (numpy's default).
    """
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_vals) - 1)
    frac = rank - low
    return sorted_vals[low] + (sorted_vals[high] - sorted_vals[low]) * frac


def lead_time_stats(
    beads: list[dict[str, Any]],
    range_key: str = DEFAULT_HISTORY_RANGE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Lead-time / cycle-time stats over closed beads in a range (design §D2a).

    - **lead time**  = created_at → closed_at (how long from filing to done)
    - **cycle time** = started_at → closed_at (how long actively in flight)

    Returns ``{n, median_lead_h, p90_lead_h, median_cycle_h, p90_cycle_h}``
    with hour-valued floats (rounded to 1 dp) or None when there is no data
    for that metric. ``n`` is the count of closed beads in the window.
    Negative/zero durations from clock skew or odd data are dropped.
    """
    cutoff = _range_to_cutoff(range_key, now=now)
    windowed = _closed_in_window(beads, cutoff)
    lead_hours: list[float] = []
    cycle_hours: list[float] = []
    for b in windowed:
        closed = _parse_dt(b.get("closed_at"))
        if closed is None:
            continue
        created = _parse_dt(b.get("created_at"))
        if created is not None:
            h = (closed - created).total_seconds() / 3600.0
            if h >= 0:
                lead_hours.append(h)
        started = _parse_dt(b.get("started_at"))
        if started is not None:
            h = (closed - started).total_seconds() / 3600.0
            if h >= 0:
                cycle_hours.append(h)
    lead_hours.sort()
    cycle_hours.sort()

    def _round(v: float | None) -> float | None:
        return None if v is None else round(v, 1)

    return {
        "n": len(windowed),
        "median_lead_h": _round(_percentile(lead_hours, 50)),
        "p90_lead_h": _round(_percentile(lead_hours, 90)),
        "median_cycle_h": _round(_percentile(cycle_hours, 50)),
        "p90_cycle_h": _round(_percentile(cycle_hours, 90)),
    }


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


def humanize_hours(hours: float | None) -> str:
    """Render an hour-valued duration as a compact human string.

    Examples: ``None`` -> '\u2014', 0.4 -> '24m', 2.5 -> '2.5h',
    36.0 -> '1.5d'. Used by the History KPI strip for lead/cycle times.
    """
    if hours is None:
        return "\u2014"
    if hours < 0:
        return "\u2014"
    if hours < 1:
        minutes = int(round(hours * 60))
        return f"{minutes}m"
    if hours < 48:
        # Trim a trailing .0 so whole hours read cleanly (e.g. '3h' not '3.0h').
        val = round(hours, 1)
        return f"{val:g}h"
    days = round(hours / 24.0, 1)
    return f"{days:g}d"


def status_timeline(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive a per-bead status-transition timeline from ``bd history <id>``.

    ``bd history <id> --json`` returns one full issue snapshot per Dolt
    commit, **newest first** (see design bdboard-rrc 2.2). This is the
    deferred "bead E" enrichment: rather than the field-by-field audit diff
    (:func:`bdboard.app._shape_audit`), we collapse the snapshot stream to
    only the moments the lifecycle *status* changed (created -> in_progress
    -> closed, ...) so a reader can see how long a bead spent in each state.

    Pure over the history payload (no I/O): the caller reuses the entries the
    audit view already fetched, so this adds **no** extra ``bd history``
    subprocess call and respects the single-writer dolt gate.

    Returns a list of stops ordered **oldest -> newest**, each a dict with
    ``status``, ``when`` (ISO commit date the bead entered this status),
    ``who`` (committer), ``commit`` (8-char short hash), and ``dwell_h``
    (hours spent IN this status before the next transition, or ``None`` for
    the current/last status whose dwell is still open-ended).

    Empty/None input yields an empty list so the template can render a
    "no transitions" state without special-casing.
    """
    if not history:
        return []

    # bd returns newest-first; walk oldest-first so transitions read forward.
    ordered = list(reversed(history))

    stops: list[dict[str, Any]] = []
    prev_status: str | None = None
    for hist in ordered:
        issue = hist.get("Issue") or {}
        status = (issue.get("status") or "").strip().lower()
        if not status:
            continue
        # Record only commits where status actually changed; the first
        # observed status is the bead's origin state and is always recorded.
        if status == prev_status:
            continue
        stops.append(
            {
                "status": status,
                "when": hist.get("CommitDate"),
                "who": hist.get("Committer") or "\u2014",
                "commit": (hist.get("CommitHash") or "")[:8],
                "dwell_h": None,
            }
        )
        prev_status = status

    # Second pass: dwell time in each status is the gap until the next
    # transition. The final stop is the bead's current state -- its dwell is
    # open-ended, so we leave it None rather than measuring against "now".
    for i in range(len(stops) - 1):
        start = _parse_dt(stops[i]["when"])
        end = _parse_dt(stops[i + 1]["when"])
        if start is not None and end is not None and end >= start:
            stops[i]["dwell_h"] = round((end - start).total_seconds() / 3600.0, 1)

    return stops
