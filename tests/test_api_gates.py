"""Route tests for GET /api/gates (the coordination strip partial).

Coordination renders as a SECOND epic-lane-style strip on the board
(bdboard-xiwd, reverting the dedicated /coordination tab bdboard-wr85). The
underlying gate/slot derivation and the /api/gates route are unchanged; only
the presentation moved back onto the board as chips.

We invoke the endpoint coroutine directly with a minimal ASGI Request and
assert on the rendered HTML. bd.list_gates / bd.show_long and
store.snapshot_active are stubbed so no real subprocess runs.

Covers the bead's acceptance criteria:
  - the strip lists open gates as chips carrying their await type
  - a merge-slot renders as a chip with its held/available state + holder
  - chips open the bead modal (#bead-modal); the strip reuses the .epic-chip idiom
  - the strip hides when there is no coordination state (hidden-when-empty)
  - bd verb failures degrade gracefully (inline message, not 500)
"""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/gates",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _stub(
    monkeypatch,
    *,
    gates: Any = None,
    active: list | None = None,
    show_long_map: dict | None = None,
    repo_url: str | None = None,
) -> None:
    async def fake_list_gates() -> Any:
        if isinstance(gates, Exception):
            raise gates
        return gates or []

    async def fake_snapshot_active() -> list:
        return active or []

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        full = (show_long_map or {}).get(bead_id)
        return full, None

    monkeypatch.setattr(app_module.bd, "list_gates", fake_list_gates)
    monkeypatch.setattr(app_module.store, "snapshot_active", fake_snapshot_active)
    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: repo_url)


def _call() -> tuple[int, str]:
    resp = asyncio.run(app_module.api_gates(_request()))
    return resp.status_code, resp.body.decode()


# ----- gates listing -----


def test_lists_open_gate_as_chip_with_await_type(monkeypatch):
    """AC1: the strip lists open gates as chips carrying their await type."""
    _stub(
        monkeypatch,
        repo_url="https://github.com/owner/repo",
        gates=[
            {
                "id": "gt-1",
                "title": "Gate: gh:pr",
                "issue_type": "gate",
                "await_type": "gh:pr",
                "await_id": "42",
                "created_at": "2026-06-07T00:00:00Z",
            }
        ],
    )

    status, body = _call()

    assert status == 200
    # Rendered as a second epic-lane-style strip with a Coordination label.
    assert "coordination-lane" in body
    assert "Coordination" in body
    # The gate is a chip reusing the epic-chip idiom.
    assert "epic-chip" in body
    assert "gt-1" in body
    # The interpreted await type rides the chip as a badge (not a raw scalar).
    assert "gate-await-badge" in body
    assert "gh:pr" in body
    # Chips open the bead modal like the epic chips do.
    assert 'hx-target="#bead-modal"' in body
    assert 'hx-get="/api/bead/gt-1"' in body


def test_strip_hides_when_no_coordination_state(monkeypatch):
    """A board with no gates and no merge-slots renders nothing (hidden)."""
    _stub(monkeypatch, gates=[], active=[])
    status, body = _call()
    assert status == 200
    assert "coordination-lane" not in body
    assert body.strip() == ""


# ----- merge-slot affordance -----


def test_merge_slot_held_renders_as_chip_with_holder(monkeypatch):
    """AC2: a held merge-slot renders as a chip with its state + holder."""
    slot_list_bead = {"id": "x-merge-slot", "labels": ["gt:slot"], "status": "in_progress"}
    slot_full = {
        "id": "x-merge-slot",
        "title": "merge slot",
        "labels": ["gt:slot"],
        "status": "in_progress",
        "metadata": {"holder": "agent-7", "waiters": ["agent-3", "agent-9"]},
    }
    _stub(
        monkeypatch,
        gates=[],
        active=[slot_list_bead],
        show_long_map={"x-merge-slot": slot_full},
    )

    status, body = _call()

    assert status == 200
    assert "coordination-lane" in body
    assert "x-merge-slot" in body
    assert "merge-slot-state-held" in body
    assert "held by agent-7" in body
    # Not a raw JSON dump of metadata.
    assert "field-json" not in body


def test_merge_slot_available_renders_free(monkeypatch):
    slot = {
        "id": "x-merge-slot",
        "title": "merge slot",
        "labels": ["gt:slot"],
        "status": "open",
        "metadata": {},
    }
    _stub(
        monkeypatch,
        gates=[],
        active=[slot],
        show_long_map={"x-merge-slot": slot},
    )

    status, body = _call()

    assert status == 200
    assert "merge-slot-state-available" in body
    assert "free to acquire" in body


def test_merge_slot_contended_shows_waiter_count(monkeypatch):
    """An available-but-contended slot reports its waiter count on the chip."""
    slot = {
        "id": "x-merge-slot",
        "title": "merge slot",
        "labels": ["gt:slot"],
        "status": "open",
        "metadata": {"waiters": ["agent-3", "agent-9"]},
    }
    _stub(
        monkeypatch,
        gates=[],
        active=[slot],
        show_long_map={"x-merge-slot": slot},
    )

    status, body = _call()

    assert status == 200
    assert "merge-slot-state-available" in body
    assert "2 waiting" in body


# ----- graceful degradation -----


def test_gate_list_failure_degrades_inline_not_500(monkeypatch):
    """AC3: a bd gate list failure renders an inline message, not a 500."""
    _stub(monkeypatch, gates=RuntimeError("bd exploded"), active=[])

    status, body = _call()

    assert status == 200
    # The strip still renders (so the error is visible) with an inline message.
    assert "coordination-lane" in body
    assert "coordination-error-flag" in body
    assert "try again" in body.lower()


# ----- modal: merge-slot field kind (field_row.html) -----


def _modal_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/bead/x-merge-slot",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def test_modal_renders_merge_slot_affordance(monkeypatch):
    """AC2 (modal): a gt:slot bead renders the held/holder/queue affordance
    ABOVE the raw metadata row, not only as a raw JSON blob."""
    slot = {
        "id": "x-merge-slot",
        "title": "merge slot",
        "labels": ["gt:slot"],
        "status": "in_progress",
        "metadata": {"holder": "agent-7", "waiters": ["agent-3", "agent-9"]},
        "created_at": "2026-06-07T00:00:00Z",
        "updated_at": "2026-06-07T00:00:00Z",
    }

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        return slot, None

    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)

    resp = asyncio.run(app_module.api_bead(_modal_request(), "x-merge-slot"))
    body = resp.body.decode()

    assert resp.status_code == 200
    assert "merge-slot-state-held" in body
    assert "agent-7" in body
    assert "agent-3" in body and "agent-9" in body
    # The raw metadata field is STILL rendered below (anatomy: drop no field).
    assert "field-json" in body
