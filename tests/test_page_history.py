"""Route tests for GET /history (the full-page History view), the new third
masthead nav entry, and the SSE re-fetch wiring, per
docs/design/bdboard-rrc/history-page-design.md §4/D4/D7 (bead C, bdboard-7ib).

We invoke the endpoint coroutine directly with a minimal ASGI Request (no
TestClient/httpx dependency needed) and assert on the rendered HTML. The page
itself shells no bd subprocess (the #history-region fills lazily via an HTMX
`load` fetch to /api/history). It does, however, call `_validate_or_warn()` ->
`bd.validate()`, which requires the `bd` binary + a `.beads/` workspace; an
autouse fixture in tests/conftest.py stubs that out so the happy path is
environment-independent (bdboard-e4l). Error-path tests re-stub it explicitly.

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


def test_head_script_never_derefs_document_body(monkeypatch) -> None:
    """Regression for bdboard-src: the Custom date-range toggle did nothing.

    The custom-range disclosure (and the page-size persistence + configRequest
    listeners) are delegated from an inline <script> that lives in the page
    <head>. While the head is parsing, ``document.body`` is still ``null``, so
    any ``document.body.addEventListener(...)`` there throws a TypeError that
    aborts the rest of the <script> block — leaving the Custom toggle's click
    listener unregistered, so clicking 'Custom' produced no response.

    Guard: the markup BEFORE </head> must not reference ``document.body``.
    Delegating off ``document`` (always present, still sees bubbled events) is
    the fix; this test fails if anyone reintroduces the null-deref.
    """
    _, body = _call_history()

    head, sep, _rest = body.partition("</head>")
    assert sep, "expected a </head> in the rendered page"
    assert "document.body.addEventListener" not in head, (
        "head-script must delegate from `document`, not `document.body` "
        "(null at head-parse time) — see bdboard-src"
    )


def test_custom_toggle_disclosure_is_wired(monkeypatch) -> None:
    """bdboard-src: the Custom toggle + its delegated click handler must ship.

    The toggle is JS-only (no HTMX fallback), so the disclosure JS that flips
    the form's [hidden]/aria-expanded must be present and keyed off the
    toggle's id.
    """
    _, body = _call_history()

    # The handler is delegated from `document` and matches the toggle by id.
    assert "document.addEventListener('click'" in body
    assert "history-custom-toggle" in body
    assert "history-custom-range" in body
