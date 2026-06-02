"""Tests for board time-filter ↔ masthead CLOSED stat sync (bdboard-de4z).

Bug: changing the Board time window (12h/1d/3d) updated the Closed lane and
its badge but the masthead #counts strip kept showing the unfiltered totals, so
the header and the visible lanes disagreed about the active window.

The board time filter is a *purely client-side* control (it shows/hides
already-fetched cards; see docs/catalog/board-time-filter.md), so the fix lives
in the client: applyBoardFilter() now feeds the SAME visibleCount it writes into
the Closed lane badge into the masthead CLOSED cell, keyed off a stable
`data-count-status` hook on the counts cells. Reusing one number guarantees the
header and lanes can never drift at the window boundary (no client-now vs
server-now skew).

These are markup/wiring tests (no TestClient/httpx): they render the counts
partial and assert on the static base.html script wiring.
"""

from __future__ import annotations

from pathlib import Path

from bdboard import app as app_module

_PKG_DIR = Path(app_module.__file__).parent
_BASE_HTML = (_PKG_DIR / "templates" / "base.html").read_text(encoding="utf-8")


def _render_counts(counts: dict[str, int]) -> str:
    """Render partials/counts.html through the app's Jinja env."""
    template = app_module.TEMPLATES.env.get_template("partials/counts.html")
    return template.render(counts=counts)


# ----- the stable hook the JS targets -----


def test_counts_cells_carry_status_hook() -> None:
    """Each counts cell exposes data-count-status so JS can target a cell by
    status without depending on the (text-transformed, re-wordable) label."""
    html = _render_counts({"open": 3, "blocked": 1, "deferred": 0, "closed": 7})

    assert 'data-count-status="open"' in html
    assert 'data-count-status="blocked"' in html
    assert 'data-count-status="deferred"' in html
    assert 'data-count-status="closed"' in html


def test_closed_cell_pairs_hook_with_value() -> None:
    """The closed cell keeps the hook and the .counts-value together so the JS
    can find the cell by status and rewrite its number."""
    html = _render_counts({"open": 0, "blocked": 0, "deferred": 0, "closed": 5})

    assert 'data-count-status="closed"' in html
    assert "counts-value" in html
    assert ">5<" in html


# ----- the client wiring that keeps header == lanes -----


def test_sync_helper_targets_closed_cell_by_hook() -> None:
    """A dedicated sync helper updates ONLY the masthead CLOSED cell, keyed off
    the data-count-status hook (not OPEN/BLOCKED/DEFERRED, which are
    window-invariant)."""
    assert "function syncMastheadClosedCount" in _BASE_HTML
    assert '[data-count-status="closed"]' in _BASE_HTML


def test_sync_mirrors_zero_state_muting() -> None:
    """When the filtered closed count hits zero the cell picks up the same
    counts-cell-zero muting the server template applies, so a filtered-to-empty
    window doesn't leave a bright, misleading number."""
    assert "counts-cell-zero" in _BASE_HTML
    assert "visibleCount === 0" in _BASE_HTML


def test_apply_filter_feeds_visible_count_to_masthead() -> None:
    """applyBoardFilter reuses the SAME visibleCount for the lane badge AND the
    masthead, guaranteeing the two can't diverge at the window boundary."""
    assert "syncMastheadClosedCount(visibleCount);" in _BASE_HTML


def test_masthead_sync_guarded_by_real_closed_lane() -> None:
    """The masthead is synced only when the closed lane has real content (the
    [data-closed-count] badge exists), so a premature run against the skeleton
    can't clobber the server total with a stale 0."""
    idx_guard = _BASE_HTML.find("const countEl = closedLane.querySelector('[data-closed-count]');")
    # Match the CALL (trailing `;`), not the function definition signature.
    idx_sync = _BASE_HTML.find("syncMastheadClosedCount(visibleCount);")
    assert idx_guard != -1, "expected the closed-lane countEl guard to exist"
    assert idx_sync != -1, "expected the masthead sync call to exist"
    assert idx_sync > idx_guard, "masthead sync must be gated behind the countEl guard"


def test_counts_strip_resync_on_independent_settle() -> None:
    """If #counts hydrates AFTER the closed lane, its fresh swap carries the
    unfiltered server total — so the afterSettle handler re-applies the saved
    filter when #counts settles, re-syncing the CLOSED cell."""
    assert "target.id === 'counts'" in _BASE_HTML
    # That branch still routes through wireFilterBadges -> applyBoardFilter.
    assert "isCountsStrip" in _BASE_HTML
