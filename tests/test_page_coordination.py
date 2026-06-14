"""Route tests for the dedicated Coordination page (bdboard-wr85).

Coordination (open gates + merge-slot mutexes) was promoted off the board into
its own primary-nav tab at /coordination. The board no longer carries an inline
#coordination region; the dedicated page renders the SAME panel by HTMX-loading
partials/gates_panel.html via /api/gates?standalone=1.

We invoke the endpoint coroutines directly with a minimal ASGI Request and
assert on rendered HTML. An autouse fixture in tests/conftest.py stubs workspace
validation so the happy path is environment-independent; the /api/gates bd calls
are stubbed where the panel content matters.

Covers the bead's acceptance criteria:
  - a Coordination tab appears in the primary nav and routes to /coordination
  - the board no longer renders an inline coordination region
  - /coordination shows gates + merge slots (reusing gates_panel.html) and an
    explicit empty state when there is none
  - live updates wiring (load + refresh from:body) preserved; modal drill-downs
    target #bead-modal
  - nav active-state + aria-current correct
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module

TEMPLATES = Path("src/bdboard/templates")


def _request(path: str = "/coordination", query: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query.encode(),
        "headers": [],
    }
    return Request(scope)


def _call_coordination() -> tuple[int, str]:
    resp = asyncio.run(app_module.page_coordination(_request()))
    return resp.status_code, resp.body.decode()


def _stub_gates(monkeypatch, *, gates: Any = None, active: list | None = None) -> None:
    async def fake_list_gates() -> Any:
        return gates or []

    async def fake_snapshot_active() -> list:
        return active or []

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        return None, None

    monkeypatch.setattr(app_module.bd, "list_gates", fake_list_gates)
    monkeypatch.setattr(app_module.store, "snapshot_active", fake_snapshot_active)
    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)


def _call_api_gates(standalone: bool = False) -> tuple[int, str]:
    resp = asyncio.run(app_module.api_gates(_request("/api/gates"), standalone=standalone))
    return resp.status_code, resp.body.decode()


# ----- /coordination full page -----


def test_coordination_page_renders_full_document() -> None:
    """/coordination returns 200 and extends base.html (full page, not a partial)."""
    status, body = _call_coordination()

    assert status == 200
    assert "<!doctype html>" in body.lower()
    assert "<title>Coordination" in body
    assert 'class="masthead"' in body
    # The HTMX region that hydrates the panel, loading the standalone variant.
    assert 'id="coordination"' in body
    assert 'hx-get="/api/gates?standalone=1"' in body
    # Live updates: load + SSE refresh wiring preserved.
    assert 'hx-trigger="load, refresh from:body"' in body


def test_coordination_is_the_active_nav_tab() -> None:
    """Coordination is the active page (non-colour cue + aria-current)."""
    _, body = _call_coordination()
    assert 'href="/coordination"\n     class="mh-link is-active"' in body
    assert 'aria-current="page"' in body


def test_coordination_nav_link_present_on_other_pages() -> None:
    """The Coordination tab appears in the shared primary nav."""
    resp = asyncio.run(app_module.index(_request("/")))
    body = resp.body.decode()
    assert 'href="/coordination"' in body
    # The link text is now followed by the count-badge slot (bdboard-iz8h),
    # so assert on the text start rather than an immediate </a>.
    assert ">Coordination<" in body


# ----- board no longer carries an inline coordination region -----


def test_board_drops_inline_coordination_region() -> None:
    """The board (dashboard.html) no longer renders a #coordination region."""
    resp = asyncio.run(app_module.index(_request("/")))
    body = resp.body.decode()
    assert 'id="coordination"' not in body
    assert 'hx-get="/api/gates"' not in body


def test_dashboard_template_has_no_coordination_region() -> None:
    """Belt-and-braces: the template source carries no coordination region."""
    html = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="coordination"' not in html


# ----- standalone empty state + populated panel -----


def test_standalone_shows_explicit_empty_state(monkeypatch) -> None:
    """With no gates/slots, the standalone panel shows an explicit empty state
    instead of the board's render-nothing (which would leave the page blank)."""
    _stub_gates(monkeypatch, gates=[], active=[])
    status, body = _call_api_gates(standalone=True)
    assert status == 200
    assert "coordination-empty-state" in body
    assert "coordination-panel" not in body


def test_non_standalone_still_renders_nothing_when_empty(monkeypatch) -> None:
    """The shared partial keeps its hidden-when-empty behaviour off the page."""
    _stub_gates(monkeypatch, gates=[], active=[])
    status, body = _call_api_gates(standalone=False)
    assert status == 200
    assert "coordination-empty-state" not in body
    assert "coordination-panel" not in body


def test_standalone_panel_is_expanded_when_populated(monkeypatch) -> None:
    """When there ARE gates, the standalone panel renders expanded (open) and
    keeps the modal drill-down wiring into gate beads."""
    _stub_gates(
        monkeypatch,
        gates=[
            {
                "id": "gt-1",
                "title": "Gate: manual",
                "issue_type": "gate",
                "await_type": "manual",
            }
        ],
        active=[],
    )
    status, body = _call_api_gates(standalone=True)
    assert status == 200
    assert "coordination-panel-standalone" in body
    assert "<details" in body and " open" in body
    # Modal drill-down into the gate bead is preserved.
    assert 'hx-target="#bead-modal"' in body
    assert "coordination-empty-state" not in body
