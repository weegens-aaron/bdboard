"""Route tests for the formula-pour UI (bdboard-ain.1).

Covers GET /api/formulas (picker), GET /api/formulas/{name}/form (variable
form from the parsed *.formula.json), and POST /api/formulas/{name}/pour:
  - CSRF validation
  - pre-flight blocking of required (no-default) variables
  - pour success -> rename grouping node -> optimistic SSE broadcast
  - bd stderr surfaced on pour failure (the --dry-run-can't-catch case)
  - default fallback for blank fields
"""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module


def _get_request(path: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _post_request(
    path: str,
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
        "path": path,
        "query_string": b"",
        "headers": headers,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


# ----- stubs -----


def _stub_list_formulas(result: Any) -> None:
    async def fake(*args, **kwargs) -> Any:
        if isinstance(result, Exception):
            raise result
        return result

    app_module.bd.list_formulas = fake  # type: ignore[assignment]


def _stub_read_vars(result: Any) -> None:
    def fake(source: str) -> Any:
        if isinstance(result, Exception):
            raise result
        return result

    app_module.bd.read_formula_variables = fake  # type: ignore[assignment]


def _stub_pour(result: Any) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []

    async def fake(name: str, variables: dict) -> Any:
        calls.append((name, variables))
        if isinstance(result, Exception):
            raise result
        return result

    app_module.bd.pour_formula = fake  # type: ignore[assignment]
    return calls


def _stub_rename() -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def fake(bead_id: str, title: str) -> None:
        calls.append((bead_id, title))

    app_module.bd.rename_bead = fake  # type: ignore[assignment]
    return calls


def _stub_broadcast() -> list[str]:
    calls: list[str] = []

    async def fake(event: str) -> None:
        calls.append(event)

    app_module.bus.broadcast = fake  # type: ignore[assignment]
    return calls


# ----- GET /api/formulas -----


def test_api_formulas_renders_picker() -> None:
    _stub_list_formulas([{"name": "code-health-audit", "description": "Audit", "source": "/x"}])
    resp = asyncio.run(app_module.api_formulas(_get_request("/api/formulas")))
    body = resp.body.decode()
    assert resp.status_code == 200
    assert "code-health-audit" in body
    assert "Audit" in body


def test_api_formulas_degrades_on_bd_failure() -> None:
    _stub_list_formulas(RuntimeError("bd down"))
    resp = asyncio.run(app_module.api_formulas(_get_request("/api/formulas")))
    assert resp.status_code == 200
    assert "Couldn" in resp.body.decode()


# ----- GET /api/formulas/{name}/form -----


def test_api_formula_form_renders_variables() -> None:
    _stub_list_formulas(
        [{"name": "demo", "description": "Demo formula", "source": "/x.formula.json"}]
    )
    _stub_read_vars(
        [
            {
                "name": "repo",
                "description": "Repo",
                "default": "bdboard",
                "required": False,
            },
            {
                "name": "token",
                "description": "Token",
                "default": None,
                "required": True,
            },
        ]
    )
    resp = asyncio.run(app_module.api_formula_form(_get_request("/api/formulas/demo/form"), "demo"))
    body = resp.body.decode()
    assert resp.status_code == 200
    assert 'name="var_repo"' in body
    assert 'value="bdboard"' in body
    assert 'name="var_token"' in body
    assert "required" in body  # the required var carries the attribute


def test_api_formula_form_404_for_unknown() -> None:
    _stub_list_formulas([{"name": "demo", "source": "/x"}])
    resp = asyncio.run(app_module.api_formula_form(_get_request("/api/formulas/nope/form"), "nope"))
    assert resp.status_code == 404


# ----- POST /api/formulas/{name}/pour -----


def _call_pour(
    name: str,
    form_data: dict[str, str],
    csrf_header: str | None = None,
) -> tuple[int, str]:
    resp = asyncio.run(
        app_module.api_formula_pour(
            _post_request(f"/api/formulas/{name}/pour", form_data, csrf_header),
            name=name,
            csrf=form_data.get("csrf_token"),
            x_csrf_token=csrf_header,
        )
    )
    return resp.status_code, resp.body.decode()


def test_pour_requires_csrf() -> None:
    from fastapi import HTTPException

    _stub_list_formulas([{"name": "demo", "source": "/x"}])
    raised = False
    try:
        _call_pour("demo", {})
    except HTTPException as e:
        raised = True
        assert e.status_code == 403
    assert raised


def test_pour_blocks_missing_required_var() -> None:
    _stub_list_formulas([{"name": "demo", "source": "/x"}])
    _stub_read_vars([{"name": "token", "description": "Token", "default": None, "required": True}])
    pour_calls = _stub_pour({"new_epic_id": "x", "created": 1})
    _stub_rename()
    _stub_broadcast()

    status, body = _call_pour(
        "demo",
        {"csrf_token": app_module._CSRF_TOKEN},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 400
    assert "required" in body.lower()
    assert "token" in body
    assert pour_calls == []  # never poured


def test_pour_success_renames_and_broadcasts() -> None:
    _stub_list_formulas([{"name": "demo", "source": "/x"}])
    _stub_read_vars(
        [
            {
                "name": "repo",
                "description": "Repo",
                "default": "bdboard",
                "required": False,
            }
        ]
    )
    # A healthy pour: id_mapping has one entry per created node (here the
    # molecule wrapper + 3 step beads == 4). The wrapper is hidden, so the
    # board shows created - 1 == 3 (bdboard-98e count honesty).
    pour_calls = _stub_pour(
        {
            "new_epic_id": "bd-abc-mol-u72",
            "created": 4,
            "id_mapping": {
                "demo": "bd-abc-mol-u72",
                "demo.root": "bd-abc-mol-aa1",
                "demo.a": "bd-abc-mol-bb2",
                "demo.b": "bd-abc-mol-cc3",
            },
        }
    )
    rename_calls = _stub_rename()
    broadcasts = _stub_broadcast()

    status, body = _call_pour(
        "demo",
        {"csrf_token": app_module._CSRF_TOKEN, "var_repo": "myrepo"},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 200
    assert pour_calls == [("demo", {"repo": "myrepo"})]
    # rename uses the bd suffix after the last '-'
    assert rename_calls == [("bd-abc-mol-u72", "demo u72")]
    assert "beads_changed" in broadcasts
    assert "Poured" in body
    # Reports the VISIBLE count (4 created - 1 hidden wrapper), not the raw 4.
    assert "3" in body
    assert "4 beads" not in body


def test_pour_uses_default_when_field_blank() -> None:
    _stub_list_formulas([{"name": "demo", "source": "/x"}])
    _stub_read_vars(
        [
            {
                "name": "repo",
                "description": "Repo",
                "default": "bdboard",
                "required": False,
            }
        ]
    )
    pour_calls = _stub_pour({"new_epic_id": "bd-x-mol-z", "created": 1})
    _stub_rename()
    _stub_broadcast()

    status, _ = _call_pour(
        "demo",
        {"csrf_token": app_module._CSRF_TOKEN, "var_repo": ""},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 200
    assert pour_calls == [("demo", {"repo": "bdboard"})]


def test_pour_surfaces_bd_stderr_on_failure() -> None:
    _stub_list_formulas([{"name": "demo", "source": "/x"}])
    _stub_read_vars([])
    _stub_pour(RuntimeError("tasks can only block other tasks, not epics"))
    _stub_rename()
    _stub_broadcast()

    status, body = _call_pour(
        "demo",
        {"csrf_token": app_module._CSRF_TOKEN},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 500
    assert "Pour failed" in body
    assert "tasks can only block" in body


def test_pour_soft_warns_when_rename_fails() -> None:
    _stub_list_formulas([{"name": "demo", "source": "/x"}])
    _stub_read_vars([])
    _stub_pour({"new_epic_id": "bd-x-mol-z", "created": 2})
    broadcasts = _stub_broadcast()

    async def failing_rename(bead_id: str, title: str) -> None:
        raise RuntimeError("rename boom")

    app_module.bd.rename_bead = failing_rename  # type: ignore[assignment]

    status, body = _call_pour(
        "demo",
        {"csrf_token": app_module._CSRF_TOKEN},
        csrf_header=app_module._CSRF_TOKEN,
    )

    # Pour succeeded; rename failure is a soft warning, not a hard error.
    assert status == 200
    assert "Poured" in body
    assert "couldn" in body.lower()  # the soft rename warning
    assert "beads_changed" in broadcasts
