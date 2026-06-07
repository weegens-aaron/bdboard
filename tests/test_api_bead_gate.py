"""Route + helper tests for gate await-condition rendering (audit FB-3 / bdboard-wgsy).

Covers the modal-facing half of the gate fidelity work:
  - GET /api/bead/<id> for a gate bead injects an interpreted `gate_condition`
    row (a PR/run link / timer deadline / manual-only flag) ABOVE the raw
    await_* scalars, framing the gate as a pending WAIT.
  - The raw await_type / await_id fields are STILL rendered (the anatomy
    invariant: bdboard drops no bd field).
  - _repo_base_url() normalises common git remote shapes to an https repo base
    URL, host-agnostic (enterprise GitHub included), and degrades to None when
    there's no remote.

bd.show_long is stubbed so no real subprocess runs.
"""

from __future__ import annotations

import asyncio
import subprocess
from types import SimpleNamespace

from starlette.requests import Request

from bdboard import app as app_module


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/bead/x",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _stub_show_long(bead: dict):
    async def fake_show_long(bead_id, fresh=False):  # noqa: ARG001 - parity
        return bead, None

    app_module.bd.show_long = fake_show_long  # type: ignore[assignment]


def _call(bead_id: str = "gt-1") -> tuple[int, str]:
    resp = asyncio.run(app_module.api_bead(_request(), bead_id))
    return resp.status_code, resp.body.decode()


def _gate(await_type: str, **extra) -> dict:
    bead = {
        "id": "gt-1",
        "title": f"Gate: {await_type}",
        "issue_type": "gate",
        "status": "open",
        "await_type": await_type,
        "created_at": "2026-06-07T00:00:00Z",
        "updated_at": "2026-06-07T00:00:00Z",
    }
    bead.update(extra)
    return bead


# ----- modal: gate condition row -----


def test_gate_modal_renders_pr_link(monkeypatch):
    """AC2: a gh:pr gate renders a clickable PR link in the modal."""
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: "https://github.com/owner/repo")
    _stub_show_long(_gate("gh:pr", await_id="42"))

    status, body = _call()

    assert status == 200
    assert "gate-condition" in body
    assert "https://github.com/owner/repo/pull/42" in body
    assert "PR #42" in body
    # Raw await_* fields are still surfaced (anatomy: drop no field).
    assert "await_type" in body
    assert "await_id" in body


def test_gate_modal_renders_run_link(monkeypatch):
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: "https://github.com/owner/repo")
    _stub_show_long(_gate("gh:run", await_id="987654"))

    status, body = _call()

    assert status == 200
    assert "https://github.com/owner/repo/actions/runs/987654" in body


def test_gate_modal_timer_shows_deadline(monkeypatch):
    """AC2: a timer gate shows a deadline (no link)."""
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)
    _stub_show_long(_gate("timer", timeout=7_200_000_000_000))

    status, body = _call()

    assert status == 200
    assert "gate-condition-deadline" in body
    assert "2026-06-07T02:00:00Z" in body


def test_gate_modal_human_flags_manual_only(monkeypatch):
    """AC2: a human gate is flagged manual-only."""
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)
    _stub_show_long(_gate("human"))

    status, body = _call()

    assert status == 200
    assert "gate-manual-flag" in body
    assert "manual only" in body


def test_non_gate_modal_has_no_gate_condition(monkeypatch):
    monkeypatch.setattr(app_module, "_repo_base_url", lambda: None)
    _stub_show_long(
        {
            "id": "t1",
            "title": "Plain task",
            "issue_type": "task",
            "status": "open",
            "created_at": "2026-06-07T00:00:00Z",
            "updated_at": "2026-06-07T00:00:00Z",
        }
    )

    status, body = _call("t1")

    assert status == 200
    assert "gate-condition" not in body


# ----- _repo_base_url parsing -----


def _stub_git_remote(monkeypatch, url: str | None, returncode: int = 0):
    def fake_run(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(returncode=returncode, stdout=(url or ""), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    app_module._repo_base_url.cache_clear()


def test_repo_base_url_parses_https_remote(monkeypatch):
    _stub_git_remote(monkeypatch, "https://github.com/owner/repo.git")
    assert app_module._repo_base_url() == "https://github.com/owner/repo"


def test_repo_base_url_parses_ssh_scp_remote(monkeypatch):
    _stub_git_remote(monkeypatch, "git@github.com:owner/repo.git")
    assert app_module._repo_base_url() == "https://github.com/owner/repo"


def test_repo_base_url_parses_enterprise_host(monkeypatch):
    _stub_git_remote(monkeypatch, "git@gecgithub01.walmart.com:team/proj.git")
    assert app_module._repo_base_url() == "https://gecgithub01.walmart.com/team/proj"


def test_repo_base_url_none_when_no_remote(monkeypatch):
    _stub_git_remote(monkeypatch, None, returncode=1)
    assert app_module._repo_base_url() is None
    app_module._repo_base_url.cache_clear()
