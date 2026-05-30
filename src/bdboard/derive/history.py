"""History page derivations (bdboard-rrc design §4).

All pure functions over the existing list_all snapshot — no new bd call,
no persistence. They power the long-window History page (the complement
to the board's 12h/1d/3d lane filter and 50-cap closed lane).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from bdboard.derive.lanes import _is_closed
from bdboard.derive.timeutil import _day_bucket, _epoch, _parse_dt

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
