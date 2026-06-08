"""Route tests for GET /history after the Analytics migration (bdboard-ove7).

History used to be a standalone full page at /history. It is now the FIRST
sub-view inside the Analytics tab; /history is a thin redirect to
/analytics?view=history so old links / bookmarks don't break. The full-page
behaviour (masthead, lazy #history-region, nav active-state, SSE wiring) now
lives on the Analytics page and is covered by test_page_analytics.py.

We invoke the endpoint coroutine directly with a minimal ASGI Request (no
TestClient/httpx dependency needed) and assert on the response.
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


def test_history_redirects_into_analytics() -> None:
    """/history redirects to the Analytics History sub-view (no broken links)."""
    resp = asyncio.run(app_module.page_history(_request()))

    # A redirect, not a rendered page.
    assert resp.status_code == 307
    assert resp.headers["location"] == "/analytics?view=history"


def test_history_redirect_is_temporary_not_permanent() -> None:
    """307 (temporary) keeps the redirect un-cached so the canonical path can
    change again later, and preserves the request method."""
    resp = asyncio.run(app_module.page_history(_request()))

    assert resp.status_code == 307  # not 301/308 (permanent)
