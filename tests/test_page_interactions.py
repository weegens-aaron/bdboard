"""Route tests for the swarm interaction-log viewer (bead bdboard-bghy).

Covers:
  - GET /interactions returns 200, extends base.html, and is the active nav page
  - the page lazy-loads its region from /api/interactions on load + SSE refresh
  - the shared nav now exposes the Interactions link on every page
  - GET /api/interactions renders kind filter chips + entry rows
  - ?kind= filters the list to one kind
  - a missing interactions.jsonl degrades to a friendly empty state (no 500)
  - the per-bead bd-history Audit modal is NOT touched by this feature

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


def _call_page() -> tuple[int, str]:
    resp = asyncio.run(app_module.page_interactions(_request()))
    return resp.status_code, resp.body.decode()


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


# ----- page shell -----


def test_page_renders_full_document() -> None:
    status, body = _call_page()
    assert status == 200
    assert "<!doctype html>" in body.lower()
    assert "<title>Interactions" in body
    assert 'class="masthead"' in body


def test_page_region_lazy_loads_and_refreshes() -> None:
    _, body = _call_page()
    assert 'id="interactions-region"' in body
    assert 'hx-get="/api/interactions"' in body
    # Reuses the SSE pipeline for live updates, like History/Memory.
    assert 'hx-trigger="load, refresh from:body"' in body


def test_page_nav_marks_interactions_active() -> None:
    _, body = _call_page()
    assert 'aria-label="Primary"' in body
    assert 'href="/interactions"' in body
    # Interactions is the active page here (is-active + aria-current).
    assert 'href="/interactions"\n     class="mh-link is-active"' in body


def test_other_pages_expose_interactions_link() -> None:
    # The shared nav partial must surface the link everywhere (board here).
    resp = asyncio.run(app_module.index(_request("/")))
    assert 'href="/interactions"' in resp.body.decode()


def test_page_surfaces_workspace_error(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_validate_or_warn", lambda: "bd not found")
    resp = asyncio.run(app_module.page_interactions(_request()))
    assert resp.status_code == 500
    assert "bd not found" in resp.body.decode()


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
