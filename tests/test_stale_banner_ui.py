"""Render tests for the closed-window label + stale-data banner (bdboard-75rq).

Two display-fidelity gaps the board had:

  1. The Closed lane only shows closures inside BOARD_CLOSED_WINDOW_DAYS with
     NO affordance, so an empty lane was ambiguous ("nothing closed" vs "older
     closures hidden"). The lane now states its active window and links to the
     uncapped History page.

  2. A sustained ``bd list`` refresh failure froze the board on the last-good
     snapshot with only a log line. A page-level stale banner now surfaces a
     SUSTAINED outage; a healthy board renders nothing (region collapses).

These are markup tests (no TestClient): they render the partials through the
app's Jinja env and assert on the base.html poll wiring, mirroring
test_board_counts_filter_sync.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from bdboard import app as app_module
from bdboard.store import StalenessState

_PKG_DIR = Path(app_module.__file__).parent
_BASE_HTML = (_PKG_DIR / "templates" / "base.html").read_text(encoding="utf-8")


def _render_closed_lane(closed, window_days: int) -> str:
    template = app_module.TEMPLATES.env.get_template("partials/closed_lane.html")
    return template.render(closed=closed, closed_window_days=window_days)


def _render_banner(state: StalenessState, last_success_label: str | None) -> str:
    template = app_module.TEMPLATES.env.get_template("partials/stale_banner.html")
    return template.render(staleness=state, last_success_label=last_success_label)


# ----- AC1: the Closed lane states its window + links to History -----


def test_closed_lane_states_active_window() -> None:
    html = _render_closed_lane([], window_days=3)
    assert "Last 3 days" in html


def test_closed_lane_window_singular_day() -> None:
    # Defensive: a 1-day window should read "day", not "days".
    html = _render_closed_lane([], window_days=1)
    assert "Last 1 day" in html
    assert "Last 1 days" not in html


def test_closed_lane_links_to_uncapped_history() -> None:
    html = _render_closed_lane([], window_days=3)
    # range=all is the uncapped History view — older closures are reachable.
    assert 'href="/history?range=all"' in html
    assert "See History" in html


# ----- AC2 + AC3: sustained failure surfaces; transient does not -----


def test_banner_renders_when_stale() -> None:
    state = StalenessState(
        stale=True,
        consecutive_failures=4,
        last_success=datetime(2026, 6, 6, 9, 30, tzinfo=UTC),
    )
    html = _render_banner(state, last_success_label="09:30")
    assert "stale-banner" in html
    assert "09:30" in html
    assert 'role="status"' in html


def test_banner_empty_when_healthy() -> None:
    # A healthy board renders NOTHING so the region collapses (no flash).
    state = StalenessState(stale=False, consecutive_failures=0, last_success=None)
    html = _render_banner(state, last_success_label=None)
    assert "stale-banner" not in html
    assert html.strip() == ""


def test_banner_omits_last_updated_when_never_succeeded() -> None:
    # Stale with no prior success (e.g. bd broken since boot): no time copy,
    # but still warn that data may be stale.
    state = StalenessState(stale=True, consecutive_failures=5, last_success=None)
    html = _render_banner(state, last_success_label=None)
    assert "stale-banner" in html
    assert "Last updated" not in html


# ----- base.html wires a poll for the banner (a frozen board has no SSE) -----


def test_base_html_polls_staleness_endpoint() -> None:
    assert "/api/staleness" in _BASE_HTML
    # Polled on an interval AND re-checked on SSE refresh so it clears on
    # recovery. The interval is what catches a frozen board (no SSE events).
    assert "every 30s" in _BASE_HTML
    assert "refresh from:body" in _BASE_HTML
