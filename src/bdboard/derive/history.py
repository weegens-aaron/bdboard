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

# Allowed page sizes for the paginated closed list (bdboard-3jj). The
# user-facing selector offers exactly these; any other value (missing or
# tampered query param) clamps to HISTORY_PAGE_SIZE.
HISTORY_PAGE_SIZES = (25, 50, 100)

# Default page size for the paginated closed list (bdboard-3jj). Must be a
# member of HISTORY_PAGE_SIZES.
HISTORY_PAGE_SIZE = 50


def clamp_page_size(value: Any) -> int:
    """Coerce an arbitrary page_size input to the allowed set (bdboard-3jj).

    Returns ``value`` when it parses to a member of
    :data:`HISTORY_PAGE_SIZES`; otherwise falls back to
    :data:`HISTORY_PAGE_SIZE` (50). This is the single source of truth for
    page-size validation so the API endpoint and any caller agree on the
    same default-on-invalid behaviour rather than each re-implementing it.
    """
    try:
        size = int(value)
    except (TypeError, ValueError):
        return HISTORY_PAGE_SIZE
    return size if size in HISTORY_PAGE_SIZES else HISTORY_PAGE_SIZE


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


def _created_in_window(
    beads: list[dict[str, Any]], cutoff: datetime | None
) -> list[dict[str, Any]]:
    """Beads whose created_at is >= cutoff (all when cutoff is None).

    The 'beads created' counterpart to :func:`_closed_in_window`: where the
    closed/throughput view filters by ``closed_at``, this filters by
    ``created_at``. Status is irrelevant: a still-*open* bead filed in the
    window counts just as much as one that has since closed. Beads with no
    parseable ``created_at`` are excluded - they cannot be placed on a
    timeline.
    """
    out: list[dict[str, Any]] = []
    for b in beads:
        created = _parse_dt(b.get("created_at"))
        if created is None:
            continue
        if cutoff is not None and created < cutoff:
            continue
        out.append(b)
    return out


def created(
    beads: list[dict[str, Any]],
    range_key: str = DEFAULT_HISTORY_RANGE,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Beads-created-per-day series within a range (mirrors :func:`throughput`).

    Buckets ``created_at`` by local calendar day (:func:`_day_bucket`) and
    returns a gap-free ascending series
    ``[{\"day\": \"YYYY-MM-DD\", \"count\": int}, ...]`` spanning the first
    through last day that has a creation in the window. Days with zero
    creations inside that span are filled with ``count=0`` so the chart reads
    as a continuous timeline rather than a jagged one. Status is irrelevant
    (an open bead filed in-window still counts), which is exactly the
    complement to :func:`throughput`: created answers 'how much did we file?',
    throughput answers 'how much did we finish?'. Returns ``[]`` when nothing
    was created in the window. Pure over the snapshot - no extra I/O.
    """
    cutoff = _range_to_cutoff(range_key, now=now)
    windowed = _created_in_window(beads, cutoff)
    buckets: dict[str, int] = defaultdict(int)
    for b in windowed:
        day = _day_bucket(b.get("created_at"))
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
