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
from datetime import UTC, datetime, timedelta

from starlette.requests import Request

from bdboard import app as app_module

NOW = datetime.now(UTC)


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
    dt = NOW.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
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
        "updated_at": _iso(days_ago),
    }


def _stub_snapshot(beads):
    async def fake_snapshot():
        return beads

    app_module.store.snapshot = fake_snapshot  # type: ignore[assignment]


def _call(range: str = "30d", page: int = 1, page_size: int | None = None) -> tuple[int, str]:
    qs = f"range={range}&page={page}"
    if page_size is not None:
        qs += f"&page_size={page_size}"
    resp = asyncio.run(
        app_module.api_history(_request(qs), range=range, page=page, page_size=page_size)
    )
    return resp.status_code, resp.body.decode()


def test_masthead_stats_present_foot_summary_absent() -> None:
    # bdboard-9jt: the header/masthead KPI stats strip is RESTORED (it was
    # over-removed alongside the bottom foot summary by bdboard-2qf). The
    # masthead stats <dl> must come back as an hx-swap-oob fragment with its
    # labels, while the bottom-of-page foot summary ("N closed/day on average")
    # stays removed. A stubbed bd_summary populates the 'via bd' Total/Closed
    # cells to prove the graceful headline path renders when bd is available.
    async def fake_summary():
        return {"total_issues": 5, "closed_issues": 3}

    app_module.store.bd.status_summary = fake_summary  # type: ignore[assignment]
    _stub_snapshot([_bead("a", days_ago=1), _bead("b", days_ago=2)])

    _, body = _call()

    # Masthead stats surface IS back: OOB fragment, host id, stat labels/icons.
    assert "history-stats" in body
    assert 'hx-swap-oob="true"' in body
    assert "stat-info" in body
    for label in ("Avg lead", "Median lead", "Throughput", "Closed (range)"):
        assert label in body
    # The 'via bd' workspace totals render when bd_summary is available.
    assert "Total" in body

    # The bottom foot summary stays removed (bdboard-2qf intent preserved).
    assert "history-foot-summary" not in body
    assert "closed/day on average" not in body


def test_masthead_stats_degrade_without_bd_summary() -> None:
    # bdboard-9jt: the masthead must degrade gracefully when bd's status
    # summary is unavailable (status_summary returns None). The range-derived
    # KPIs still render; only the optional 'via bd' Total/Closed cells drop.
    async def fake_summary():
        return None

    app_module.store.bd.status_summary = fake_summary  # type: ignore[assignment]
    _stub_snapshot([_bead("a", days_ago=1), _bead("b", days_ago=2)])

    _, body = _call()

    # The strip still renders with the range-derived KPIs.
    assert "history-stats" in body
    assert 'hx-swap-oob="true"' in body
    for label in ("Avg lead", "Median lead", "Throughput", "Closed (range)"):
        assert label in body
    # Foot summary stays gone regardless of bd availability.
    assert "history-foot-summary" not in body
    assert "closed/day on average" not in body


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
    assert 'hx-get="/api/history?range=90d&page=1&page_size=50"' in body
    # All four presets are rendered.
    assert 'aria-label="Show history for the last all time"' in body


def test_bad_range_degrades_to_default() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    status, body = _call(range="bogus")

    assert status == 200
    # Falls back to the 30d default window: the range control marks 30d active.
    assert 'aria-pressed="true"' in body
    assert 'hx-get="/api/history?range=30d&page=1&page_size=50"' in body


def test_pagination_page_two_shows_newer_pager() -> None:
    # 150 closed beads, all within range -> default page size 50, so page 2
    # exists.
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
    # The 'all' range button is the active one.
    assert 'hx-get="/api/history?range=7d&page=1&page_size=50"' in body


def test_closed_list_renders_within_range() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    _, body = _call()

    # The closed bead surfaces in the paginated list (no KPI strip needed).
    assert "Bead a" in body


def test_created_chart_renders_with_text_aria_labels() -> None:
    # Combined chart (bdboard-ijd): created AND closed share one strip. An
    # OPEN bead filed in-window must register on the created series even
    # though it never closed.
    open_bead = {
        "id": "open1",
        "title": "Bead open1",
        "status": "open",
        "priority": 1,
        "created_at": _iso(3),
        "updated_at": _iso(1),
    }
    _stub_snapshot([_bead("a", days_ago=1), open_bead])

    status, body = _call()

    assert status == 200
    # The unified chart names both series via the legend, not two sections.
    assert "Created vs closed" in body
    assert "history-legend" in body
    # Bars are not colour-only: each day pair carries an accessible label
    # conveying both counts.
    assert "created," in body
    assert "closed on" in body
    # The created bars use the dedicated (hatched) variant class.
    assert "throughput-bar-created" in body
    # The closed series carries its explicit variant class too.
    assert "throughput-bar-closed" in body
    # One combined chart container, not two stacked strips.
    assert "throughput-chart-combined" in body
    assert "history-created" not in body


def test_combined_chart_shows_per_day_counts_and_baseline_columns() -> None:
    """Regression for bdboard-oey: the combine dropped the per-day count
    labels and let bars hang upside-down from the top. The fix restores a
    per-series .throughput-col (bottom-aligned, so bars grow UP from the
    baseline) each carrying a visible .throughput-count."""
    # Two beads closed the same day -> a closed count of 2 must surface as a
    # visible per-day label, not just the legend total.
    _stub_snapshot([_bead("a", days_ago=1), _bead("b", days_ago=1)])

    status, body = _call()

    assert status == 200
    # Per-day count labels are back (lost in the combine).
    assert "throughput-count" in body
    # The specific per-day closed count (2 on that day) is rendered, not only
    # the legend total.
    assert ">2<" in body
    # Each series renders in its own bottom-aligned column so bars grow up
    # from the baseline rather than hanging from the top.
    assert "throughput-col" in body


def test_created_empty_state_when_nothing_created_in_window() -> None:
    old_open = {
        "id": "old",
        "title": "Bead old",
        "status": "open",
        "created_at": _iso(400),
        "updated_at": _iso(400),
    }
    _stub_snapshot([old_open])

    status, body = _call(range="7d")

    assert status == 200
    # Combined chart's empty state covers BOTH series in one message.
    assert "No beads created or closed to chart" in body


# --- Page-size selector (bdboard-3jj) -----------------------------------


def test_default_page_size_is_fifty() -> None:
    # 60 closed beads within range: with the default page size of 50, page 1
    # holds exactly 50 and a "Older" pager appears (has_more).
    beads = [_bead(f"b{i}", days_ago=1) for i in range(60)]
    _stub_snapshot(beads)

    _, body = _call()  # no page_size -> default 50

    # The selector reflects the active size: 50 is the selected option.
    assert '<option value="50" selected>50</option>' in body
    assert '<option value="25">25</option>' in body
    assert '<option value="100">100</option>' in body
    # 50 of 60 on page 1 -> a next-page control exists.
    assert "Older" in body


def test_page_size_25_limits_page_and_selector_reflects_it() -> None:
    beads = [_bead(f"b{i}", days_ago=1) for i in range(60)]
    _stub_snapshot(beads)

    _, body = _call(page_size=25)

    # The selector shows 25 as the active option after the swap.
    assert '<option value="25" selected>25</option>' in body
    # Pager + range links carry the active page size so paging preserves it.
    assert "page_size=25" in body


def test_invalid_page_size_degrades_to_fifty() -> None:
    beads = [_bead(f"b{i}", days_ago=1) for i in range(60)]
    _stub_snapshot(beads)

    # A bogus value (not in {25,50,100}) clamps to the default 50.
    _, body = _call(page_size=999)

    assert '<option value="50" selected>50</option>' in body
    assert "page_size=50" in body


def test_pager_links_preserve_active_page_size() -> None:
    beads = [_bead(f"b{i}", days_ago=1) for i in range(60)]
    _stub_snapshot(beads)

    _, body = _call(page=1, page_size=25)

    # Next ("Older") link advances the page while keeping page_size=25.
    assert "page=2&page_size=25" in body


def test_range_buttons_carry_active_page_size() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    _, body = _call(range="7d", page_size=100)

    # Switching range preserves the chosen size (resets to page 1).
    assert 'hx-get="/api/history?range=90d&page=1&page_size=100"' in body


# --- Custom date-range selector (bdboard-7k6) ---------------------------


def _call_custom(
    from_date: str | None = None,
    to_date: str | None = None,
    range: str = "30d",
    page: int = 1,
    page_size: int | None = None,
) -> tuple[int, str]:
    qs = f"range={range}&page={page}"
    if page_size is not None:
        qs += f"&page_size={page_size}"
    if from_date is not None:
        qs += f"&from_date={from_date}"
    if to_date is not None:
        qs += f"&to_date={to_date}"
    resp = asyncio.run(
        app_module.api_history(
            _request(qs),
            range=range,
            page=page,
            page_size=page_size,
            from_date=from_date,
            to_date=to_date,
        )
    )
    return resp.status_code, resp.body.decode()


def test_custom_toggle_and_date_inputs_render() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    _, body = _call()

    # The Custom toggle and the from/to date inputs are present.
    assert 'id="history-custom-toggle"' in body
    assert 'id="history-custom-range"' in body
    assert 'name="from_date"' in body
    assert 'name="to_date"' in body
    assert 'type="date"' in body


def test_custom_range_marks_custom_active_not_preset() -> None:
    # A bead closed exactly today (days_ago=0) so an all-encompassing custom
    # window includes it.
    today = NOW.strftime("%Y-%m-%d")
    _stub_snapshot([_bead("a", days_ago=0)])

    _, body = _call_custom(from_date="2000-01-01", to_date=today)

    # The custom toggle owns the active cue; presets are not pressed.
    assert 'id="history-custom-toggle"' in body
    assert 'aria-expanded="true"' in body
    # The submitted dates echo back into the inputs.
    assert f'value="{today}"' in body
    # The bead inside the window surfaces.
    assert "Bead a" in body


def test_custom_range_supersedes_preset_filtering() -> None:
    # Old bead outside the 7d preset, but inside an explicit wide custom window.
    today = NOW.strftime("%Y-%m-%d")
    _stub_snapshot([_bead("old", days_ago=400)])

    status, body = _call_custom(range="7d", from_date="2000-01-01", to_date=today)

    assert status == 200
    # Despite range=7d, the custom window pulls in the 400-day-old bead.
    assert "Bead old" in body


def test_custom_range_pager_preserves_dates() -> None:
    today = NOW.strftime("%Y-%m-%d")
    beads = [_bead(f"b{i}", days_ago=1) for i in range(60)]
    _stub_snapshot(beads)

    _, body = _call_custom(from_date="2000-01-01", to_date=today, page_size=25)

    # Pager links carry the custom window so paging stays scoped to it.
    assert "from_date=2000-01-01" in body
    assert f"to_date={today}" in body
    assert "page_size=25" in body


def test_no_custom_dates_keeps_preset_behaviour() -> None:
    _stub_snapshot([_bead("a", days_ago=1)])

    _, body = _call_custom(range="7d")

    # Without from/to, the preset wins and its badge is pressed.
    assert 'aria-pressed="true"' in body
    assert 'hx-get="/api/history?range=90d&page=1&page_size=50"' in body
