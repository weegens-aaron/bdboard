"""Route tests for GET /history (the full-page History view), the new third
masthead nav entry, and the SSE re-fetch wiring, per
docs/design/bdboard-rrc/history-page-design.md §4/D4/D7 (bead C, bdboard-7ib).

We invoke the endpoint coroutine directly with a minimal ASGI Request (no
TestClient/httpx dependency needed) and assert on the rendered HTML. The page
itself shells no bd subprocess (the #history-region fills lazily via an HTMX
`load` fetch to /api/history), so no stubbing is required for the happy path.

Covers:
  - /history returns 200 and extends base.html (full page, not a partial)
  - the #history-region lazy-loads from /api/history on page load
  - the region re-fetches on SSE `refresh` events (D7 live update)
  - masthead nav now has a THIRD entry (History) with aria-current active
  - Board / History / Memory all reachable from the shared nav
  - the dashboard + memory pages also render the new History entry (symmetry)
  - workspace validation failure renders the error page, not an empty view
"""

from __future__ import annotations

import asyncio

from starlette.requests import Request

from bdboard import app as app_module


def _request(path: str = "/history") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _call_history() -> tuple[int, str]:
    resp = asyncio.run(app_module.page_history(_request()))
    return resp.status_code, resp.body.decode()


def _call_memory() -> tuple[int, str]:
    resp = asyncio.run(app_module.page_memory(_request("/memory")))
    return resp.status_code, resp.body.decode()


def _call_index() -> tuple[int, str]:
    resp = asyncio.run(app_module.index(_request("/")))
    return resp.status_code, resp.body.decode()


def test_history_page_renders_full_document() -> None:
    status, body = _call_history()

    assert status == 200
    # Extends base.html -> full HTML document, not a bare partial.
    assert "<!doctype html>" in body.lower()
    assert "<title>History" in body
    # Masthead is present (symmetric with the dashboard + memory).
    assert 'class="masthead"' in body


def test_history_region_lazy_loads_from_api_history() -> None:
    _, body = _call_history()

    assert 'id="history-region"' in body
    assert 'hx-get="/api/history"' in body
    assert 'hx-swap="innerHTML"' in body


def test_history_region_refetches_on_sse_refresh() -> None:
    _, body = _call_history()

    # D7: inherit the board's SSE pipeline — load on first paint, then
    # re-fetch whenever the watcher fires a `refresh` event on <body>.
    assert 'hx-trigger="load, refresh from:body"' in body


def test_history_page_has_third_nav_entry_active() -> None:
    _, body = _call_history()

    assert 'aria-label="Primary"' in body
    # All three surfaces are reachable from the shared nav.
    assert 'href="/"' in body
    assert 'href="/history"' in body
    assert 'href="/memory"' in body
    # History is the active page here (non-colour cue + aria-current).
    assert 'href="/history"\n     class="mh-link is-active"' in body
    assert 'aria-current="page"' in body


def test_dashboard_renders_history_nav_entry() -> None:
    status, body = _call_index()

    assert status == 200
    # The new History entry appears on the board too (DRY shared nav),
    # but it is NOT the active page there.
    assert 'href="/history"' in body
    assert 'href="/"\n     class="mh-link is-active"' in body


def test_memory_page_renders_history_nav_entry() -> None:
    status, body = _call_memory()

    assert status == 200
    # The new History entry appears on the memory surface too (symmetry).
    assert 'href="/history"' in body
    assert 'href="/memory"\n     class="mh-link is-active"' in body


def test_history_page_surfaces_workspace_error(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_validate_or_warn", lambda: "bd not found")

    resp = asyncio.run(app_module.page_history(_request()))

    assert resp.status_code == 500
    assert "bd not found" in resp.body.decode()
