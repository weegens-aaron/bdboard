"""Timestamp parsing & humanization helpers shared by the derive package.

All pure functions over ISO-8601 strings — no I/O, no caching. Kept in their
own module so both the lane derivations and the history derivations can lean
on a single, well-tested time toolkit without importing each other.
"""

from __future__ import annotations

from datetime import UTC, datetime


def _epoch(ts: str | None) -> float:
    """Parse an ISO timestamp (with optional Z) to a float epoch. 0 on miss."""
    if not ts:
        return 0.0
    try:
        s = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return 0.0


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
        dt = dt.replace(tzinfo=UTC)
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


def humanize_ts(ts: str | None) -> str:
    """Render an ISO timestamp as e.g. '14m ago' / '2h ago' / 'May 19'."""
    if not ts:
        return "—"
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return ts
    delta = datetime.now(UTC) - dt
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
