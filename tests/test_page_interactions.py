"""Route tests for the swarm interaction-log viewer.

Interactions migrated from a standalone /interactions page into the SECOND
Analytics sub-view (bdboard-vtd4); /interactions is now a thin 307 redirect to
/analytics?view=interactions (symmetric with /history). The interaction log
itself is unchanged — the Analytics sub-view shell reuses /api/interactions +
partials/interactions.html, kind filter chips and all.

Covers:
  - GET /interactions 307-redirects into the Analytics Interactions sub-view
  - the Interactions sub-view is reachable + lazy-loads /api/interactions
  - the standalone Interactions PRIMARY nav item is gone (now an Analytics tab)
  - GET /api/interactions renders kind filter chips + entry rows
  - ?kind= filters the list to one kind (still works inside Analytics)
  - a missing interactions.jsonl degrades to a friendly empty state (no 500)

We invoke the endpoint coroutines directly with a minimal ASGI Request (no
TestClient needed). The autouse conftest fixture stubs workspace validation so
the page happy-path is environment-independent; the /api tests point the bd
client at a tmp workspace so they read a controlled interactions.jsonl.
"""

from __future__ import annotations

import asyncio
import json

from starlette.requests import Request

from bdboard import app as app_module


def _request(path: str = "/interactions", query: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query.encode(),
        "headers": [],
    }
    return Request(scope)


def _call_api(kind: str = "", *, beads_dir=None, monkeypatch=None) -> tuple[int, str]:
    if beads_dir is not None and monkeypatch is not None:
        # Point the module-level bd client's workspace at the tmp dir; its
        # beads_dir property returns workspace/.beads, so we pass the PARENT.
        monkeypatch.setattr(app_module.bd, "workspace", beads_dir.parent)
    resp = asyncio.run(app_module.api_interactions(_request(query=f"kind={kind}"), kind=kind))
    return resp.status_code, resp.body.decode()


def _seed(beads_dir, rows) -> None:
    beads_dir.mkdir(parents=True, exist_ok=True)
    (beads_dir / "interactions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


# ----- /interactions redirect into the Analytics tab -----


def test_interactions_redirects_into_analytics() -> None:
    """The former standalone page is now a 307 redirect to the sub-view, so old
    links / bookmarks / the removed nav entry never break."""
    resp = asyncio.run(app_module.page_interactions(_request()))
    assert resp.status_code == 307
    assert resp.headers["location"] == "/analytics?view=interactions"


def test_interactions_subview_lazy_loads_and_refreshes() -> None:
    """Selecting the Interactions sub-view renders the region that lazy-loads
    /api/interactions and live-updates via the shared SSE pipeline."""
    resp = asyncio.run(app_module.page_analytics(_request("/analytics"), view="interactions"))
    body = resp.body.decode()
    assert resp.status_code == 200
    assert 'id="interactions-region"' in body
    assert 'hx-get="/api/interactions"' in body
    # Reuses the SSE pipeline for live updates, like History/Memory.
    assert 'hx-trigger="load, refresh from:body"' in body


def test_standalone_interactions_nav_item_is_gone() -> None:
    """The primary nav no longer carries a standalone Interactions link — it is
    an Analytics switcher tab now. The board's masthead must not link to
    /interactions."""
    resp = asyncio.run(app_module.index(_request("/")))
    body = resp.body.decode()
    assert 'href="/interactions"' not in body
    # Analytics is the surface that now hosts it.
    assert 'href="/analytics"' in body


# ----- /api/interactions partial -----


def test_api_renders_rows_and_kind_chips(tmp_path, monkeypatch) -> None:
    beads_dir = tmp_path / ".beads"
    _seed(
        beads_dir,
        [
            {
                "id": "int-1",
                "kind": "tool_call",
                "created_at": "2026-01-02T00:00:00Z",
                "issue_id": "bdboard-aaa",
                "tool_name": "grep",
                "exit_code": 0,
            },
            {
                "id": "int-2",
                "kind": "llm_call",
                "created_at": "2026-01-03T00:00:00Z",
                "extra": {"model": "claude-x"},
            },
        ],
    )
    status, body = _call_api(beads_dir=beads_dir, monkeypatch=monkeypatch)
    assert status == 200
    # Kind chips with counts + an "All" chip.
    assert ">All <span" in body
    assert "tool_call" in body
    assert "llm_call" in body
    # Row summaries rendered.
    assert "grep (exit 0)" in body
    assert "model claude-x" in body
    # The bead link opens the SHARED modal (reuse, not a rebuilt audit view).
    assert 'hx-get="/api/bead/bdboard-aaa"' in body
    assert 'hx-target="#bead-modal"' in body


def test_api_kind_filter(tmp_path, monkeypatch) -> None:
    beads_dir = tmp_path / ".beads"
    _seed(
        beads_dir,
        [
            {
                "id": "a",
                "kind": "tool_call",
                "created_at": "2026-01-01T00:00:00Z",
                "tool_name": "ls",
            },
            {
                "id": "b",
                "kind": "llm_call",
                "created_at": "2026-01-02T00:00:00Z",
                "extra": {"model": "m1"},
            },
        ],
    )
    _, body = _call_api(kind="llm_call", beads_dir=beads_dir, monkeypatch=monkeypatch)
    # Only the llm_call row's summary shows; the tool_call row is filtered out.
    assert "model m1" in body
    assert "int-a" not in body or "ls" not in body
    # The llm_call chip reads as active (aria-pressed=true).
    assert 'aria-label="Show only llm_call interactions"' in body


def test_api_missing_log_degrades_gracefully(tmp_path, monkeypatch) -> None:
    # tmp workspace with NO interactions.jsonl at all.
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir(parents=True)
    status, body = _call_api(beads_dir=beads_dir, monkeypatch=monkeypatch)
    assert status == 200  # never 500s
    assert "No interaction log found yet" in body
    # Mentions the canonical path so the user knows where it'd appear.
    assert "interactions.jsonl" in body


def test_api_empty_kind_filter_message(tmp_path, monkeypatch) -> None:
    beads_dir = tmp_path / ".beads"
    _seed(
        beads_dir,
        [{"id": "a", "kind": "tool_call", "created_at": "2026-01-01T00:00:00Z", "tool_name": "ls"}],
    )
    # Filter for a kind that isn't present -> friendly "nothing of this kind".
    _, body = _call_api(kind="label", beads_dir=beads_dir, monkeypatch=monkeypatch)
    assert "No <code>label</code> interactions recorded yet" in body
