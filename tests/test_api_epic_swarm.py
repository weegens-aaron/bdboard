"""Route tests for the epic rollup + swarm panel (bdboard-je14, FB-10).

Three surfaces, three of the bead's acceptance criteria:
  - GET /api/lanes stamps a child count/progress rollup onto each epic chip
    (AC1: the epic strip shows a child count/progress rollup).
  - GET /api/epic/<id>/swarm renders progress % + Completed/Active/Ready/
    Blocked cohorts (AC2) and the Wave model with max parallelism (AC3).
  - The bead modal lazily wires the swarm panel for epics only.

bd verbs + the store snapshot are stubbed so no real subprocess runs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module


def _request(path: str = "/") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
        }
    )


# ----- /api/lanes epic-strip rollup -----


def test_lanes_stamps_epic_rollup_badge(monkeypatch):
    """AC1: the epic strip shows a child count/progress rollup."""
    epic = {
        "id": "bdboard-atvy",
        "title": "Remediate display gaps",
        "issue_type": "epic",
        "status": "in_progress",
        "priority": 1,
    }

    async def fake_snapshot_active() -> list:
        return [epic]

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        return None, None  # hydrate keeps the snapshot bead as-is

    async def fake_mol_progress(epic_id: str) -> dict:
        assert epic_id == "bdboard-atvy"
        return {"total": 14, "completed": 10, "in_progress": 1, "percent": 71.4}

    monkeypatch.setattr(app_module.store, "snapshot_active", fake_snapshot_active)
    monkeypatch.setattr(app_module.store, "cached_known_ids", lambda: {"bdboard-atvy"})
    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module.bd, "mol_progress", fake_mol_progress)

    resp = asyncio.run(app_module.api_lanes(_request("/api/lanes")))
    body = resp.body.decode()

    assert resp.status_code == 200
    assert "epic-rollup" in body
    assert "10/14" in body
    assert "71%" in body
    assert 'style="width: 71%"' in body


def test_lanes_omits_rollup_when_mol_progress_fails(monkeypatch):
    """A failed rollup degrades silently (no badge), board still renders."""
    epic = {
        "id": "bdboard-atvy",
        "title": "Childless epic",
        "issue_type": "epic",
        "status": "open",
    }

    async def fake_snapshot_active() -> list:
        return [epic]

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        return None, None

    async def boom(epic_id: str) -> dict:
        raise RuntimeError("no children")

    monkeypatch.setattr(app_module.store, "snapshot_active", fake_snapshot_active)
    monkeypatch.setattr(app_module.store, "cached_known_ids", lambda: set())
    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module.bd, "mol_progress", boom)

    resp = asyncio.run(app_module.api_lanes(_request("/api/lanes")))
    body = resp.body.decode()

    assert resp.status_code == 200
    assert "epic-rollup" not in body
    # The epic chip itself still rendered.
    assert "bdboard-atvy" in body


# ----- /api/epic/<id>/swarm panel -----


def _swarm_status() -> dict:
    return {
        "active": [{"assignee": "Aaron", "id": "bdboard-je14", "title": "Rollup"}],
        "active_count": 1,
        "blocked": [],
        "blocked_count": 0,
        "completed": [{"id": "bdboard-2n6g", "title": "Glyphs", "closed_at": "x"}],
        "epic_id": "bdboard-atvy",
        "epic_title": "Remediate",
        "progress_percent": 71.4,
        "ready": [{"id": "bdboard-lwiv", "title": "Dolt sync"}],
        "ready_count": 1,
        "total_issues": 14,
    }


def _swarm_validate() -> dict:
    return {
        "epic_id": "bdboard-atvy",
        "errors": None,
        "estimated_sessions": 14,
        "max_parallelism": 3,
        "ready_fronts": [
            {"issues": ["bdboard-lwiv"], "titles": ["Dolt sync"], "wave": 0},
        ],
        "swarmable": True,
        "total_issues": 14,
        "warnings": None,
    }


def _stub_swarm(monkeypatch, *, status: Any, validate: Any) -> None:
    async def fake_status(epic_id: str) -> Any:
        if isinstance(status, Exception):
            raise status
        return status

    async def fake_validate(epic_id: str) -> Any:
        if isinstance(validate, Exception):
            raise validate
        return validate

    monkeypatch.setattr(app_module.bd, "swarm_status", fake_status)
    monkeypatch.setattr(app_module.bd, "swarm_validate", fake_validate)


def test_swarm_panel_renders_progress_cohorts_and_waves(monkeypatch):
    """AC2 + AC3: progress %, the four cohorts, and the Wave model."""
    _stub_swarm(monkeypatch, status=_swarm_status(), validate=_swarm_validate())

    resp = asyncio.run(
        app_module.api_epic_swarm(_request("/api/epic/bdboard-atvy/swarm"), "bdboard-atvy")
    )
    body = resp.body.decode()

    assert resp.status_code == 200
    # AC2: progress + cohorts.
    assert "71%" in body
    assert "Completed" in body and "Active" in body
    assert "Ready" in body and "Blocked" in body
    assert "bdboard-2n6g" in body  # a completed child id
    # AC3: waves + max parallelism.
    assert "Wave 1" in body  # bd's 0-based -> human 1-based
    assert "max parallelism 3" in body
    assert "swarmable" in body


def test_swarm_panel_degrades_when_both_fail(monkeypatch):
    """Both bd calls fail -> single inline retry message, not a 500."""
    _stub_swarm(
        monkeypatch,
        status=RuntimeError("boom"),
        validate=RuntimeError("boom"),
    )

    resp = asyncio.run(app_module.api_epic_swarm(_request("/api/epic/x/swarm"), "x"))
    body = resp.body.decode()

    assert resp.status_code == 200
    assert "swarm-error" in body
    assert "try again" in body.lower()


def test_swarm_panel_partial_when_only_validate_fails(monkeypatch):
    """status OK, validate fails -> cohorts render, no waves section."""
    _stub_swarm(monkeypatch, status=_swarm_status(), validate=RuntimeError("boom"))

    resp = asyncio.run(
        app_module.api_epic_swarm(_request("/api/epic/bdboard-atvy/swarm"), "bdboard-atvy")
    )
    body = resp.body.decode()

    assert resp.status_code == 200
    assert "71%" in body  # cohorts/progress still there
    assert "swarm-wave-list" not in body  # waves section absent


# ----- bead modal wiring -----


def test_modal_wires_swarm_panel_for_epic(monkeypatch):
    epic = {
        "id": "bdboard-atvy",
        "title": "An epic",
        "issue_type": "epic",
        "status": "in_progress",
        "created_at": "2026-06-07T00:00:00Z",
        "updated_at": "2026-06-07T00:00:00Z",
    }

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        return epic, None

    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)

    resp = asyncio.run(app_module.api_bead(_request("/api/bead/bdboard-atvy"), "bdboard-atvy"))
    body = resp.body.decode()

    assert resp.status_code == 200
    assert "/api/epic/bdboard-atvy/swarm" in body


def test_modal_skips_swarm_panel_for_non_epic(monkeypatch):
    task = {
        "id": "bdboard-je14",
        "title": "A task",
        "issue_type": "task",
        "status": "in_progress",
        "created_at": "2026-06-07T00:00:00Z",
        "updated_at": "2026-06-07T00:00:00Z",
    }

    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001
        return task, None

    monkeypatch.setattr(app_module.bd, "show_long", fake_show_long)
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)

    resp = asyncio.run(app_module.api_bead(_request("/api/bead/bdboard-je14"), "bdboard-je14"))
    body = resp.body.decode()

    assert resp.status_code == 200
    assert "/api/epic/" not in body
