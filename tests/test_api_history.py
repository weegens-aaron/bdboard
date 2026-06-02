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
    async def fake_snapshot(closed_after=None):
        return beads

    # The board path uses snapshot(); the History page uses snapshot_history()
    # (bdboard-p8v split the two so the board's short date window doesn't
    # truncate the long-window History view). The History path now also pushes
    # the active range's lower bound down as ``closed_after`` (bdboard-gp06),
    # so the history stub accepts (and ignores) that kwarg. Stub both so tests
    # stay decoupled from which path the route under test happens to call.
    async def fake_board_snapshot():
        return beads

    app_module.store.snapshot = fake_board_snapshot  # type: ignore[assignment]
    app_module.store.snapshot_history = fake_snapshot  # type: ignore[assignment]


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


def test_window_change_changes_returned_set() -> None:
    # bdboard-li44 regression: changing the active window must re-derive a
    # DIFFERENT closed set, not echo the previous render. One mix of recent +
    # old beads, fetched once, sliced by the route per requested window:
    #   - a narrow preset (7d) shows only the recent bead
    #   - a wide preset (all) shows BOTH
    #   - a custom narrow window shows only the bead inside it
    # This guards the route's window resolution + derive pushdown so a future
    # change can't silently make every window render the same thing again.
    recent = _bead("recent", days_ago=1)
    old = _bead("old", days_ago=400)
    _stub_snapshot([recent, old])

    def cards(body: str) -> set[str]:
        return {b for b in ("recent", "old") if f"Bead {b}<" in body}

    _, narrow = _call(range="7d")
    _, wide = _call(range="all")

    assert cards(narrow) == {"recent"}
    assert cards(wide) == {"recent", "old"}
    # The two windows genuinely differ — the core symptom of the bug was that
    # they did not.
    assert cards(narrow) != cards(wide)

    # A custom window scoped to the old bead's day surfaces ONLY it, proving
    # the custom path also drives the set (not just presets).
    old_day = (NOW - timedelta(days=400)).strftime("%Y-%m-%d")
    _, custom = _call_custom(from_date=old_day, to_date=old_day)
    assert cards(custom) == {"old"}


def test_all_range_includes_old_beads() -> None:
    _stub_snapshot([_bead("old", days_ago=400)])

    status, body = _call(range="all")

    assert status == 200
    assert "Bead old" in body
    # The 'all' range button is the active one.
    assert 'hx-get="/api/history?range=7d&page=1&page_size=50"' in body


def test_all_range_pages_through_more_than_fifty_closed() -> None:
    # bdboard-a194: with >50 closed beads and range=all, the History page must
    # be able to page through ALL of them, and the total must reflect the true
    # in-window closed count — not a hidden 50-cap. We spread the closes over
    # distinct days so range=all (no upper bound) keeps every one in-window.
    beads = [_bead(f"b{i}", days_ago=i) for i in range(120)]
    _stub_snapshot(beads)

    # Walk every page at the default page size of 50 and collect the bead ids
    # that surface in the rendered cards.
    seen: set[str] = set()
    page = 1
    while True:
        status, body = _call(range="all", page=page, page_size=50)
        assert status == 200
        found = {f"b{i}" for i in range(120) if f"Bead b{i}<" in body}
        if not found:
            break
        seen |= found
        page += 1
        if page > 10:  # safety net against an accidental infinite loop
            break

    # Every one of the 120 closed beads is reachable across the pages — the
    # old HISTORY_CLOSED_LIMIT=50 would have made b50..b119 unreachable.
    assert seen == {f"b{i}" for i in range(120)}
    # The result-count line reflects the TRUE closed total, not 50.
    _, page1 = _call(range="all", page=1, page_size=50)
    assert "120" in page1


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


def test_custom_range_is_a_popover_with_apply_and_clear_inside() -> None:
    """bdboard-9zf: From/To/Apply/Clear live in a popover anchored to Custom.

    The popover always ships hidden (opens only on an explicit Custom click),
    is wrapped in the position:relative .history-custom anchor, declares
    role=dialog + aria-haspopup, and contains BOTH Apply and Clear. There must
    be no persistent inline date inputs or a standalone Clear link in the
    toolbar.
    """
    _stub_snapshot([_bead("a", days_ago=1)])

    _, body = _call()

    # Anchor wrapper + popover class + dialog semantics.
    assert 'class="history-custom"' in body
    assert "history-custom-pop" in body
    assert 'role="dialog"' in body
    assert 'aria-haspopup="dialog"' in body
    # Popover ships hidden and the toggle is collapsed by default.
    assert "hidden" in body
    assert 'aria-expanded="false"' in body
    # Apply AND Clear both live inside (the popover always renders Clear now,
    # not only when custom is active).
    assert "history-date-apply" in body
    assert "history-date-clear" in body
    assert ">Apply<" in body
    assert ">Clear<" in body
    # The old persistent-inline form class is gone.
    assert 'class="history-custom-range"' not in body


def test_custom_range_marks_custom_active_not_preset() -> None:
    # A bead closed exactly today (days_ago=0) so an all-encompassing custom
    # window includes it.
    today = NOW.strftime("%Y-%m-%d")
    _stub_snapshot([_bead("a", days_ago=0)])

    _, body = _call_custom(from_date="2000-01-01", to_date=today)

    # The custom toggle owns the active cue via the badge highlight, NOT an
    # open popover (bdboard-9zf moved the inputs into a popover that ships
    # hidden + aria-expanded=false; the active state is the pressed badge).
    assert 'id="history-custom-toggle"' in body
    assert "filter-badge-active" in body
    assert 'aria-pressed="true"' in body
    assert 'aria-expanded="false"' in body
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


# --- Filter-bounded fetch (bdboard-gp06) --------------------------------


def _stub_snapshot_recording(beads):
    """Like _stub_snapshot but records the closed_after the route forwards.

    Returns a list capturing every ``closed_after`` value the route hands to
    ``store.snapshot_history`` so tests can assert the active filter window is
    pushed down to the data layer (bdboard-gp06).
    """
    seen: list = []

    async def fake_snapshot(closed_after=None):
        seen.append(closed_after)
        return beads

    app_module.store.snapshot_history = fake_snapshot  # type: ignore[assignment]
    return seen


def test_narrow_range_pushes_lower_bound_to_fetch() -> None:
    # A narrow range bounds the fetch at the data layer: the route forwards a
    # concrete closed_after cutoff (not None) so bd only pulls the in-window
    # closures rather than slurping the whole closed table.
    seen = _stub_snapshot_recording([_bead("a", days_ago=1)])

    _call(range="7d")

    assert len(seen) == 1
    cutoff = seen[0]
    assert cutoff is not None
    delta = datetime.now(UTC) - cutoff
    assert timedelta(days=6, hours=23) <= delta <= timedelta(days=7, hours=1)


def test_all_range_keeps_fetch_unbounded() -> None:
    # range=all is unbounded by design: the route forwards closed_after=None
    # so the data layer issues a genuine full-table read.
    seen = _stub_snapshot_recording([_bead("a", days_ago=1)])

    _call(range="all")

    assert seen == [None]


def test_custom_window_pushes_from_date_lower_bound() -> None:
    # A custom from/to selection bounds the fetch by the from_date lower
    # bound, mirroring the preset path.
    seen = _stub_snapshot_recording([_bead("a", days_ago=1)])

    _call_custom(from_date="2026-05-01", to_date="2026-05-31")

    assert len(seen) == 1
    cutoff = seen[0]
    assert cutoff is not None
    assert cutoff.strftime("%Y-%m-%d") == "2026-05-01"


def test_custom_to_only_leaves_fetch_unbounded() -> None:
    # An open-ended lower bound (only a to_date, no from_date) resolves
    # cutoff=None, so the fetch stays unbounded — the user explicitly chose
    # no lower bound.
    seen = _stub_snapshot_recording([_bead("a", days_ago=1)])

    _call_custom(to_date="2026-05-31")

    assert seen == [None]


def test_window_kpi_throughput_consistent_across_ranges() -> None:
    # The displayed closed-list total, the 'Closed (range)' KPI (stats n), and
    # the throughput series must all reflect the SAME in-window closed set for
    # every range (no off-by-one between the bd fetch bound and the derive
    # slice). Asserted at the derive layer over one snapshot, sharing one now.
    from bdboard import derive

    now = datetime.now(UTC)
    beads = [_bead(f"in{i}", days_ago=i) for i in range(1, 6)] + [_bead("out", days_ago=400)]

    for range_key in ("7d", "30d", "90d", "all"):
        window = derive.history_window(beads, range_key=range_key, page_size=100, now=now)
        stats = derive.lead_time_stats(beads, range_key=range_key, now=now)
        series = derive.throughput(beads, range_key=range_key, now=now)
        combined = derive.combined(beads, range_key=range_key, now=now)
        series_total = sum(d["count"] for d in series)
        combined_total = sum(d["closed"] for d in combined)
        assert window["total"] == stats["n"] == series_total == combined_total
