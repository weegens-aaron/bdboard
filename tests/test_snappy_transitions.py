"""Markup tests for the snappy-transitions / TTFP work (bdboard-2do).

Every primary navigation (Board / History / Memory) and the bead-detail
modal must give an immediate visual response on click — a skeleton shell
that paints instantly plus an HTMX request indicator (#nav-progress) — so
the UI never freezes while a bd-CLI-backed fetch resolves.

These tests assert on the rendered HTML (no TestClient/httpx needed): the
full-page routes return a cheap shell with skeleton placeholders and wire
their data regions to hydrate via HTMX `load`, and every nav/modal trigger
carries hx-indicator="#nav-progress". The board shell in particular must
NOT block on store.snapshot() anymore — it hydrates lanes + counts lazily,
symmetric with /history and /memory.
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
    resp = asyncio.run(app_module.page_history(_request("/history")))
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
    """base.html ships the bead-modal skeleton template + the progress bar."""
    _, body = _call_index()

    assert 'id="bead-modal-skeleton"' in body
    assert 'id="nav-progress"' in body
    assert "modal-skeleton" in body


def test_all_full_pages_render_skeletons() -> None:
    """Board / History / Memory each paint a skeleton shell instantly."""
    for status, body in (_call_index(), _call_history(), _call_memory()):
        assert status == 200
        assert "skeleton" in body


def test_nav_and_modal_triggers_wire_progress_indicator() -> None:
    """Every full page wires hx-indicator="#nav-progress" on its triggers."""
    for _, body in (_call_index(), _call_history(), _call_memory()):
        assert 'hx-indicator="#nav-progress"' in body


def test_styles_include_skeleton_and_progress_css() -> None:
    """The stylesheet defines the shimmer + progress-bar primitives."""
    css = (Path(app_module.__file__).parent / "static" / "styles.css").read_text()

    assert ".skeleton" in css
    assert "@keyframes skeleton-shimmer" in css
    assert ".nav-progress" in css
    assert "@keyframes nav-progress-indeterminate" in css
    # Theme-aware tokens for light + dark.
    assert "--skeleton-base" in css
    assert "--skeleton-sheen" in css
    # Balanced braces — guards against the mid-append corruption that broke
    # the keyframe block in a prior interrupted session.
    assert css.count("{") == css.count("}")
    # Reduced-motion users get a static placeholder, not a shimmer.
    assert "prefers-reduced-motion" in css
