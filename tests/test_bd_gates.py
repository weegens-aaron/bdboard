"""Unit tests for BdClient gate / merge-slot coordination methods (bdboard-50v5).

Covers:
  - list_gates: shells `bd gate list --json`, returns the open-gate list,
    normalises bd's JSON `null` (zero open gates) to [], rejects other
    non-list payloads.
  - merge_slot_check: shells `bd merge-slot check --json`, returns the dict
    bd emits (including the "not found" available=false shape), rejects a
    non-dict payload.

_run_json is stubbed so no real bd subprocess runs.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bdboard.bd import BdClient


def _client_returning(payload: Any) -> tuple[BdClient, list[list[str]]]:
    client = BdClient()
    calls: list[list[str]] = []

    async def fake_run_json(args: list[str], timeout: float) -> Any:
        calls.append(args)
        return payload

    client._run_json = fake_run_json  # type: ignore[assignment]
    return client, calls


# ----- list_gates -----


def test_list_gates_shells_gate_list_and_returns_list() -> None:
    payload = [{"id": "gt-1", "issue_type": "gate", "await_type": "human"}]
    client, calls = _client_returning(payload)

    result = asyncio.run(client.list_gates())

    assert result == payload
    assert calls == [["gate", "list"]]


def test_list_gates_normalises_null_to_empty_list() -> None:
    """bd serialises an empty open-gate set as JSON null, not []."""
    client, _ = _client_returning(None)
    assert asyncio.run(client.list_gates()) == []


def test_list_gates_rejects_non_list_payload() -> None:
    client, _ = _client_returning({"not": "a list"})
    with pytest.raises(RuntimeError, match="non-list"):
        asyncio.run(client.list_gates())


# ----- merge_slot_check -----


def test_merge_slot_check_shells_and_returns_dict() -> None:
    payload = {"available": True, "id": "x-merge-slot"}
    client, calls = _client_returning(payload)

    result = asyncio.run(client.merge_slot_check())

    assert result == payload
    assert calls == [["merge-slot", "check"]]


def test_merge_slot_check_passes_through_not_found_shape() -> None:
    """A missing slot is a normal state (available=false, error=not found),
    not a subprocess failure."""
    payload = {"available": False, "error": "not found", "id": "x-merge-slot"}
    client, _ = _client_returning(payload)
    assert asyncio.run(client.merge_slot_check()) == payload


def test_merge_slot_check_rejects_non_dict_payload() -> None:
    client, _ = _client_returning([1, 2, 3])
    with pytest.raises(RuntimeError, match="non-object"):
        asyncio.run(client.merge_slot_check())
