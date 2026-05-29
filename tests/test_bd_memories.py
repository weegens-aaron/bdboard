"""Unit tests for BdClient.memories() JSON-contract handling.

These exercise the four contract shapes called out in
docs/design/bdboard-5p1/memory-view-design.md §2.1:
  - empty / sentinel-only payload  -> zero results
  - no-match search (sentinel only) -> zero results
  - search-match (one entry + sentinel) -> that entry, sentinel stripped
  - full list (many entries + sentinel) -> all, sorted by key

We stub _run_json so no real bd subprocess is spawned; the cache /
semaphore plumbing underneath is exercised for free via _cached.
"""

from __future__ import annotations

import asyncio
from typing import Any

from bdboard.bd import BdClient


def _client_returning(payload: Any) -> tuple[BdClient, list[list[str]]]:
    """Build a BdClient whose _run_json returns ``payload`` and records the
    args it was called with (so we can assert the shelled command)."""
    client = BdClient()
    calls: list[list[str]] = []

    async def fake_run_json(args: list[str], timeout: float) -> Any:
        calls.append(args)
        return payload

    client._run_json = fake_run_json  # type: ignore[assignment]
    return client, calls


def test_empty_sentinel_only_yields_no_results() -> None:
    client, calls = _client_returning({"schema_version": 1})

    result = asyncio.run(client.memories())

    assert result == []
    # No search term -> bare `bd memories`.
    assert calls == [["memories"]]


def test_no_match_search_yields_no_results() -> None:
    client, calls = _client_returning({"schema_version": 1})

    result = asyncio.run(client.memories("nonexistent-term"))

    assert result == []
    # Search term is appended to the args.
    assert calls == [["memories", "nonexistent-term"]]


def test_search_match_strips_sentinel_and_returns_entry() -> None:
    client, _ = _client_returning(
        {"bd-edit-stalls": "Never run bd edit.", "schema_version": 1}
    )

    result = asyncio.run(client.memories("edit"))

    assert result == [{"key": "bd-edit-stalls", "body": "Never run bd edit."}]
    assert all(entry["key"] != "schema_version" for entry in result)


def test_full_list_is_sorted_by_key_with_sentinel_stripped() -> None:
    client, _ = _client_returning(
        {
            "zeta": "last alphabetically",
            "alpha": "first alphabetically",
            "schema_version": 1,
            "mid": "middle",
        }
    )

    result = asyncio.run(client.memories())

    assert result == [
        {"key": "alpha", "body": "first alphabetically"},
        {"key": "mid", "body": "middle"},
        {"key": "zeta", "body": "last alphabetically"},
    ]


def test_blank_query_is_treated_as_list_all() -> None:
    client, calls = _client_returning({"schema_version": 1})

    asyncio.run(client.memories("   "))

    # Whitespace-only query collapses to the bare list command.
    assert calls == [["memories"]]


def test_non_object_payload_raises() -> None:
    client, _ = _client_returning(["not", "an", "object"])

    try:
        asyncio.run(client.memories())
    except RuntimeError as exc:
        assert "non-object" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected RuntimeError for non-object payload")
