"""Shape epic-rollup + swarm-coordination views from bd payloads (audit FB-10).

Three bd commands feed the epic/swarm surfaces; this module turns their raw
JSON into template-friendly dicts so the route handlers stay thin and the
shapes are unit-testable without a live bd:

- :func:`epic_rollup` — ``bd mol progress <id>`` -> the count/progress badge
  the epic strip stamps back onto the parent epic (formulas#2).
- :func:`swarm_view`  — ``bd swarm status <id>`` + ``bd swarm validate <id>``
  merged into one view: progress %, the Completed/Active/Ready/Blocked
  cohorts (swarms#2), and the Wave model with max parallelism (swarms#3).

Like the rest of :mod:`bdboard.derive`, these are pure functions with no I/O —
they only reshape dicts the caller already fetched.
"""

from __future__ import annotations

from typing import Any


def _round_percent(value: Any) -> int:
    """Coerce bd's float percent (e.g. 71.4285…) to a clamped 0–100 int.

    bd emits ``percent`` / ``progress_percent`` as a raw float. The badge wants
    a tidy integer; a missing / non-numeric value degrades to 0 rather than
    raising so a partial payload still renders.
    """
    try:
        pct = round(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, pct))


def _int(value: Any) -> int:
    """Coerce a bd count to int, defaulting to 0 for missing/garbage values."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def epic_rollup(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    """Shape ``bd mol progress`` output into the epic-strip rollup badge.

    Returns ``{total, completed, in_progress, percent}`` (percent a 0–100 int),
    or ``None`` when there is nothing to roll up — a payload that is missing /
    not a dict, or reports zero children (``total <= 0``). Returning ``None``
    lets the template skip the badge entirely for childless epics rather than
    rendering a meaningless ``0/0``.
    """
    if not isinstance(progress, dict):
        return None
    total = _int(progress.get("total"))
    if total <= 0:
        return None
    return {
        "total": total,
        "completed": _int(progress.get("completed")),
        "in_progress": _int(progress.get("in_progress")),
        "percent": _round_percent(progress.get("percent")),
    }


def _cohort(items: Any) -> list[dict[str, Any]]:
    """Normalise a swarm-status cohort list into ``{id, title, assignee}`` dicts.

    bd may serialise an empty cohort as ``null`` (not ``[]``); non-list shapes
    and non-dict members are dropped defensively so a malformed payload yields
    an empty cohort rather than blowing up the panel.
    """
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(
            {
                "id": it.get("id"),
                "title": it.get("title"),
                "assignee": it.get("assignee"),
                "closed_at": it.get("closed_at"),
            }
        )
    return out


def _waves(ready_fronts: Any) -> list[dict[str, Any]]:
    """Shape ``swarm validate``'s ``ready_fronts`` into legible wave rows.

    Each front becomes ``{wave, size, issues}`` where ``wave`` is bumped to a
    human 1-based number (bd numbers waves from 0) and ``issues`` zips the
    parallel ``issues`` ids with their ``titles`` into ``{id, title}`` pairs.
    A null/empty ``ready_fronts`` (a fully-closed or non-swarmable epic) yields
    an empty list.
    """
    if not isinstance(ready_fronts, list):
        return []
    out: list[dict[str, Any]] = []
    for front in ready_fronts:
        if not isinstance(front, dict):
            continue
        ids = front.get("issues") if isinstance(front.get("issues"), list) else []
        titles = front.get("titles") if isinstance(front.get("titles"), list) else []
        issues = [
            {"id": ids[i], "title": titles[i] if i < len(titles) else None} for i in range(len(ids))
        ]
        out.append(
            {
                # bd numbers waves from 0; show a human 1-based "Wave N".
                "wave": _int(front.get("wave")) + 1,
                "size": len(issues),
                "issues": issues,
            }
        )
    return out


def _messages(value: Any) -> list[str]:
    """Normalise bd's null-or-list errors/warnings field into a list of str."""
    if not isinstance(value, list):
        return []
    return [str(m) for m in value if m]


def swarm_view(
    status: dict[str, Any] | None,
    validate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge ``swarm status`` + ``swarm validate`` into one panel view.

    Either input may be ``None`` (its bd call failed); the view degrades to
    whatever is available so a status-only or validate-only panel still
    renders. The returned dict carries:

    - ``epic_id`` / ``epic_title`` (from whichever payload has them)
    - ``progress_percent`` (0–100 int) and ``total``
    - ``completed`` / ``active`` / ``ready`` / ``blocked`` cohort lists plus
      their ``*_count`` companions (swarms#2)
    - ``swarmable``, ``max_parallelism``, ``estimated_sessions`` and the
      ``waves`` model (swarms#3)
    - ``errors`` / ``warnings`` (normalised null -> [])
    - ``has_status`` / ``has_validate`` flags so the template can show partial
      degradation messaging.
    """
    status = status if isinstance(status, dict) else None
    validate = validate if isinstance(validate, dict) else None

    completed = _cohort((status or {}).get("completed"))
    active = _cohort((status or {}).get("active"))
    ready = _cohort((status or {}).get("ready"))
    blocked = _cohort((status or {}).get("blocked"))

    epic_id = (status or {}).get("epic_id") or (validate or {}).get("epic_id")
    epic_title = (status or {}).get("epic_title") or (validate or {}).get("epic_title")

    return {
        "epic_id": epic_id,
        "epic_title": epic_title,
        "has_status": status is not None,
        "has_validate": validate is not None,
        "progress_percent": _round_percent((status or {}).get("progress_percent")),
        "total": _int((status or {}).get("total_issues") or (validate or {}).get("total_issues")),
        "completed": completed,
        "active": active,
        "ready": ready,
        "blocked": blocked,
        "completed_count": _int((status or {}).get("completed_count")) or len(completed),
        "active_count": _int((status or {}).get("active_count")) or len(active),
        "ready_count": _int((status or {}).get("ready_count")) or len(ready),
        "blocked_count": _int((status or {}).get("blocked_count")) or len(blocked),
        "swarmable": bool((validate or {}).get("swarmable")),
        "max_parallelism": _int((validate or {}).get("max_parallelism")),
        "estimated_sessions": _int((validate or {}).get("estimated_sessions")),
        "waves": _waves((validate or {}).get("ready_fronts")),
        "errors": _messages((validate or {}).get("errors")),
        "warnings": _messages((validate or {}).get("warnings")),
    }
