"""Route tests for GET /memory (the full-page memory view) and the shared
masthead nav, per notes/design/bdboard-5p1/memory-view-design.md §3 D3, §5,
§6 (bead C).

We invoke the endpoint coroutine directly with a minimal ASGI Request (no
TestClient/httpx dependency needed) and assert on the rendered HTML. The
page itself shells no bd subprocess (the list region fills lazily via an
HTMX `load` fetch to /api/memory). It does call `_validate_or_warn()` ->
`bd.validate()`, which needs the `bd` binary + a `.beads/` workspace; an
autouse fixture in tests/conftest.py stubs that out so the happy path is
environment-independent (bdboard-e4l). Error-path tests re-stub it explicitly.

Covers:
  - /memory returns 200 and extends base.html (full page, not a partial)
  - search strip carries aria-label="Search memories"
  - search is HTMX-debounced (keyup changed delay:250ms) to /api/memory
  - list region lazy-loads from /api/memory on page load
  - masthead nav links / <-> /memory with aria-current on the active page
  - the dashboard index also renders the shared nav (symmetry)
  - workspace validation failure renders the error page, not an empty view
"""

from __future__ import annotations

import asyncio

from starlette.requests import Request

from bdboard import app as app_module


def _request(path: str = "/memory") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _call_memory() -> tuple[int, str]:
    resp = asyncio.run(app_module.page_memory(_request()))
    return resp.status_code, resp.body.decode()


def _call_index() -> tuple[int, str]:
    resp = asyncio.run(app_module.index(_request("/")))
    return resp.status_code, resp.body.decode()


def test_memory_page_renders_full_document() -> None:
    status, body = _call_memory()

    assert status == 200
    # Extends base.html -> full HTML document, not a bare partial.
    assert "<!doctype html>" in body.lower()
    assert "<title>Memory" in body
    # Masthead is present (symmetric with the dashboard).
    assert 'class="masthead"' in body


def test_memory_page_search_strip_is_labelled() -> None:
    _, body = _call_memory()

    assert 'aria-label="Search memories"' in body
    assert 'role="search"' in body
    # Explicit label associated with the input id.
    assert 'for="memory-q"' in body
    assert 'id="memory-q"' in body


def test_memory_page_search_is_htmx_debounced_to_api_memory() -> None:
    _, body = _call_memory()

    assert 'hx-get="/api/memory"' in body
    assert "keyup changed delay:250ms" in body
    assert 'hx-target="#memory-list"' in body


def test_memory_page_list_region_lazy_loads() -> None:
    _, body = _call_memory()

    assert 'id="memory-list"' in body
    # The list region pulls its content from /api/memory on load, and
    # refreshes on SSE 'refresh' events for live invalidation.
    assert 'hx-trigger="load, refresh from:body"' in body


def test_memory_page_nav_links_both_surfaces() -> None:
    _, body = _call_memory()

    assert 'aria-label="Primary"' in body
    assert 'href="/"' in body
    assert 'href="/memory"' in body
    # Memory is the active page here.
    assert 'aria-current="page"' in body
    assert 'href="/memory"\n     class="mh-link is-active"' in body


def test_dashboard_renders_shared_nav() -> None:
    status, body = _call_index()

    assert status == 200
    # Same nav chrome appears on the dashboard, with Board active.
    assert 'aria-label="Primary"' in body
    assert 'href="/memory"' in body
    assert 'aria-current="page"' in body
    assert 'href="/"\n     class="mh-link is-active"' in body


def test_memory_page_surfaces_workspace_error(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_validate_or_warn", lambda: "bd not found")

    resp = asyncio.run(app_module.page_memory(_request()))

    assert resp.status_code == 500
    assert "bd not found" in resp.body.decode()
