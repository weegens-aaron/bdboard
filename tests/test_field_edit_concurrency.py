"""Optimistic-lock concurrency tests for the field-edit route (bdboard-o9v.5).

Multiple tabs (or a human + an agent) can edit the same bead. The
_subprocess_gate serializes the *writes*, but a stale form posted from one tab
would otherwise clobber a concurrent edit (last-write-wins). The route runs an
`updated_at` precondition: it re-reads the bead LIVE before writing and rejects
a stale submit with a friendly "bead changed, please refresh" (HTTP 409)
instead of silently overwriting.

These reuse the route harness from test_field_edit (same stubbing style: bd is
never actually shelled here) so the two suites can't drift.
"""

from __future__ import annotations

from bdboard import app as app_module
from test_field_edit import (
    _bead,
    _call_field,
    _stub_bus_broadcast,
    _stub_show_long,
    _stub_update_field,
)


def test_stale_form_rejected_without_clobber() -> None:
    """A submit whose expected_updated_at is older than the live bead's must
    be rejected (409) and must NEVER reach bd — i.e. no silent clobber."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    # Live bead has moved on since the form was rendered.
    _stub_show_long(_bead(updated_at="2026-05-30T23:59:59Z"))
    status, body = _call_field(
        "bdboard-x1",
        {
            "field": "title",
            "value": "My stale edit",
            "expected_updated_at": "2026-05-30T21:22:12Z",
        },
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 409
    assert "changed" in body.lower()
    assert "refresh" in body.lower()
    assert calls == [], "stale edit must never reach bd (no clobber)"


def test_matching_updated_at_proceeds() -> None:
    """When the form's token matches the live bead, the edit proceeds."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(updated_at="2026-05-30T21:22:12Z", title="Fresh"))
    status, _body = _call_field(
        "bdboard-x1",
        {
            "field": "title",
            "value": "Fresh",
            "expected_updated_at": "2026-05-30T21:22:12Z",
        },
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls == [("bdboard-x1", "--title", "Fresh", app_module._ACTOR)]


def test_no_token_skips_lock() -> None:
    """Backwards-compat: a form with no expected_updated_at (older UI) skips
    the precondition and degrades to last-write-wins rather than blocking."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(updated_at="2026-05-30T23:59:59Z", title="x"))
    status, _body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "x"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls, "no token => no precondition => edit proceeds"


def test_notes_append_skips_lock_even_if_stale() -> None:
    """Append-only notes never clobber, so the precondition is skipped even
    with a stale token — the append still applies."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(updated_at="2026-05-30T23:59:59Z", notes="old\n\nnew"))
    status, _body = _call_field(
        "bdboard-x1",
        {
            "field": "notes",
            "value": "new",
            "expected_updated_at": "2026-05-30T21:22:12Z",
        },
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls[0][1] == "--append-notes"


def test_unreadable_precondition_does_not_block_write() -> None:
    """If the precondition's live re-read fails (bd hiccup), we don't block
    the edit on a read we couldn't make — degrade to prior behaviour."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    # show_long returns (None, err) for BOTH the precondition read and the
    # post-write re-render; the route still saves and acks gracefully.
    _stub_show_long(None)

    async def fake_snapshot():
        return {}

    app_module.store.snapshot = fake_snapshot  # type: ignore[assignment]
    app_module.store.bead = lambda _id: None  # type: ignore[assignment]
    status, _body = _call_field(
        "bdboard-x1",
        {
            "field": "title",
            "value": "x",
            "expected_updated_at": "2026-05-30T21:22:12Z",
        },
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls, "unreadable precondition must not block the write"


def test_rendered_row_carries_fresh_token() -> None:
    """The re-rendered inline-edit form must embed the fresh updated_at so the
    NEXT edit from this row carries an up-to-date precondition token."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(updated_at="2026-05-31T08:00:00Z", title="Renamed"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "Renamed"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert 'name="expected_updated_at"' in body
    assert 'value="2026-05-31T08:00:00Z"' in body
