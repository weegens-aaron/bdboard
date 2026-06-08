"""Route + wiring tests for the Coordination nav count badge (bdboard-iz8h).

The badge surfaces the number of outstanding coordination items (open gates +
held/contended merge slots) on the Coordination nav tab, so a user knows there
is something to look at WITHOUT opening the tab.

Covered here:
  - GET /api/coordination/count renders a numeric badge ONLY when count > 0
  - the count is derived from the SAME source as the /coordination page
    (_collect_coordination), so it can't drift
  - held/contended merge slots count; an idle available slot does not
  - the badge is screen-reader announced (sr-only sentence) and not colour-only
    (the visible number carries the meaning)
  - a gate-list failure degrades to count 0, not a 500
  - nav.html wires the badge slot with HTMX (load + refresh from:body) so it
    rides the existing SSE refresh pipeline

We invoke the endpoint coroutine directly with a minimal ASGI Request and
assert on rendered HTML. bd.list_gates / bd.show_long and
store.snapshot_active are stubbed so no real subprocess runs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module

TEMPLATES = Path("src/bdboard/templates")


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/coordination/count",
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
) -> None:
    async def fake_list_gates() -> Any:
        if isinstance(gates, Exception):
            raise gates
        return gates or []

    async def fake_snapshot_active() -> list:
        return active or []

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        return (show_long_map or {}).get(bead_id), None

    monkeypatch.setattr(app_module.bd, "list_gates", fake_list_gates)
    monkeypatch.setattr(app_module.store, "snapshot_active", fake_snapshot_active)
    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)


def _call() -> tuple[int, str]:
    resp = asyncio.run(app_module.api_coordination_count(_request()))
    return resp.status_code, resp.body.decode()


# ----- render-nothing when quiet -----


def test_badge_empty_when_no_coordination(monkeypatch) -> None:
    """AC: badge appears only when count > 0; a quiet board shows nothing."""
    _stub(monkeypatch, gates=[], active=[])
    status, body = _call()
    assert status == 200
    assert "mh-link-badge" not in body
    assert body.strip() == ""


# ----- numeric badge when there's work -----


def test_badge_counts_open_gates(monkeypatch) -> None:
    """AC: open gates contribute to the count."""
    _stub(
        monkeypatch,
        gates=[
            {"id": "gt-1", "issue_type": "gate", "await_type": "human"},
            {"id": "gt-2", "issue_type": "gate", "await_type": "human"},
        ],
        active=[],
    )
    status, body = _call()
    assert status == 200
    assert "mh-link-badge" in body
    # The visible number is the signal (not colour-only).
    assert ">2<" in body


def test_badge_is_screen_reader_announced_and_plural(monkeypatch) -> None:
    """AC: badge is SR-announced, not colour-only (sr-only sentence present)."""
    _stub(
        monkeypatch,
        gates=[{"id": f"gt-{i}", "issue_type": "gate", "await_type": "human"} for i in range(3)],
        active=[],
    )
    _, body = _call()
    assert 'class="sr-only"' in body
    assert "3 open coordination items" in body


def test_badge_singular_grammar(monkeypatch) -> None:
    """One item -> singular 'item', not 'items'."""
    _stub(
        monkeypatch,
        gates=[{"id": "gt-1", "issue_type": "gate", "await_type": "human"}],
        active=[],
    )
    _, body = _call()
    assert "1 open coordination item" in body
    assert "1 open coordination items" not in body


# ----- merge slots: held/contended count, idle doesn't -----


def test_badge_counts_held_merge_slot(monkeypatch) -> None:
    slot = {
        "id": "x-merge-slot",
        "labels": ["gt:slot"],
        "status": "in_progress",
        "metadata": {"holder": "agent-7", "waiters": []},
    }
    _stub(monkeypatch, gates=[], active=[slot], show_long_map={"x-merge-slot": slot})
    _, body = _call()
    assert "mh-link-badge" in body
    assert ">1<" in body


def test_badge_ignores_idle_available_slot(monkeypatch) -> None:
    """An available slot with no waiters is idle -> not something to look at."""
    slot = {
        "id": "x-merge-slot",
        "labels": ["gt:slot"],
        "status": "open",
        "metadata": {},
    }
    _stub(monkeypatch, gates=[], active=[slot], show_long_map={"x-merge-slot": slot})
    _, body = _call()
    assert "mh-link-badge" not in body


# ----- graceful degradation -----


def test_gate_list_failure_degrades_to_zero_not_500(monkeypatch) -> None:
    """A bd gate list failure must not 500 the nav; badge just shows nothing."""
    _stub(monkeypatch, gates=RuntimeError("bd exploded"), active=[])
    status, body = _call()
    assert status == 200
    assert "mh-link-badge" not in body


# ----- nav.html wiring (HTMX + SSE pipeline) -----


def test_nav_wires_badge_slot_with_htmx_and_sse() -> None:
    """The badge slot lives in nav.html and rides the existing refresh pipeline."""
    html = (TEMPLATES / "partials" / "nav.html").read_text(encoding="utf-8")
    assert "mh-link-badge-slot" in html
    assert 'hx-get="/api/coordination/count"' in html
    # Same load + SSE refresh trigger as every other live region.
    assert 'hx-trigger="load, refresh from:body"' in html
    # SR announcement of the live count change.
    assert 'aria-live="polite"' in html
