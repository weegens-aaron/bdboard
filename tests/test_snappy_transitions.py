"""Markup tests for the snappy-transitions / TTFP work (bdboard-2do).

Every primary navigation (Board / History / Memory) and the bead-detail
modal must give an immediate visual response on click — a skeleton shell
that paints instantly — so the UI never freezes while a bd-CLI-backed fetch
resolves.

These tests assert on the rendered HTML (no TestClient/httpx needed): the
full-page routes return a cheap shell with skeleton placeholders and wire
their data regions to hydrate via HTMX `load`. The board shell in particular
must NOT block on store.snapshot() anymore — it hydrates lanes + counts
lazily, symmetric with /history and /memory.

The former global top progress bar (#nav-progress) was removed in
bdboard-ddb; skeleton loaders are the single loading-feedback mechanism.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from starlette.requests import Request

from bdboard import app as app_module

_TEMPLATES = Path(app_module.__file__).parent / "templates"


def _request(path: str = "/") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _call_index() -> tuple[int, str]:
    resp = asyncio.run(app_module.index(_request("/")))
    return resp.status_code, resp.body.decode()


def _call_history() -> tuple[int, str]:
    # History migrated into the Analytics tab (bdboard-ove7); the former
    # standalone /history page is now the first Analytics sub-view. The History
    # sub-view shell still owns #history-region + #history-stats and lazy-loads
    # /api/history, so the snappy-transition guarantees are asserted here via
    # the Analytics page rendering the History sub-view.
    resp = asyncio.run(app_module.page_analytics(_request("/analytics"), view="history"))
    return resp.status_code, resp.body.decode()


def _call_memory() -> tuple[int, str]:
    resp = asyncio.run(app_module.page_memory(_request("/memory")))
    return resp.status_code, resp.body.decode()


def test_skeleton_partials_exist() -> None:
    """The four skeleton scaffolds the shells include must exist on disk."""
    partials = _TEMPLATES / "partials"
    for name in (
        "counts_skeleton.html",
        "lanes_skeleton.html",
        "history_skeleton.html",
        "memory_skeleton.html",
    ):
        assert (partials / name).is_file(), f"missing skeleton: {name}"


def test_board_shell_hydrates_lanes_and_counts_lazily() -> None:
    """The board renders a cheap shell with skeletons that hydrate via load.

    Regression guard for the old behaviour where `/` awaited
    store.snapshot() + per-epic `bd show` before returning ANY HTML.
    """
    status, body = _call_index()

    assert status == 200
    # Skeleton shimmer placeholders paint instantly.
    assert "skeleton" in body
    # Both data regions hydrate from their cheap API routes on load.
    assert 'hx-get="/api/lanes"' in body
    assert 'hx-get="/api/counts"' in body
    assert 'hx-trigger="load, refresh from:body"' in body


def test_board_modal_skeleton_template_present() -> None:
    """base.html ships the bead-modal skeleton template."""
    _, body = _call_index()

    assert 'id="bead-modal-skeleton"' in body
    assert "modal-skeleton" in body


def test_top_loading_bar_removed() -> None:
    """The former global top progress bar is gone (bdboard-ddb).

    Skeleton loaders now convey in-flight data regions, so the top
    loading/progress bar was removed as redundant. Guard against any
    leftover element, CSS, or hx-indicator wiring creeping back in.
    """
    for _, body in (_call_index(), _call_history(), _call_memory()):
        assert 'id="nav-progress"' not in body
        assert 'hx-indicator="#nav-progress"' not in body

    css = (Path(app_module.__file__).parent / "static" / "styles.css").read_text()
    assert ".nav-progress {" not in css
    assert ".nav-progress.is-active" not in css
    assert "@keyframes nav-progress-indeterminate" not in css


def test_all_full_pages_render_skeletons() -> None:
    """Board / History / Memory each paint a skeleton shell instantly."""
    for status, body in (_call_index(), _call_history(), _call_memory()):
        assert status == 200
        assert "skeleton" in body


def test_hydrating_regions_mark_aria_busy() -> None:
    """Every async data region is flagged aria-busy on first paint (bdboard-3vp).

    AC: skeletons are accessible (aria-busy/aria-live or equivalent). Each
    full-page shell marks its hydrating region(s) aria-busy="true" so AT knows
    the shimmer is a loading placeholder; a delegated htmx:afterSettle handler
    (in base.html) flips it to false once real content lands.
    """
    _, board = _call_index()
    # Board: both the lanes region and the masthead counts host.
    assert 'class="lanes-region"' in board
    assert 'aria-busy="true"' in board
    assert board.count('aria-busy="true"') >= 2

    _, history = _call_history()
    # History: the swap region AND the masthead stats host both load lazily.
    assert 'id="history-region"' in history
    assert 'id="history-stats"' in history
    assert history.count('aria-busy="true"') >= 2

    _, memory = _call_memory()
    assert 'id="memory-list"' in memory
    assert 'aria-busy="true"' in memory

    # The settle handler that clears the busy flag must be wired once on body.
    assert "htmx:afterSettle" in board
    assert "aria-busy" in board  # handler references it


def test_history_masthead_stats_host_has_skeleton() -> None:
    """The History masthead stats strip paints a skeleton, not a blank gap.

    Regression guard for bdboard-3vp: #history-stats used to be an empty
    <div> that stayed blank until the first /api/history OOB swap landed, so
    the KPI/masthead-counts region had no skeleton loader. It now includes the
    shared counts skeleton (reserving the stat columns) so the masthead is
    symmetric with the board's #counts host.
    """
    _, body = _call_history()

    # The stats host exists, is busy, and ships shimmer placeholders.
    assert 'id="history-stats"' in body
    assert "counts-skeleton" in body
    # Empty host regression: there must be skeleton markup between the host's
    # opening tag and its close, not just <div id="history-stats"></div>.
    assert 'id="history-stats"></div>' not in body


def test_history_region_skeleton_reserves_chart() -> None:
    """The history skeleton mirrors the real region's single combined chart.

    history.html's body renders ONE combined 'Created vs closed' chart
    (bdboard-ijd merged the former two strips). The skeleton must reserve a
    fixed-height chart body (and NOT an inline KPI strip, which now lives in
    the masthead) so hydration is shift-free.
    """
    skel = (
        Path(app_module.__file__).parent / "templates" / "partials" / "history_skeleton.html"
    ).read_text()

    # A chart-body placeholder, matching the single combined chart.
    assert skel.count("skeleton-chart") >= 1
    assert "history-chart-skeleton" in skel
    # The stale inline KPI strip (which lived in the body before the stats
    # moved to the masthead) must be gone so it can't shift the layout.
    assert "history-kpi-skeleton" not in skel
    assert "skeleton-kpi" not in skel


def test_styles_include_skeleton_css() -> None:
    """The stylesheet defines the shimmer skeleton primitives."""
    css = (Path(app_module.__file__).parent / "static" / "styles.css").read_text()

    assert ".skeleton" in css
    assert "@keyframes skeleton-shimmer" in css
    # Theme-aware tokens for light + dark.
    assert "--skeleton-base" in css
    assert "--skeleton-sheen" in css
    # Balanced braces — guards against the mid-append corruption that broke
    # the keyframe block in a prior interrupted session.
    assert css.count("{") == css.count("}")
    # Reduced-motion users get a static placeholder, not a shimmer.
    assert "prefers-reduced-motion" in css
