"""Route + registry tests for the Analytics tab (bdboard-ove7).

The Analytics page (/analytics) replaces the standalone History menu item and
hosts multiple analytics/history sub-views behind one in-page switcher. The
sub-views are data-driven from src/bdboard/analytics.py's ANALYTICS_VIEWS
registry, so adding one is a small additive change. History is the first
sub-view, migrated in here and reusing /api/history + partials/history.html
unchanged.

We invoke the endpoint coroutines directly with a minimal ASGI Request (no
TestClient/httpx needed) and assert on rendered HTML. The page shells no bd
subprocess (each sub-view region hydrates lazily via HTMX); an autouse fixture
in tests/conftest.py stubs workspace validation so the happy path is
environment-independent.

Covers:
  - /analytics returns 200 and extends base.html (full page, not a partial)
  - the registry drives the switcher (data-driven extension point)
  - History renders as a selectable sub-view, unchanged in content
  - the selected sub-view is reflected in the URL (deep-link / back-forward)
  - /api/analytics returns the panel fragment for the switcher swap
  - unknown ?view= degrades to the default sub-view
  - nav active-state + aria-current correct; live refresh wiring preserved
  - workspace validation failure renders the error page
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from starlette.requests import Request

from bdboard import analytics
from bdboard import app as app_module


def _request(path: str = "/analytics", query: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query.encode(),
        "headers": [],
    }
    return Request(scope)


def _call_analytics(view: str | None = None) -> tuple[int, str]:
    resp = asyncio.run(app_module.page_analytics(_request(), view=view))
    return resp.status_code, resp.body.decode()


def _call_api_analytics(view: str | None = None) -> tuple[int, str]:
    resp = asyncio.run(app_module.api_analytics(_request("/api/analytics"), view=view))
    return resp.status_code, resp.body.decode()


def _call_index() -> tuple[int, str]:
    resp = asyncio.run(app_module.index(_request("/")))
    return resp.status_code, resp.body.decode()


def _call_memory() -> tuple[int, str]:
    resp = asyncio.run(app_module.page_memory(_request("/memory")))
    return resp.status_code, resp.body.decode()


# ----- registry: the documented extension point + conditional registration -----


def _write_log(beads_dir: Path, kinds: list[str]) -> None:
    """Write a minimal interactions.jsonl with one entry per kind."""
    beads_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"id": f"int-{i}", "kind": k, "created_at": f"2026-01-{i + 1:02d}"})
        for i, k in enumerate(kinds)
    ]
    (beads_dir / "interactions.jsonl").write_text("\n".join(lines), encoding="utf-8")


def test_history_is_always_present_and_default() -> None:
    """History is the always-on default sub-view (bdboard-8l60)."""
    assert analytics.DEFAULT_VIEW.key == "history"
    assert analytics.HISTORY_VIEW.key == "history"


def test_build_views_excludes_interactions_when_log_missing(tmp_path) -> None:
    """A missing interactions.jsonl => History only, no Interactions chip."""
    views = analytics.build_views(tmp_path / ".beads")
    assert [v.key for v in views] == ["history"]


def test_build_views_excludes_interactions_when_empty(tmp_path) -> None:
    """An empty interactions.jsonl => History only."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "interactions.jsonl").write_text("", encoding="utf-8")
    views = analytics.build_views(beads)
    assert [v.key for v in views] == ["history"]


def test_build_views_excludes_interactions_when_field_change_only(tmp_path) -> None:
    """A 100%-field_change log (the common real-world case) => History only:
    field_change is redundant with per-bead `bd history`, so it earns no
    sub-view (bdboard-8l60)."""
    beads = tmp_path / ".beads"
    _write_log(beads, ["field_change", "field_change", "field_change"])
    views = analytics.build_views(beads)
    assert [v.key for v in views] == ["history"]
    assert analytics.has_reward_bearing_interactions(beads) is False


def test_build_views_includes_interactions_when_reward_bearing(tmp_path) -> None:
    """Any reward-bearing kind (llm_call / tool_call / label) registers the
    Interactions sub-view as the second entry, with its original partial."""
    for kind in ("llm_call", "tool_call", "label"):
        beads = tmp_path / kind / ".beads"
        _write_log(beads, ["field_change", kind])
        views = analytics.build_views(beads)
        assert [v.key for v in views] == ["history", "interactions"]
        inter = views[1]
        assert inter.label == "Interactions"
        assert inter.partial == "partials/analytics_interactions.html"
        assert analytics.has_reward_bearing_interactions(beads) is True


def test_resolve_view_defaults_on_unknown_or_missing() -> None:
    """A missing/unknown ?view= degrades to the first registered view (never
    404s)."""
    views = (analytics.HISTORY_VIEW,)
    assert analytics.resolve_view(None, views) is analytics.HISTORY_VIEW
    assert analytics.resolve_view("", views) is analytics.HISTORY_VIEW
    assert analytics.resolve_view("does-not-exist", views) is analytics.HISTORY_VIEW
    # Case-insensitive, trimmed.
    assert analytics.resolve_view("  HISTORY ", views).key == "history"


def test_resolve_view_stale_interactions_degrades_when_unregistered() -> None:
    """A stale ?view=interactions degrades to History when Interactions is NOT
    registered, but resolves cleanly when it is."""
    history_only = (analytics.HISTORY_VIEW,)
    assert analytics.resolve_view("interactions", history_only) is analytics.HISTORY_VIEW
    with_interactions = (analytics.HISTORY_VIEW, analytics.INTERACTIONS_VIEW)
    assert analytics.resolve_view("interactions", with_interactions).key == "interactions"


# ----- /analytics full page -----


def test_analytics_page_renders_full_document() -> None:
    status, body = _call_analytics()

    assert status == 200
    # Extends base.html -> full HTML document, not a bare partial.
    assert "<!doctype html>" in body.lower()
    assert "<title>Analytics" in body
    assert 'class="masthead"' in body
    # The panel host that the switcher swaps into.
    assert 'id="analytics-panel"' in body


def test_analytics_switcher_is_registry_driven(monkeypatch) -> None:
    """Every registered sub-view renders one switcher tab with its label +
    deep link, proving the switcher is data-driven (not hard-coded per view).
    Forcing reward-bearing interactions registers both History + Interactions.
    """
    monkeypatch.setattr(analytics, "has_reward_bearing_interactions", lambda _b: True)
    _, body = _call_analytics()

    assert 'class="analytics-switcher"' in body
    for v in (analytics.HISTORY_VIEW, analytics.INTERACTIONS_VIEW):
        assert f'href="/analytics?view={v.key}"' in body
        assert f">{v.label}</a>" in body
        # Switcher tabs swap just the panel and push the canonical URL.
        assert f'hx-get="/api/analytics?view={v.key}"' in body
    assert 'hx-target="#analytics-panel"' in body
    assert 'hx-push-url="true"' in body


def test_history_subview_renders_unchanged_content() -> None:
    """History renders inside Analytics as a sub-view, reusing /api/history +
    its stats host, unchanged in content."""
    _, body = _call_analytics(view="history")

    # The History sub-view shell owns the region + stats host and lazy-loads
    # the SAME /api/history endpoint as before.
    assert 'id="history-region"' in body
    assert 'hx-get="/api/history"' in body
    assert 'id="history-stats"' in body


def test_interactions_subview_renders_when_reward_bearing(monkeypatch) -> None:
    """With reward-bearing interactions, the Interactions sub-view registers
    and renders inside Analytics (bdboard-vtd4), reusing /api/interactions +
    its kind filter chips, unchanged in content."""
    monkeypatch.setattr(analytics, "has_reward_bearing_interactions", lambda _b: True)
    _, body = _call_analytics(view="interactions")

    # The Interactions sub-view shell owns the region and lazy-loads the SAME
    # /api/interactions endpoint the standalone page used.
    assert 'id="interactions-region"' in body
    assert 'hx-get="/api/interactions"' in body
    assert 'hx-trigger="load, refresh from:body"' in body
    # Interactions tab reads active in the switcher.
    assert 'href="/analytics?view=interactions"' in body


def test_interactions_subview_absent_when_not_reward_bearing(monkeypatch) -> None:
    """With an empty/missing/field_change-only log, the Interactions sub-view
    is NOT registered: no switcher chip, no panel, and ?view=interactions
    degrades to History (bdboard-8l60)."""
    monkeypatch.setattr(analytics, "has_reward_bearing_interactions", lambda _b: False)
    _, body = _call_analytics(view="interactions")

    # No Interactions switcher chip and no Interactions panel.
    assert 'href="/analytics?view=interactions"' not in body
    assert 'id="interactions-region"' not in body
    # Degrades to the default History sub-view (no 404, no empty panel).
    assert 'id="history-region"' in body
    assert 'class="analytics-tab is-active"' in body


def test_standalone_interactions_nav_entry_is_gone(monkeypatch) -> None:
    """The standalone Interactions PRIMARY nav entry is replaced by the
    Analytics tab. When Interactions IS registered, 'Interactions' survives
    only as a switcher tab inside the Analytics panel, never as a primary
    masthead nav link to /interactions."""
    monkeypatch.setattr(analytics, "has_reward_bearing_interactions", lambda _b: True)
    _, body = _call_analytics()

    # No primary nav link to the old /interactions page (it redirects now).
    assert 'href="/interactions"' not in body
    # 'Interactions' survives only as a switcher tab inside the Analytics panel.
    masthead, _sep, _panel = body.partition('class="analytics-switcher"')
    assert ">Interactions</a>" not in masthead
    assert 'href="/analytics?view=interactions"' in body


def test_selected_subview_reflected_in_url_active_state() -> None:
    """The active sub-view is marked aria-current + .is-active so the URL the
    switcher pushes matches the highlighted tab (deep-link friendly)."""
    _, body = _call_analytics(view="history")

    assert (
        'href="/analytics?view=history"\n    class="analytics-tab is-active"' in body
        or 'class="analytics-tab is-active"' in body
    )
    assert 'aria-current="page"' in body


def test_unknown_view_degrades_to_default() -> None:
    """A bad/stale ?view= still renders the default sub-view, never an empty
    panel."""
    _, body = _call_analytics(view="bogus")

    # Default (history) sub-view content is present.
    assert 'id="history-region"' in body
    assert 'class="analytics-tab is-active"' in body


def test_subview_lazy_loads_and_live_refreshes() -> None:
    """The sub-view region hydrates on switch-in and live-updates on SSE,
    inheriting the board's refresh pipeline."""
    _, body = _call_analytics(view="history")

    assert 'hx-trigger="load, refresh from:body"' in body


# ----- /api/analytics panel fragment -----


def test_api_analytics_returns_panel_fragment() -> None:
    """The fragment endpoint returns the switcher + active sub-view (the same
    partial the page embeds), NOT a full document."""
    status, body = _call_api_analytics(view="history")

    assert status == 200
    assert "<!doctype html>" not in body.lower()
    assert 'class="analytics-switcher"' in body
    assert 'id="history-region"' in body


def test_api_analytics_unknown_view_degrades_to_default() -> None:
    _, body = _call_api_analytics(view="nope")

    assert 'id="history-region"' in body
    assert 'class="analytics-tab is-active"' in body


# ----- nav active-state across surfaces -----


def test_analytics_page_nav_entry_active() -> None:
    _, body = _call_analytics()

    assert 'aria-label="Primary"' in body
    assert 'href="/analytics"' in body
    # Analytics is the active page here (non-colour cue + aria-current).
    assert 'href="/analytics"\n     class="mh-link is-active"' in body


def test_history_nav_entry_is_gone() -> None:
    """The standalone History PRIMARY nav entry is replaced by Analytics.

    The 'History' label still appears — but only as a SWITCHER tab inside the
    Analytics panel, never as a primary masthead nav link to /history."""
    _, body = _call_analytics()

    # No primary nav link to the old /history page (it redirects now).
    assert 'href="/history"' not in body
    assert ">Analytics</a>" in body
    # 'History' survives only as a switcher tab inside the Analytics panel,
    # never as a primary masthead nav link. Everything BEFORE the switcher is
    # masthead chrome and must not contain a History nav entry.
    masthead, _sep, _panel = body.partition('class="analytics-switcher"')
    assert ">History</a>" not in masthead
    assert 'href="/analytics?view=history"' in body


def test_dashboard_renders_analytics_nav_entry() -> None:
    status, body = _call_index()

    assert status == 200
    assert 'href="/analytics"' in body
    assert 'href="/"\n     class="mh-link is-active"' in body


def test_memory_page_renders_analytics_nav_entry() -> None:
    status, body = _call_memory()

    assert status == 200
    assert 'href="/analytics"' in body
    assert 'href="/memory"\n     class="mh-link is-active"' in body


# ----- error path -----


def test_analytics_page_surfaces_workspace_error(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_validate_or_warn", lambda: "bd not found")

    resp = asyncio.run(app_module.page_analytics(_request()))

    assert resp.status_code == 500
    assert "bd not found" in resp.body.decode()
