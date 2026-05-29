"""Route tests for POST /api/memory and DELETE /api/memory/{key} (memory mutations).

Tests cover:
  - CSRF validation (rejects missing/invalid tokens)
  - remember/forget write paths via bd CLI wrappers
  - error handling and degraded responses
  - optimistic refresh (returns updated list on success)
  - empty key/body validation
"""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request

from bdboard import app as app_module


def _post_request(
    form_data: dict[str, str],
    csrf_header: str | None = None,
) -> Request:
    """Build a minimal POST Request for /api/memory with form data."""
    # Encode form data as URL-encoded body.
    body = "&".join(f"{k}={v}" for k, v in form_data.items()).encode()
    headers = [(b"content-type", b"application/x-www-form-urlencoded")]
    if csrf_header:
        headers.append((b"x-csrf-token", csrf_header.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/memory",
        "query_string": b"",
        "headers": headers,
    }

    # FastAPI needs an async receive function.
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _delete_request(key: str, csrf_header: str | None = None) -> Request:
    """Build a minimal DELETE Request for /api/memory/{key}."""
    headers = []
    if csrf_header:
        headers.append((b"x-csrf-token", csrf_header.encode()))
    scope = {
        "type": "http",
        "method": "DELETE",
        "path": f"/api/memory/{key}",
        "query_string": b"",
        "headers": headers,
    }
    return Request(scope)


def _stub_remember(error: Exception | None = None) -> list[tuple[str, str]]:
    """Stub bd.remember to record calls and optionally raise an error."""
    calls: list[tuple[str, str]] = []

    async def fake_remember(key: str, body: str) -> None:
        calls.append((key, body))
        if error:
            raise error

    app_module.bd.remember = fake_remember  # type: ignore[assignment]
    return calls


def _stub_forget(error: Exception | None = None) -> list[str]:
    """Stub bd.forget to record calls and optionally raise an error."""
    calls: list[str] = []

    async def fake_forget(key: str) -> None:
        calls.append(key)
        if error:
            raise error

    app_module.bd.forget = fake_forget  # type: ignore[assignment]
    return calls


def _stub_memories(result: Any) -> None:
    """Stub bd.memories to return a fixed result for re-rendering the list."""

    async def fake_memories(query: str | None = None) -> Any:
        if isinstance(result, Exception):
            raise result
        return result

    app_module.bd.memories = fake_memories  # type: ignore[assignment]


def _stub_bus_broadcast() -> list[str]:
    """Stub EventBus.broadcast to capture SSE broadcasts."""
    calls: list[str] = []

    async def fake_broadcast(event: str) -> None:
        calls.append(event)

    app_module.bus.broadcast = fake_broadcast  # type: ignore[assignment]
    return calls


# ----- POST /api/memory tests -----


def test_create_memory_requires_csrf_token() -> None:
    _stub_remember()
    _stub_memories([])

    # No CSRF token → 403.
    from fastapi import HTTPException

    try:
        asyncio.run(
            app_module.api_memory_create(
                _post_request({"key": "test", "body": "content"}),
                key="test",
                body="content",
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


def test_create_memory_accepts_valid_csrf_header() -> None:
    remember_calls = _stub_remember()
    _stub_memories([{"key": "newkey", "body": "newbody"}])
    _stub_bus_broadcast()

    status, body = _call_create(
        {"key": "newkey", "body": "newbody"},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 200
    assert remember_calls == [("newkey", "newbody")]
    assert "newkey" in body


def test_create_memory_accepts_valid_csrf_form_field() -> None:
    remember_calls = _stub_remember()
    _stub_memories([{"key": "formkey", "body": "formbody"}])
    _stub_bus_broadcast()

    status, body = _call_create(
        {"key": "formkey", "body": "formbody", "csrf_token": app_module._CSRF_TOKEN},
        csrf_form=app_module._CSRF_TOKEN,
    )

    assert status == 200
    assert remember_calls == [("formkey", "formbody")]


def test_create_memory_rejects_empty_key() -> None:
    _stub_remember()
    _stub_memories([])
    _stub_bus_broadcast()

    status, body = _call_create(
        {"key": "", "body": "content"},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 400
    assert "Key cannot be empty" in body


def test_create_memory_rejects_empty_body() -> None:
    _stub_remember()
    _stub_memories([])
    _stub_bus_broadcast()

    status, body = _call_create(
        {"key": "test", "body": ""},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 400
    assert "Body cannot be empty" in body


def test_create_memory_broadcasts_sse_on_success() -> None:
    _stub_remember()
    _stub_memories([])
    broadcasts = _stub_bus_broadcast()

    _call_create(
        {"key": "test", "body": "content"},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert "beads_changed" in broadcasts


def test_create_memory_shows_error_on_bd_failure() -> None:
    _stub_remember(RuntimeError("bd crashed"))
    _stub_memories([])
    _stub_bus_broadcast()

    status, body = _call_create(
        {"key": "test", "body": "content"},
        csrf_header=app_module._CSRF_TOKEN,
    )

    assert status == 500
    assert "Could not save" in body
    assert "bd crashed" in body


# ----- DELETE /api/memory/{key} tests -----


def test_delete_memory_requires_csrf_token() -> None:
    _stub_forget()
    _stub_memories([])

    from fastapi import HTTPException

    try:
        asyncio.run(
            app_module.api_memory_delete(
                _delete_request("testkey"),
                key="testkey",
                x_csrf_token=None,
            )
        )
        raised = False
    except HTTPException as e:
        raised = True
        assert e.status_code == 403

    assert raised, "Expected HTTPException for missing CSRF"


def test_delete_memory_accepts_valid_csrf_and_forgets() -> None:
    forget_calls = _stub_forget()
    _stub_memories([])
    _stub_bus_broadcast()

    status, body = _call_delete("victim-key", csrf_header=app_module._CSRF_TOKEN)

    assert status == 200
    assert forget_calls == ["victim-key"]


def test_delete_memory_broadcasts_sse_on_success() -> None:
    _stub_forget()
    _stub_memories([])
    broadcasts = _stub_bus_broadcast()

    _call_delete("testkey", csrf_header=app_module._CSRF_TOKEN)

    assert "beads_changed" in broadcasts


def test_delete_memory_shows_error_on_bd_failure() -> None:
    _stub_forget(RuntimeError("key not found"))
    _stub_memories([])
    _stub_bus_broadcast()

    status, body = _call_delete("nonexistent", csrf_header=app_module._CSRF_TOKEN)

    assert status == 500
    assert "Could not delete" in body
    assert "key not found" in body


# ----- helpers -----


def _call_create(
    form_data: dict[str, str],
    csrf_header: str | None = None,
    csrf_form: str | None = None,
) -> tuple[int, str]:
    """Invoke api_memory_create and return (status_code, decoded body)."""
    resp = asyncio.run(
        app_module.api_memory_create(
            _post_request(form_data, csrf_header),
            key=form_data.get("key", ""),
            body=form_data.get("body", ""),
            csrf=csrf_form or form_data.get("csrf_token"),
            x_csrf_token=csrf_header,
        )
    )
    return resp.status_code, resp.body.decode()


def _call_delete(key: str, csrf_header: str | None = None) -> tuple[int, str]:
    """Invoke api_memory_delete and return (status_code, decoded body)."""
    resp = asyncio.run(
        app_module.api_memory_delete(
            _delete_request(key, csrf_header),
            key=key,
            x_csrf_token=csrf_header,
        )
    )
    return resp.status_code, resp.body.decode()
