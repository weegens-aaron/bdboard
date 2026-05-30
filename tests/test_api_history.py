"""Route tests for GET /api/history (the History swap region partial).

Mirrors tests/test_api_memory.py: we invoke the endpoint coroutine directly
with a minimal ASGI Request and a stubbed store.snapshot so no real bd
subprocess runs. Covers the cases called out in the History design
(docs/design/bdboard-rrc/history-page-design.md §4/§5, bead B):

  - KPI strip (closed in range, median lead time, throughput/day avg)
  - throughput chart bars carry text aria-labels (not colour-only)
  - paginated closed list renders cards that open the bead modal
  - range control mirrors the filter-badge idiom with aria-pressed
  - a bad ?range= degrades to the default window
  - pagination: page 2 shows a "Newer" pager, beyond-end is graceful
  - empty-window state ("try a wider range")
  - result count + KPIs live in aria-live regions
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from starlette.requests import Request

from bdboard import app as app_module

NOW = datetime.now(timezone.utc)


def _request(query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/history",
        "query_string": query_string.encode(),
        "headers": [],
    }
    return Request(scope)


def _iso(days_ago: int, hour: int = 12) -> str:
    dt = NOW.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(
        days=days_ago
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _bead(bead_id, *, days_ago, priority=2, assignee="dev", reason="done"):
    return {
        "id": bead_id,
        "title": f"Bead {bead_id}",
        "status": "closed",
        "priority": priority,
        "assignee": assignee,
        "close_reason": reason,
        "created_at": _iso(days_ago + 1),
        "started_at": _iso(days_ago),
        "closed_at": _iso(days_ago),
    }


def _stub_snapshot(beads):
    async def fake_snapshot():
        return beads

    app_module.store.snapshot = fake_snapshot  # type: ignore[assignment]


def _call(range: str = "30d", page: int = 1) -> tuple[int, str]:
    qs = f"range={range}&page={page}"
    resp = asyncio.run(app_module.api_history(_request(qs), range=range, page=page))
    return resp.status_code, resp.body.decode()


def test_kpi_strip_renders_closed_count_and_labels() -> None:
    _stub_snapshot([_bead("a", days_ago=1), _bead("b", days_ago=2)])

    status, body = _call()

    assert status == 200
    assert "Closed in 30 days" in body
    assert "Median lead time" in body
    assert "Throughput / day" in body
    # KPI strip is in an aria-live region so range changes are announced.
    assert 'aria-live="polite"' in body


def test_throughput_bars_have_text_aria_labels() -> None:
    _stub_snapshot([_bead("a", days_ago=1), _bead("b", days_ago=1)])

    _, body = _call()

    # Bars are not colour-only: each carries an accessible label.
    assert "closed on" in body
    assert 'role="img"' in body


def test_closed_list_cards_open_bead_modal() -> None:
    _stub_snapshot([_bead("xyz", days_ago=3)])

    _, body = _call()

    assert 'hx-get="/api/bead/xyz"' in body
    assert 'hx-target="#bead-modal"' in body
    assert "Bead xyz" in body
    # close_reason is surfaced on the card.
    assert "done" in body


def test_range_control_mirrors_filter_badge_with_aria_pressed() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    _, body = _call(range="7d")

    # The active range button is pressed; the idiom matches the board.
    assert "filter-badge" in body
    assert 'aria-pressed="true"' in body
    assert 'hx-get="/api/history?range=90d&page=1"' in body
    # All four presets are rendered.
    assert 'aria-label="Show history for the last all time"' in body


def test_bad_range_degrades_to_default() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    status, body = _call(range="bogus")

    assert status == 200
    # Falls back to the 30d default window copy.
    assert "Closed in 30 days" in body


def test_pagination_page_two_shows_newer_pager() -> None:
    # 150 closed beads, all within range -> page size 100, so page 2 exists.
    beads = [_bead(f"b{i}", days_ago=1) for i in range(150)]
    _stub_snapshot(beads)

    _, body = _call(page=2)

    assert "Page 2" in body
    # A "Newer" control returns to page 1's neighbour.
    assert "page=1" in body
    assert "Newer" in body


def test_beyond_end_page_is_graceful() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    status, body = _call(page=9)

    assert status == 200
    assert "Nothing on page 9" in body


def test_empty_window_state() -> None:
    # Only an old bead, outside the 7d window.
    _stub_snapshot([_bead("old", days_ago=400)])

    status, body = _call(range="7d")

    assert status == 200
    assert "try a wider range" in body


def test_all_range_includes_old_beads() -> None:
    _stub_snapshot([_bead("old", days_ago=400)])

    status, body = _call(range="all")

    assert status == 200
    assert "Bead old" in body
    assert "Closed in all time" in body


def test_foot_summary_echoes_headline() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    _, body = _call()

    assert "closed in 30 days" in body
    assert "closed/day on average" in body
