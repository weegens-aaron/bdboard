"""Tests for the manual field-edit write path (bdboard-o9v.2).

Covers two surfaces:
  - BdClient.update_field: arg construction (flag + value vs stdin file-flag),
    --actor forwarding, cache invalidation, and stderr surfacing on failure.
  - POST /api/bead/{id}/field: CSRF guard, registry validation (reject
    non-editable / unknown fields), append-only guard, SSE broadcast, and
    optimistic re-render of just the edited field row.

These exercise the write path WITHOUT shelling a real bd: bd.update_field is
stubbed at the route layer, and the bd binary is replaced by a fake script for
the client-level arg/stdin tests.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module
from bdboard.bd import BdClient

# ───────────────────────── route helpers ──────────────────────────────────


def _post_request(
    bead_id: str,
    form_data: dict[str, str],
    csrf_header: str | None = None,
) -> Request:
    body = "&".join(f"{k}={v}" for k, v in form_data.items()).encode()
    headers = [(b"content-type", b"application/x-www-form-urlencoded")]
    if csrf_header:
        headers.append((b"x-csrf-token", csrf_header.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": f"/api/bead/{bead_id}/field",
        "query_string": b"",
        "headers": headers,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _stub_update_field(error: Exception | None = None) -> list[tuple]:
    """Stub bd.update_field to record calls and optionally raise."""
    calls: list[tuple] = []

    async def fake_update_field(bead_id, flag, value, actor=None):
        calls.append((bead_id, flag, value, actor))
        if error:
            raise error

    app_module.bd.update_field = fake_update_field  # type: ignore[assignment]
    return calls


def _stub_show_long(bead: dict[str, Any] | None) -> None:
    async def fake_show_long(bead_id: str, fresh: bool = False):
        if bead is None:
            return None, "boom"
        return bead, None

    app_module.bd.show_long = fake_show_long  # type: ignore[assignment]


def _stub_bus_broadcast() -> list[str]:
    calls: list[str] = []

    async def fake_broadcast(event: str) -> None:
        calls.append(event)

    app_module.bus.broadcast = fake_broadcast  # type: ignore[assignment]
    return calls


def _call_field(
    bead_id: str,
    form_data: dict[str, str],
    csrf_header: str | None = None,
    csrf_form: str | None = None,
) -> tuple[int, str]:
    resp = asyncio.run(
        app_module.api_bead_field_update(
            _post_request(bead_id, form_data, csrf_header),
            bead_id=bead_id,
            field=form_data.get("field", ""),
            value=form_data.get("value", ""),
            expected_updated_at=form_data.get("expected_updated_at", ""),
            csrf=csrf_form or form_data.get("csrf_token"),
            x_csrf_token=csrf_header,
        )
    )
    return resp.status_code, resp.body.decode()


def _bead(**overrides) -> dict[str, Any]:
    base = {
        "id": "bdboard-x1",
        "title": "Some title",
        "description": "Body **md**",
        "priority": 2,
        "notes": "existing notes",
        "updated_at": "2026-05-30T21:22:12Z",
    }
    base.update(overrides)
    return base


# ───────────────────────── route: CSRF ────────────────────────────────────


def test_field_update_requires_csrf_token() -> None:
    _stub_update_field()
    from fastapi import HTTPException

    try:
        asyncio.run(
            app_module.api_bead_field_update(
                _post_request("bdboard-x1", {"field": "title", "value": "x"}),
                bead_id="bdboard-x1",
                field="title",
                value="x",
                csrf=None,
                x_csrf_token=None,
            )
        )
        raised = False
    except HTTPException as e:
        raised = True
        assert e.status_code == 403
        assert "CSRF" in e.detail
    assert raised, "Expected HTTPException for missing CSRF"


# ───────────────────────── route: registry validation ─────────────────────


def test_field_update_rejects_non_editable_field() -> None:
    calls = _stub_update_field()
    _stub_bus_broadcast()
    status, body = _call_field(
        "bdboard-x1",
        {"field": "status", "value": "closed"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 400
    assert "not editable" in body
    assert calls == [], "must never invoke bd for a non-editable field"


def test_field_update_rejects_unknown_field() -> None:
    calls = _stub_update_field()
    status, body = _call_field(
        "bdboard-x1",
        {"field": "totally_made_up", "value": "x"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 400
    assert "not editable" in body
    assert calls == []


def test_field_update_uses_registry_flag_not_client_input() -> None:
    """The client picks the FIELD; the registry picks the FLAG."""
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(title="New title"))
    status, _body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "New title"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls == [("bdboard-x1", "--title", "New title", app_module._ACTOR)]


def test_field_update_notes_uses_append_flag() -> None:
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(notes="old notes\n\nnew bit"))
    status, _body = _call_field(
        "bdboard-x1",
        {"field": "notes", "value": "new bit"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls[0][1] == "--append-notes"


def test_field_update_append_only_rejects_empty() -> None:
    calls = _stub_update_field()
    status, body = _call_field(
        "bdboard-x1",
        {"field": "notes", "value": "   "},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 400
    assert "Nothing to add" in body
    assert calls == []


# ───── UI affordance: append-only 'Add a note' (bdboard-o9v.4) ─────────────


def test_notes_row_renders_add_a_note_affordance() -> None:
    """The re-rendered notes row must carry the append-only 'Add a note'
    form framed as ADDING, posting field=notes (server pins --append-notes)."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(notes="existing history\n\nfresh note"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "notes", "value": "fresh note"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    # Framed as 'Add a note', not 'edit notes'.
    assert "Add a note" in body
    # Posts to the field route with field=notes; server picks --append-notes.
    assert 'name="field" value="notes"' in body
    assert 'hx-post="/api/bead/bdboard-x1/field"' in body
    # The hint makes the append (not replace) semantics explicit.
    assert "added" in body.lower()


def test_notes_add_textarea_is_never_prefilled_with_existing_notes() -> None:
    """CRITICAL: the textarea must be EMPTY — a prefilled box invites a
    destructive replace. Existing notes render above (read-only), never
    inside an editable replace textarea."""
    _stub_update_field()
    _stub_bus_broadcast()
    sentinel = "VERIFICATION-EVIDENCE-DO-NOT-CLOBBER"
    _stub_show_long(_bead(notes=f"{sentinel}\n\nfresh note"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "notes", "value": "fresh note"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    # The existing notes show in the read-only value area (markdown prose)...
    assert sentinel in body
    # ...but NOT inside the add-note textarea (which must be empty).
    ta_open = body.index("<textarea")
    ta_close = body.index("</textarea>", ta_open)
    assert sentinel not in body[ta_open:ta_close], (
        "add-note textarea must be empty — a prefilled value risks a "
        "destructive replace of agent verification history"
    )


def test_non_append_field_row_has_no_add_a_note_form() -> None:
    """A plain editable field (title) must NOT render the notes-only
    append affordance."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(title="Renamed"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "Renamed"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert "Add a note" not in body


# ───── UI affordance: inline edit (replace semantics) (bdboard-o9v.3) ──────


def test_editable_field_row_renders_inline_edit_form() -> None:
    """An editable replace-semantics field (title) renders the inline-edit
    <details> form posting to the field route with a real <label> and a
    polite aria-live feedback region (WCAG 2.2 AA)."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(title="Renamed"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "Renamed"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert 'class="field-edit"' in body
    assert "Edit title" in body
    assert 'hx-post="/api/bead/bdboard-x1/field"' in body
    assert 'name="field" value="title"' in body
    # Real label bound to the input id.
    assert 'for="field-edit-input-title"' in body
    assert 'id="field-edit-input-title"' in body
    # Polite aria-live feedback slot for save/error announcements.
    assert 'aria-live="polite"' in body
    assert "data-edit-feedback" in body


def test_text_field_edit_prefills_current_value() -> None:
    """Replace-semantics text editors are PREFILLED with the current value
    (unlike the append-only notes textarea, which must stay empty)."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(title="Current Title Here"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "Current Title Here"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert 'value="Current Title Here"' in body


def test_select_field_edit_renders_enum_options_with_selected() -> None:
    """priority (select editor) renders all enum options, labels P0..P4, and
    marks the current value selected."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(priority=3))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "priority", "value": "3"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert "<select" in body
    # Human-friendly P-prefixed labels.
    assert ">P0<" in body and ">P3<" in body
    # The current value (3) is selected.
    sel = body.index('value="3"')
    assert "selected" in body[sel : sel + 40]


def test_priority_edit_appends_oob_header_badge() -> None:
    """Regression bdboard-nuy: editing priority must also re-render the modal
    header badge via an out-of-band swap so it stays in sync with the field
    without closing/reopening the modal."""
    _stub_update_field()
    _stub_bus_broadcast()
    # Bead now at priority 0 after the edit.
    _stub_show_long(_bead(priority=0))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "priority", "value": "0"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    # The OOB header-badge slot is appended, targeting the modal header by id.
    assert 'id="modal-priority-badge-bdboard-x1"' in body
    assert 'hx-swap-oob="true"' in body
    # It carries the NEW priority class.
    assert "bead-priority p0" in body


def test_non_priority_edit_omits_oob_header_badge() -> None:
    """Editing a non-priority field must NOT append the header-badge OOB swap
    (no spurious header churn)."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(title="Renamed"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "Renamed"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert "modal-priority-badge-" not in body


def test_number_field_edit_renders_number_input() -> None:
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(estimate=120))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "estimate", "value": "120"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert 'type="number"' in body
    assert 'value="120"' in body


def test_markdown_field_edit_renders_textarea_prefilled() -> None:
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(description="Body **md** content"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "description", "value": "Body **md** content"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert 'class="field-edit-textarea"' in body
    ta_open = body.index('class="field-edit-textarea"')
    ta_close = body.index("</textarea>", ta_open)
    assert "Body **md** content" in body[ta_open:ta_close]


def test_notes_row_has_no_replace_inline_edit_form() -> None:
    """CRITICAL: append-only notes must NEVER get the replace-semantics
    inline-edit form (that would route to a destructive replace). Only the
    'Add a note' append affordance is allowed."""
    _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead(notes="history\n\nnew"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "notes", "value": "new"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert 'class="field-edit"' not in body
    assert "Add a note" in body


# ───────────────────────── route: success path ────────────────────────────


def test_field_update_broadcasts_sse_and_renders_row() -> None:
    _stub_update_field()
    broadcasts = _stub_bus_broadcast()
    _stub_show_long(_bead(title="Renamed"))
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "Renamed"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert "beads_changed" in broadcasts
    # The re-rendered row carries the stable swap id + the new value.
    assert 'id="field-row-title"' in body
    assert "Renamed" in body


def test_field_update_surfaces_bd_error() -> None:
    _stub_update_field(RuntimeError("bd said no"))
    _stub_bus_broadcast()
    status, body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "x"},
        csrf_header=app_module._CSRF_TOKEN,
    )
    assert status == 500
    assert "Could not save" in body
    assert "bd said no" in body


def test_field_update_accepts_csrf_form_field() -> None:
    calls = _stub_update_field()
    _stub_bus_broadcast()
    _stub_show_long(_bead())
    status, _body = _call_field(
        "bdboard-x1",
        {"field": "title", "value": "x", "csrf_token": app_module._CSRF_TOKEN},
        csrf_form=app_module._CSRF_TOKEN,
    )
    assert status == 200
    assert calls


# ───────────────────────── BdClient.update_field ──────────────────────────


def _fake_bd_client(
    tmp_path: Path, *, exit_code: int = 0, stderr: str = ""
) -> tuple[BdClient, Path]:
    """Build a BdClient pointed at a fake `bd` that logs its argv + stdin.

    The fake writes one line per argv token to argv.log, dumps stdin to
    stdin.log, then exits with the configured code/stderr.
    """
    workspace = tmp_path / "ws"
    (workspace / ".beads").mkdir(parents=True)
    argv_log = tmp_path / "argv.log"
    stdin_log = tmp_path / "stdin.log"
    fake = tmp_path / "fakebd"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" > "{argv_log}"\n'
        f'cat > "{stdin_log}"\n'
        f'>&2 printf "%s" "{stderr}"\n'
        f"exit {exit_code}\n"
    )
    fake.chmod(0o755)
    client = BdClient(bd_bin=str(fake), workspace=workspace)
    return client, tmp_path


def test_update_field_passes_value_as_arg(tmp_path: Path) -> None:
    client, logs = _fake_bd_client(tmp_path)
    asyncio.run(client.update_field("bdboard-x1", "--title", "New Title", actor="Aaron"))
    argv = (logs / "argv.log").read_text().splitlines()
    assert argv == ["update", "bdboard-x1", "--title", "New Title", "--actor", "Aaron"]
    # short scalar => no stdin payload
    assert (logs / "stdin.log").read_text() == ""


def test_update_field_streams_markdown_via_stdin(tmp_path: Path) -> None:
    client, logs = _fake_bd_client(tmp_path)
    long_md = "# Heading\n\n" + ("lorem ipsum " * 500)
    asyncio.run(client.update_field("bdboard-x1", "--description", long_md))
    argv = (logs / "argv.log").read_text().splitlines()
    # description routes through the file-flag + stdin, NOT a positional arg.
    assert argv == ["update", "bdboard-x1", "--body-file", "-"]
    assert (logs / "stdin.log").read_text() == long_md


def test_update_field_design_uses_design_file(tmp_path: Path) -> None:
    client, logs = _fake_bd_client(tmp_path)
    asyncio.run(client.update_field("bdboard-x1", "--design", "design body"))
    argv = (logs / "argv.log").read_text().splitlines()
    assert argv == ["update", "bdboard-x1", "--design-file", "-"]
    assert (logs / "stdin.log").read_text() == "design body"


def test_update_field_omits_actor_when_none(tmp_path: Path) -> None:
    client, logs = _fake_bd_client(tmp_path)
    asyncio.run(client.update_field("bdboard-x1", "--title", "X", actor=None))
    argv = (logs / "argv.log").read_text().splitlines()
    assert "--actor" not in argv


def test_update_field_clears_show_cache(tmp_path: Path) -> None:
    from bdboard.bd import CacheEntry

    client, _logs = _fake_bd_client(tmp_path)
    client._show_cache["bdboard-x1"] = CacheEntry(0.0, {"id": "x"}, None)
    asyncio.run(client.update_field("bdboard-x1", "--title", "X"))
    assert client._show_cache == {}


def test_update_field_surfaces_stderr_on_failure(tmp_path: Path) -> None:
    client, _logs = _fake_bd_client(tmp_path, exit_code=1, stderr="invalid priority")
    raised = False
    try:
        asyncio.run(client.update_field("bdboard-x1", "--priority", "9"))
    except RuntimeError as e:
        raised = True
        assert "invalid priority" in str(e)
    assert raised, "non-zero bd exit must raise"


def test_show_long_fresh_bypasses_show_cache(tmp_path: Path) -> None:
    """show_long(fresh=True) must drop the cached entry so the
    optimistic-lock precondition (bdboard-o9v.5) reads LIVE state and a
    stale cache can't mask a concurrent change."""
    from bdboard.bd import CacheEntry

    client, _logs = _fake_bd_client(tmp_path)
    # Seed a fresh (non-expired) cache entry the normal path would serve.
    client._show_cache["bdboard-x1"] = CacheEntry(
        fetched_at=__import__("time").monotonic(),
        value=[{"id": "bdboard-x1", "updated_at": "STALE"}],
        error=None,
    )
    # fresh=False would return the cached STALE value; assert it does.
    cached, _ = asyncio.run(client.show_long("bdboard-x1"))
    assert cached is not None and cached.get("updated_at") == "STALE"
    # fresh=True drops the entry, forcing a live read (the fake bd emits no
    # JSON, so the read errors — but crucially the stale entry is gone).
    assert "bdboard-x1" in client._show_cache
    asyncio.run(client.show_long("bdboard-x1", fresh=True))
    # The pre-seeded STALE entry must not survive a fresh read.
    surviving = client._show_cache.get("bdboard-x1")
    assert surviving is None or surviving.value != [{"id": "bdboard-x1", "updated_at": "STALE"}]
