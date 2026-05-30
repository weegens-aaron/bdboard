"""Route tests for GET /api/bead/<id>/audit (modal lifecycle + audit trail).

Covers the deferred bead E enrichment (bdboard-7r8): the per-bead
status-transition timeline rendered above the audit trail in the bead modal.
We stub ``bd.history`` so no real subprocess runs, and assert that the same
fetched payload drives BOTH the lifecycle timeline and the audit diff (one
``bd history`` call, two views).
"""

from __future__ import annotations

import asyncio

from starlette.requests import Request

from bdboard import app as app_module


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/bead/x/audit",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _stub_history(entries, err=None):
    async def fake_history(bead_id):  # noqa: ARG001 - signature parity
        return entries, err

    app_module.bd.history = fake_history  # type: ignore[assignment]


def _call() -> tuple[int, str]:
    resp = asyncio.run(app_module.api_bead_audit(_request(), "x"))
    return resp.status_code, resp.body.decode()


def _hist(commit, status, date, committer="root"):
    return {
        "CommitHash": commit,
        "Committer": committer,
        "CommitDate": date,
        "Issue": {"status": status, "title": f"{status} snapshot"},
    }


def test_lifecycle_timeline_renders_transitions_and_dwell() -> None:
    _stub_history(
        [
            _hist("c3hashc3hashc3", "closed", "2026-05-30T12:00:00Z"),
            _hist("c2hashc2hashc2", "in_progress", "2026-05-29T12:00:00Z"),
            _hist("c1hashc1hashc1", "open", "2026-05-28T12:00:00Z"),
        ]
    )

    status, body = _call()

    assert status == 200
    # The lifecycle view exists and is distinct from the audit trail.
    assert "Lifecycle" in body
    assert "timeline-list" in body
    assert "Audit trail" in body
    # Each status stop is labelled by name (not colour-only) + dwell time.
    assert "in_progress" in body
    assert "for 24h" in body
    # The current (last) status is open-ended.
    assert "current" in body


def test_audit_error_skips_both_views() -> None:
    _stub_history(None, err="bd exploded")

    status, body = _call()

    assert status == 200
    assert "temporarily unavailable" in body
    assert "timeline-list" not in body


def test_no_history_shows_empty_note_without_timeline() -> None:
    _stub_history([])

    status, body = _call()

    assert status == 200
    assert "no recorded history yet" in body
    assert "timeline-list" not in body
