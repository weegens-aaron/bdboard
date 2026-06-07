"""Unit tests for BdClient swarm / mol-progress methods (bdboard-je14, FB-10).

Covers:
  - mol_progress: shells `bd mol progress <id> --json`, returns the rollup
    dict, rejects a non-dict payload.
  - swarm_status: shells `bd swarm status <id> --json`, returns the dict,
    rejects a non-dict payload.
  - swarm_validate: shells `bd swarm validate <id> --json`, returns the dict,
    rejects a non-dict payload.

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


# ----- mol_progress -----


def test_mol_progress_shells_and_returns_dict() -> None:
    payload = {"total": 14, "completed": 10, "percent": 71.4}
    client, calls = _client_returning(payload)

    result = asyncio.run(client.mol_progress("bdboard-atvy"))

    assert result == payload
    assert calls == [["mol", "progress", "bdboard-atvy"]]


def test_mol_progress_rejects_non_dict() -> None:
    client, _ = _client_returning([1, 2, 3])
    with pytest.raises(RuntimeError, match="non-object"):
        asyncio.run(client.mol_progress("bdboard-atvy"))


# ----- swarm_status -----


def test_swarm_status_shells_and_returns_dict() -> None:
    payload = {"progress_percent": 71.4, "active_count": 1, "completed": []}
    client, calls = _client_returning(payload)

    result = asyncio.run(client.swarm_status("bdboard-atvy"))

    assert result == payload
    assert calls == [["swarm", "status", "bdboard-atvy"]]


def test_swarm_status_rejects_non_dict() -> None:
    client, _ = _client_returning(None)
    with pytest.raises(RuntimeError, match="non-object"):
        asyncio.run(client.swarm_status("bdboard-atvy"))


# ----- swarm_validate -----


def test_swarm_validate_shells_and_returns_dict() -> None:
    payload = {"swarmable": True, "max_parallelism": 3, "ready_fronts": []}
    client, calls = _client_returning(payload)

    result = asyncio.run(client.swarm_validate("bdboard-atvy"))

    assert result == payload
    assert calls == [["swarm", "validate", "bdboard-atvy"]]


def test_swarm_validate_rejects_non_dict() -> None:
    client, _ = _client_returning("nope")
    with pytest.raises(RuntimeError, match="non-object"):
        asyncio.run(client.swarm_validate("bdboard-atvy"))
