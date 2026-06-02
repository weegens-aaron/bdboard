"""Unit tests for BdClient.list_closed_history() — the History data source.

The History page is the long-window retrospective surface; its closed fetch
must NOT be truncated to a static count. Previously it shelled
``bd list --status closed ... --limit 50`` (HISTORY_CLOSED_LIMIT), so anything
older than the 50 newest closures was unreachable no matter how the page's
range / custom-date / pagination controls were set (bdboard-a194). These tests
pin the contract that the fetch is now unbounded (``--limit 0``) and that every
closed bead the fetch returns is surfaced (no in-fetch truncation).

We stub _run_json so no real bd subprocess is spawned; the cache / semaphore
plumbing underneath is exercised for free via the wrapper.
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


def test_default_fetch_is_unbounded() -> None:
    # The default (no explicit limit) must shell --limit 0 so the History
    # page sees the FULL closed record, not a count-capped slice.
    client, calls = _client_returning([])

    asyncio.run(client.list_closed_history())

    assert calls == [
        ["list", "--status", "closed", "--sort", "closed", "--no-pager", "--limit", "0"]
    ]


def test_more_than_fifty_closed_beads_are_all_reachable() -> None:
    # Regression for bdboard-a194: with >50 closed beads, the fetch must
    # return ALL of them (the old HISTORY_CLOSED_LIMIT=50 silently dropped
    # everything past the 50 newest closures before any filtering ran).
    beads = [{"id": f"b{i}", "status": "closed"} for i in range(150)]
    client, _ = _client_returning(beads)

    result = asyncio.run(client.list_closed_history())

    assert len(result) == 150
    assert {b["id"] for b in result} == {f"b{i}" for i in range(150)}


def test_explicit_limit_is_passed_through() -> None:
    # The optional limit param still works for callers that genuinely want a
    # truncated fetch (e.g. a smoke test) — it is NOT the default behaviour.
    client, calls = _client_returning([])

    asyncio.run(client.list_closed_history(limit=10))

    assert calls == [
        ["list", "--status", "closed", "--sort", "closed", "--no-pager", "--limit", "10"]
    ]


def test_non_list_payload_raises() -> None:
    # A malformed (non-array) payload is a contract failure and must raise so
    # the Store's except-and-keep-previous-cache path can log it loudly.
    client, _ = _client_returning({"not": "a list"})

    try:
        asyncio.run(client.list_closed_history())
    except RuntimeError as exc:
        assert "closed-history" in str(exc)
    else:  # pragma: no cover - explicit failure if no raise
        raise AssertionError("expected RuntimeError on non-list payload")
