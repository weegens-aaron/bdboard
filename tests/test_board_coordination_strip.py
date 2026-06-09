"""Tests for Coordination-as-a-board-strip (bdboard-xiwd).

Coordination was reverted off its own /coordination tab (bdboard-wr85) and its
nav count badge (bdboard-iz8h) back onto the board, presented as a SECOND
epic-lane-style strip below the "Epics in flight" strip. These tests guard the
revert: the nav no longer references coordination, the removed routes are gone,
and the board carries the #coordination strip region wired to /api/gates.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from starlette.requests import Request

from bdboard import app as app_module

TEMPLATES = Path("src/bdboard/templates")


def _request(path: str = "/") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


# ----- nav no longer references coordination -----


def test_nav_has_no_coordination_link_or_badge() -> None:
    """The shared nav partial drops the Coordination tab + its count badge.

    We assert on the rendered wiring (the clickable link, the badge slot, and
    the count endpoint), not on comment mentions — the partial's doc comment
    legitimately documents the revert history.
    """
    html = (TEMPLATES / "partials" / "nav.html").read_text(encoding="utf-8")
    assert 'href="/coordination"' not in html
    assert "mh-link-badge-slot" not in html
    assert "/api/coordination/count" not in html
    # No clickable Coordination nav link text.
    assert ">Coordination<" not in html


def test_nav_still_has_the_three_primary_tabs() -> None:
    """Board / Analytics / Memory remain the primary nav tabs."""
    html = (TEMPLATES / "partials" / "nav.html").read_text(encoding="utf-8")
    assert 'href="/"' in html and ">Board<" in html
    assert 'href="/analytics"' in html and ">Analytics<" in html
    assert 'href="/memory"' in html and ">Memory<" in html


def test_board_index_nav_has_no_coordination() -> None:
    """End-to-end: the rendered board page nav carries no coordination tab."""
    resp = asyncio.run(app_module.index(_request("/")))
    body = resp.body.decode()
    assert 'href="/coordination"' not in body
    assert "mh-link-badge-slot" not in body


# ----- removed routes -----


def test_coordination_page_route_is_removed() -> None:
    """The /coordination full-page route no longer exists on the app."""
    paths = {getattr(r, "path", None) for r in app_module.app.routes}
    assert "/coordination" not in paths


def test_coordination_count_route_is_removed() -> None:
    """The /api/coordination/count badge endpoint no longer exists."""
    paths = {getattr(r, "path", None) for r in app_module.app.routes}
    assert "/api/coordination/count" not in paths


def test_coordination_count_helper_is_removed() -> None:
    """derive.coordination_count was removed with the badge (YAGNI)."""
    from bdboard import derive

    assert not hasattr(derive, "coordination_count")


# ----- board carries the coordination strip region -----


def test_lanes_partial_has_coordination_strip_region() -> None:
    """The board's lanes partial carries the #coordination strip region wired
    to /api/gates with the live load + SSE refresh triggers, placed below the
    epics strip (a SECOND epic-lane-style strip)."""
    html = (TEMPLATES / "partials" / "lanes.html").read_text(encoding="utf-8")
    assert 'id="coordination"' in html
    assert 'hx-get="/api/gates"' in html
    assert 'hx-trigger="load, refresh from:body"' in html
    # It sits AFTER the "Epics in flight" strip (a second strip), and BEFORE
    # the main lanes grid.
    epics_idx = html.find("Epics in flight")
    coord_idx = html.find('id="coordination"')
    lanes_idx = html.find('<div class="lanes">')
    assert epics_idx != -1 and coord_idx != -1 and lanes_idx != -1
    assert epics_idx < coord_idx < lanes_idx


def test_obsolete_templates_are_gone() -> None:
    """The dedicated page + badge + disclosure-panel partials were deleted."""
    assert not (TEMPLATES / "coordination.html").exists()
    assert not (TEMPLATES / "partials" / "coordination_badge.html").exists()
    assert not (TEMPLATES / "partials" / "gates_panel.html").exists()
    # The replacement strip partial exists.
    assert (TEMPLATES / "partials" / "coordination_lane.html").exists()
