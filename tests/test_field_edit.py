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
    async def fake_show_long(bead_id: str):
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
