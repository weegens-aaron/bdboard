"""Gate (async-coordination) derivations from raw bead snapshots.

A *gate* is a bead (``issue_type == "gate"``) that makes another bead **wait**
on an external/async condition before it becomes runnable. ``bd gate create
--blocks <id>`` produces the gate and wires it to its target by a ``blocks``
edge (gate → target), so the gate itself carries no unmet blocker of its own —
its ``blocks`` edge points *outward*. That is exactly why a naive lane
derivation drops an open gate into the READY lane as claimable work, when it is
in fact a pending wait (audit FB-3 / ``06-gates-coordination.md``).

This module is the single, pure home for the two gate-aware shapings the board
needs:

- :func:`is_gate` — the type predicate (mirrors ``_is_epic`` / ``_is_molecule``
  in :mod:`bdboard.derive.lanes`).
- :func:`gate_condition` — interpret a gate's await fields into a *labelled
  condition* the modal can render as a PR/run link, a timer deadline, or a
  manual-only flag, instead of the raw alphabetical ``await_type`` /
  ``await_id`` / ``timeout`` scalar rows bd emits.

Field shapes (verified against bd v1.0.5 ``ce242a879`` in a ``gt``-prefix
sandbox — ``bd gate create`` of each type, read back via
``bd gate list --json`` / ``bd show --long --json``):

    human   -> {await_type: "human"}                       # no await_id
    timer   -> {await_type: "timer", timeout: <int ns>}    # NOT await_id
    gh:run  -> {await_type: "gh:run", await_id: "<run id>"}
    gh:pr   -> {await_type: "gh:pr",  await_id: "<pr number>"}
    bead    -> {await_type: "bead",   await_id: "<rig>:<bead-id>"}

Note the surprises the audit warned about: ``timer`` carries its deadline as a
``timeout`` integer **in nanoseconds** (Go ``time.Duration``), NOT as
``await_id``; ``human`` carries neither; and ``bead`` gates are manually
resolvable only (cross-rig auto-resolution was removed in bd v1.0.4).

Everything here is a pure function over a bead dict — no I/O, no caching. The
repo base URL needed to build PR / Actions links is resolved by the caller (the
route in ``app.py`` reads the workspace git remote once) and threaded in, so
this module stays trivially testable AND host-agnostic: an enterprise GitHub
host (e.g. ``gecgithub01.walmart.com``) builds correct links exactly like
``github.com`` does, because we never hardcode the host.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from bdboard.derive.timeutil import _parse_dt

# Nanoseconds per second — bd stores a timer gate's `timeout` as a Go
# time.Duration, which serialises to an integer nanosecond count.
_NS_PER_SEC = 1_000_000_000

# The magic label bd stamps on a merge-slot bead. There is exactly one slot
# per rig (`<prefix>-merge-slot`), and it is the only bead carrying this label.
_MERGE_SLOT_LABEL = "gt:slot"


def is_gate(bead: dict[str, Any]) -> bool:
    """True for an async-coordination gate bead (``issue_type == "gate"``)."""
    return (bead.get("issue_type") or "").lower() == "gate"


def is_merge_slot(bead: dict[str, Any]) -> bool:
    """True for a merge-slot mutex bead (carries the ``gt:slot`` label).

    A merge-slot is bd's exclusive-access primitive: a single bead per rig
    (``<prefix>-merge-slot``) that serialises conflict resolution. It is NOT a
    gate (``issue_type`` is whatever bd creates it as, not ``"gate"``) — the
    only reliable discriminator is the ``gt:slot`` label, so we match on that
    rather than on type or id-suffix (id prefix varies per rig).
    """
    labels = bead.get("labels") or []
    if not isinstance(labels, list):
        return False
    return _MERGE_SLOT_LABEL in labels


def _coerce_metadata(raw: Any) -> dict[str, Any]:
    """Return a metadata mapping from bd's ``metadata`` field, or ``{}``.

    bd usually emits ``metadata`` as a JSON object, but a defensive parse keeps
    the affordance from crashing on a stringified payload or an unexpected
    shape — graceful degradation is the whole point of this module.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _coerce_waiters(raw: Any) -> list[str]:
    """Normalise ``metadata.waiters`` into an ordered list of waiter labels.

    bd stores the waiter queue as a priority-ordered list. Each entry may be a
    bare string (a worker address) or a small dict (e.g. ``{"actor": ...}`` /
    ``{"holder": ...}`` / ``{"id": ...}``); we render a human label for either
    so the queue is never a raw JSON blob. Order is preserved verbatim (bd's
    queue is already priority-ordered — we don't re-sort).
    """
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            label = entry.strip()
        elif isinstance(entry, dict):
            label = str(
                entry.get("actor")
                or entry.get("holder")
                or entry.get("name")
                or entry.get("id")
                or entry
            ).strip()
        else:
            label = str(entry).strip()
        if label:
            out.append(label)
    return out


def merge_slot_view(bead: dict[str, Any]) -> dict[str, Any] | None:
    """Interpret a merge-slot bead into a held/available + waiter-queue view.

    Returns ``None`` for a non-slot bead. For a slot, returns a dict the panel
    and the modal render instead of the raw ``metadata`` JSON blob::

        {
          "id":       "x-merge-slot",
          "held":     True,                 # status == in_progress
          "holder":   "agent-7" | None,     # metadata.holder when held
          "waiters":  ["agent-3", "agent-9"],  # priority-ordered queue
          "waiter_count": 2,
          "state":    "held" | "available",
        }

    Held vs available follows bd's convention: ``status == "in_progress"`` is
    HELD, anything else (notably ``open``) is AVAILABLE. The holder is only
    meaningful while held; an available slot reports ``holder = None`` even if
    a stale ``metadata.holder`` lingers. Pure over the bead dict (no I/O).
    """
    if not is_merge_slot(bead):
        return None

    status = (bead.get("status") or "").lower()
    held = status == "in_progress"
    meta = _coerce_metadata(bead.get("metadata"))
    holder = meta.get("holder")
    holder_str = str(holder).strip() if holder not in (None, "") else None
    waiters = _coerce_waiters(meta.get("waiters"))

    return {
        "id": bead.get("id"),
        "held": held,
        # An available slot has no current holder, regardless of any stale
        # holder value left in metadata.
        "holder": holder_str if held else None,
        "waiters": waiters,
        "waiter_count": len(waiters),
        "state": "held" if held else "available",
    }


def _github_link(repo_url: str | None, await_type: str, await_id: str) -> str | None:
    """Build the PR / Actions URL for a ``gh:pr`` / ``gh:run`` gate, or None.

    ``repo_url`` is a repo *base* URL with no trailing slash, e.g.
    ``https://github.com/owner/repo`` (or an enterprise host like
    ``https://gecgithub01.walmart.com/owner/repo``). Host-agnostic by
    construction: we only append the PR / run path, so an enterprise gate
    links to its own host.

    Returns None (graceful degradation to a plain text condition) when the
    repo base URL is unknown or the await_id is missing — never a half-formed
    URL.
    """
    if not repo_url or not await_id:
        return None
    base = repo_url.rstrip("/")
    if await_type == "gh:pr":
        return f"{base}/pull/{await_id}"
    if await_type == "gh:run":
        return f"{base}/actions/runs/{await_id}"
    return None


def _format_until(deadline: datetime, now: datetime) -> str:
    """Render a coarse 'in 1h 59m' / 'elapsed' relative to ``now``.

    Kept deliberately coarse (hours + minutes, or days for long timers) so a
    timer deadline reads at a glance without implying second-level precision
    the gate check (a poller) doesn't actually offer.
    """
    delta = deadline - now
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "elapsed"
    days, rem = divmod(secs, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes = rem // 60
    if days:
        return f"in {days}d {hours}h" if hours else f"in {days}d"
    if hours:
        return f"in {hours}h {minutes}m" if minutes else f"in {hours}h"
    if minutes:
        return f"in {minutes}m"
    return "in <1m"


def gate_condition(
    bead: dict[str, Any],
    *,
    repo_url: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Interpret a gate's await fields into a labelled, renderable condition.

    Returns ``None`` for a non-gate bead. For a gate, returns a dict the modal
    renders via the ``gate`` field kind:

        {
          "await_type": "gh:pr",                 # raw type (badge/diagnostic)
          "summary":    "Waiting for PR #42 to merge",
          "link":       "https://github.com/o/r/pull/42" | None,
          "link_text":  "PR #42" | None,
          "deadline":   "2026-06-07T07:46:48Z" | None,   # timer only (ISO)
          "until":      "in 2h" | "elapsed" | None,       # timer only
          "manual_only": True,                    # human / bead gates
          "note":       "...caveat..." | None,
        }

    Graceful by construction: an unknown ``await_type``, a missing repo URL,
    or a missing await_id degrade to a plain text summary rather than a crash
    or a broken link — so a future bd gate type never breaks the modal.
    """
    if not is_gate(bead):
        return None

    await_type = (bead.get("await_type") or "").strip().lower()
    await_id = bead.get("await_id")
    await_id_str = str(await_id) if await_id not in (None, "") else None

    cond: dict[str, Any] = {
        "await_type": await_type or "unknown",
        "summary": "",
        "link": None,
        "link_text": None,
        "deadline": None,
        "until": None,
        "manual_only": False,
        "note": None,
    }

    if await_type == "gh:pr":
        cond["link"] = _github_link(repo_url, await_type, await_id_str or "")
        cond["link_text"] = f"PR #{await_id_str}" if await_id_str else None
        cond["summary"] = (
            f"Waiting for PR #{await_id_str} to merge"
            if await_id_str
            else "Waiting for a PR to merge"
        )
        if cond["link"] is None and await_id_str:
            cond["note"] = "Repo unknown — no link built; resolves when the PR merges."

    elif await_type == "gh:run":
        cond["link"] = _github_link(repo_url, await_type, await_id_str or "")
        cond["link_text"] = f"Actions run {await_id_str}" if await_id_str else None
        cond["summary"] = (
            f"Waiting for GitHub Actions run {await_id_str} to succeed"
            if await_id_str
            else "Waiting for a GitHub Actions run to succeed"
        )
        if cond["link"] is None and await_id_str:
            cond["note"] = "Repo unknown — no link built; resolves on run success."

    elif await_type == "timer":
        # bd stores the timeout as a Go time.Duration: an integer nanosecond
        # count under `timeout` (NOT await_id). Deadline = created_at + timeout.
        timeout_ns = bead.get("timeout")
        created = _parse_dt(bead.get("created_at"))
        if isinstance(timeout_ns, (int, float)) and created is not None:
            deadline = created + timedelta(seconds=timeout_ns / _NS_PER_SEC)
            ref = now or datetime.now(UTC)
            cond["deadline"] = deadline.strftime("%Y-%m-%dT%H:%M:%SZ")
            cond["until"] = _format_until(deadline, ref)
            cond["summary"] = f"Auto-resolves {cond['until']}"
        else:
            cond["summary"] = "Auto-resolves after a timer"

    elif await_type == "human":
        cond["manual_only"] = True
        cond["summary"] = "Manual resolution required"
        cond["note"] = "Resolve with `bd gate resolve` once the condition is met."

    elif await_type == "bead":
        # await_id is "<rig>:<bead-id>"; cross-rig auto-resolution was REMOVED
        # in bd v1.0.4, so these are manually resolvable only.
        cond["manual_only"] = True
        cond["link_text"] = await_id_str
        cond["summary"] = (
            f"Waiting on bead {await_id_str}" if await_id_str else "Waiting on another bead"
        )
        cond["note"] = (
            "Cross-rig auto-resolution was removed in bd 1.0.4 — resolve manually "
            "with `bd gate resolve`."
        )

    else:
        # Unknown / future gate type: surface what we have without guessing.
        cond["manual_only"] = True
        label = await_type or "unknown"
        cond["summary"] = f"Waiting on a '{label}' condition"
        if await_id_str:
            cond["link_text"] = await_id_str

    return cond
