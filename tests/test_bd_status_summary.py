"""Unit tests for BdClient.status_summary() — the optional headline KPI.

status_summary() wraps `bd status --json` and returns the ``summary``
sub-object (design §6, bead F). It is *optional sugar*: any bd hiccup or
malformed payload must degrade to None so the History page simply omits the
headline rather than erroring. These tests pin that contract.

We stub _run_json so no real bd subprocess is spawned; the cache /
semaphore plumbing underneath is exercised for free via _cached.
"""

from __future__ import annotations

import asyncio
from typing import Any

from bdboard.bd import BdClient


def _client_returning(payload: Any) -> tuple[BdClient, list[list[str]]]:
    """Build a BdClient whose _run_json returns ``payload`` and records the
    args it was shelled with (so we can assert the command)."""
    client = BdClient()
    calls: list[list[str]] = []

    async def fake_run_json(args: list[str], timeout: float) -> Any:
        calls.append(args)
        return payload

    client._run_json = fake_run_json  # type: ignore[assignment]
    return client, calls


def test_returns_summary_subobject() -> None:
    summary = {
        "total_issues": 42,
        "closed_issues": 30,
        "in_progress_issues": 5,
        "average_lead_time_hours": 12.5,
    }
    client, calls = _client_returning({"schema_version": 1, "summary": summary})

    result = asyncio.run(client.status_summary())

    assert result == summary
    # Shells the bare `bd status` (the JSON flag is added by _run_json).
    assert calls == [["status"]]


def test_missing_summary_key_yields_none() -> None:
    client, _ = _client_returning({"schema_version": 1})

    result = asyncio.run(client.status_summary())

    assert result is None


def test_non_dict_summary_yields_none() -> None:
    client, _ = _client_returning({"summary": ["not", "a", "dict"]})

    result = asyncio.run(client.status_summary())

    assert result is None


def test_non_object_payload_yields_none() -> None:
    # status_summary swallows the contract failure to None (optional sugar)
    # rather than propagating the RuntimeError _run_json-derived path raises.
    client = BdClient()

    async def boom(args: list[str], timeout: float) -> Any:
        raise RuntimeError("bd status blew up")

    client._run_json = boom  # type: ignore[assignment]

    result = asyncio.run(client.status_summary())

    assert result is None
