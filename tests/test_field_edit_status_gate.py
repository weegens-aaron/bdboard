"""Status-gating tests for manual field editing (bdboard-1lf).

Manual field editing (epic bdboard-o9v) only applies to beads that are still
OPEN. Once a bead is in_progress (claimed / work-in-flight) or closed
(historical record), its fields must be read-only:

  - UI: _ordered_fields() must NOT mark any field editable, so the modal
    renders no inline-edit / add-note affordances.
  - Server: POST /api/bead/{id}/field must reject the write (403) even if a
    crafted request reaches the endpoint, enforced from the LIVE bead status.

Open (and pre-work states that are neither claimed nor completed) stay
editable exactly as before.

These reuse the route harness from test_field_edit so the suites can't drift.
"""

from __future__ import annotations

from starlette.requests import Request

from bdboard import app as app_module
from test_field_edit import (
    _bead,
    _call_field,
    _stub_bus_broadcast,
    _stub_show_long,
    _stub_update_field,
)

# ───────────────────────── _bead_is_editable policy ────────────────────────


def test_open_bead_is_editable() -> None:
    assert app_module._bead_is_editable({"status": "open"}) is True


def test_missing_status_defaults_editable() -> None:
    """No lifecycle marker => treat as open => editable."""
    assert app_module._bead_is_editable({}) is True


def test_pre_work_states_stay_editable() -> None:
    """blocked / deferred are neither claimed nor completed — still editable."""
    assert app_module._bead_is_editable({"status": "blocked"}) is True
    assert app_module._bead_is_editable({"status": "deferred"}) is True


def test_in_progress_is_locked() -> None:
    assert app_module._bead_is_editable({"status": "in_progress"}) is False


def test_closed_statuses_are_locked() -> None:
    for status in ("closed", "resolved", "done"):
        assert app_module._bead_is_editable({"status": status}) is False, status


def test_status_match_is_case_insensitive() -> None:
    assert app_module._bead_is_editable({"status": "IN_PROGRESS"}) is False
    assert app_module._bead_is_editable({"status": "Closed"}) is False


# ───────────────────────── UI hint gating ─────────────────────────────────


def _rows_by_key(bead):
    return {r["key"]: r for r in app_module._ordered_fields(bead)}


def test_open_bead_rows_expose_editable_hints() -> None:
    rows = _rows_by_key(_bead(status="open"))
    assert rows["title"]["editable"] is True
    assert rows["notes"]["editable"] is True


def test_in_progress_bead_rows_are_all_readonly() -> None:
    rows = _rows_by_key(_bead(status="in_progress"))
    # Even registry-editable fields must be read-only on a claimed bead.
    assert rows["title"]["editable"] is False
    assert rows["description"]["editable"] is False
    assert rows["notes"]["editable"] is False
    # The editor metadata still rides along (the registry is unchanged);
    # only the *gate* flipped.
    assert rows["title"]["editor"] == "text"


def test_closed_bead_rows_are_all_readonly() -> None:
    rows = _rows_by_key(_bead(status="closed"))
    for key in ("title", "description", "priority", "notes"):
        assert rows[key]["editable"] is False, key


def _modal_html(bead) -> str:
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/bead/{bead['id']}",
            "query_string": b"",
            "headers": [],
        }
    )
    return app_module.TEMPLATES.TemplateResponse(
        req,
        "partials/bead_modal.html",
        {
            "bead": bead,
            "fields": app_module._ordered_fields(bead),
            "source": "test",
            "warning": None,
        },
    ).body.decode()


def test_locked_bead_modal_renders_no_edit_affordances() -> None:
    """End-to-end through the modal template: a closed bead's rendered HTML
    carries neither the inline-edit form nor the add-note affordance."""
    html = _modal_html(_bead(status="closed"))
    assert 'class="field-edit"' not in html
    assert "Add a note" not in html
    assert 'data-editable="1"' not in html


def test_open_bead_modal_renders_edit_affordances() -> None:
    """Contrast: an open bead's modal DOES expose the edit affordances."""
    html = _modal_html(_bead(status="open"))
    assert 'class="field-edit"' in html
    assert "Add a note" in html
    assert 'data-editable="1"' in html


# ───────────────────────── server-side enforcement ────────────────────────


def test_edit_rejected_on_in_progress_bead() -> None:
    """A field write must be refused (403) when the LIVE bead is in_progress,
    and must NEVER reach bd — even though the field itself is registry-editable."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(status="in_progress"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "sneaky edit"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 403
    assert "only open beads are editable" in body
    assert "in_progress" in body
    assert calls == [], "locked bead must never reach bd"


def test_edit_rejected_on_closed_bead() -> None:
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(status="closed"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "description", "value": "rewrite history"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 403
    assert "only open beads are editable" in body
    assert calls == []


def test_append_note_also_rejected_on_locked_bead() -> None:
    """The status gate covers append-only notes too — you can't bolt notes
    onto a claimed/closed bead via this path (the audit trail / append-notes
    flow is the proper channel for that)."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(status="closed"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "notes", "value": "late addition"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 403
    assert calls == []


def test_edit_allowed_on_open_bead() -> None:
    """Sanity: an open bead still edits cleanly through the gate."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(status="open", title="Renamed"))
    status, _body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "Renamed"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls == [("bdboard-x1", "--title", "Renamed", app_module._ACTOR)]


def test_unreadable_live_status_does_not_block_edit() -> None:
    """If the LIVE status read fails (bd hiccup), we degrade gracefully and
    let the edit proceed rather than hard-blocking on a read we couldn't make
    — the registry whitelist already bounds the blast radius."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(None)

    async def fake_snapshot():
        return {}

    app_module.store.snapshot = fake_snapshot  # type: ignore[assignment]
    app_module.store.bead = lambda _id: None  # type: ignore[assignment]
    status, _body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "x"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls, "unreadable status must not block the write"
