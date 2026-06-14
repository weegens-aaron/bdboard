"""Tests for the Dolt local-vs-remote sync badge (bdboard-lwiv).

bdboard reads the LOCAL dolt store and never consults the remote, so un-pushed
local writes (ahead of origin) and a teammate's pushed-but-un-pulled writes
(behind origin) are invisible — the board reads "live" while silently stale-vs-
origin. The masthead "live · push" pill only reflected the SSE socket and was
confusable with `bd dolt push`.

This covers three things:

  AC1  BdClient.dolt_sync_status() classifies ahead / behind / diverged /
       synced / no-remote / unknown from the underlying bd+dolt shell-outs.
  AC2  the path NEVER 500s — every shell failure degrades to a quiet state
       (no remote, or unknown), never an exception.
  AC3  the live pill is relabeled so it no longer reads as a Dolt-sync cue,
       and the badge partial renders the drift states.

The state-machine tests stub the low-level helpers so no real bd/dolt
subprocess is spawned. The render tests drive the partial through the app's
Jinja env (mirroring test_stale_banner_ui.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from bdboard import app as app_module
from bdboard.bd import BdClient

_PKG_DIR = Path(app_module.__file__).parent
_BASE_HTML = (_PKG_DIR / "templates" / "base.html").read_text(encoding="utf-8")


def _client(
    remotes: list[str] | None,
    status_ok: bool = True,
    ahead_behind: tuple[str, int, int] | None = None,
) -> BdClient:
    """A BdClient with the three sync helpers stubbed."""
    client = BdClient()

    async def fake_remotes() -> list[str] | None:
        return remotes

    async def fake_status_ok() -> bool:
        return status_ok

    async def fake_ab(remote: str) -> tuple[str, int, int] | None:
        return ahead_behind

    client._bd_dolt_remotes = fake_remotes  # type: ignore[assignment]
    client._bd_dolt_status_ok = fake_status_ok  # type: ignore[assignment]
    client._dolt_ahead_behind = fake_ab  # type: ignore[assignment]
    return client


# ----- AC1 + AC2: state machine -----


def test_no_remote_state() -> None:
    client = _client(remotes=[])
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "no-remote"
    assert result["remote"] is None


def test_remote_list_failure_degrades_to_unknown() -> None:
    # Couldn't even list remotes (bd hiccup) -> quiet 'unknown', never raise.
    client = _client(remotes=None)
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "unknown"


def test_ahead_state_counts_unpushed() -> None:
    client = _client(remotes=["origin"], ahead_behind=("main", 3, 0))
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "ahead"
    assert result["ahead"] == 3
    assert result["remote"] == "origin"


def test_behind_state_counts_unpulled() -> None:
    client = _client(remotes=["origin"], ahead_behind=("main", 0, 2))
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "behind"
    assert result["behind"] == 2


def test_diverged_state_both_directions() -> None:
    client = _client(remotes=["origin"], ahead_behind=("main", 1, 4))
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "diverged"
    assert result["ahead"] == 1
    assert result["behind"] == 4


def test_synced_state_when_level() -> None:
    client = _client(remotes=["origin"], ahead_behind=("main", 0, 0))
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "synced"


def test_status_engine_failure_degrades_to_unknown() -> None:
    # Remote configured but the engine probe fails -> 'unknown', not a
    # misleading 'synced' (and definitely not a 500).
    client = _client(remotes=["origin"], status_ok=False)
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "unknown"


def test_ahead_behind_unavailable_degrades_to_unknown() -> None:
    # No `dolt` binary / never-fetched ref -> _dolt_ahead_behind returns None
    # -> 'unknown' (remote present but drift uncomputable), no exception.
    client = _client(remotes=["origin"], ahead_behind=None)
    result = asyncio.run(client.dolt_sync_status())
    assert result["state"] == "unknown"
    assert result["remote"] == "origin"


def test_capture_json_missing_binary_returns_none() -> None:
    # The raw helper must swallow a missing binary into None (the contract the
    # whole soft-fail chain rests on), never raise OSError.
    client = BdClient()
    result = asyncio.run(client._run_capture_json(["definitely-not-a-real-binary-xyz"]))
    assert result is None


# ----- AC3: render the drift states -----


def _render_badge(sync: dict[str, Any]) -> str:
    template = app_module.TEMPLATES.env.get_template("partials/dolt_sync_badge.html")
    return template.render(sync=sync)


def _sync(state: str, ahead: int = 0, behind: int = 0) -> dict[str, Any]:
    return {
        "state": state,
        "ahead": ahead,
        "behind": behind,
        "remote": "origin",
        "branch": "main",
    }


def test_badge_renders_ahead() -> None:
    html = _render_badge(_sync("ahead", ahead=3))
    assert "3 unpushed" in html
    assert "sync-badge-ahead" in html
    assert 'role="status"' in html


def test_badge_renders_behind() -> None:
    html = _render_badge(_sync("behind", behind=2))
    assert "2 behind" in html
    assert "sync-badge-behind" in html


def test_badge_renders_diverged() -> None:
    html = _render_badge(_sync("diverged", ahead=1, behind=4))
    assert "diverged" in html
    assert "sync-badge-diverged" in html


def test_badge_renders_no_remote() -> None:
    html = _render_badge(_sync("no-remote"))
    assert "no remote" in html
    assert "sync-badge-noremote" in html


def test_badge_empty_when_synced() -> None:
    # Synced / unknown render nothing so the footer region collapses.
    assert _render_badge(_sync("synced")).strip() == ""
    assert _render_badge(_sync("unknown")).strip() == ""


# ----- AC3: pill relabel + badge poll wiring -----


def test_live_pill_relabeled_away_from_dolt() -> None:
    # The pill no longer reads as a `bd dolt push` indicator.
    assert "live · push" not in _BASE_HTML
    assert "live · updates" in _BASE_HTML


def test_base_html_polls_sync_endpoint() -> None:
    assert "/api/dolt-sync" in _BASE_HTML
    # Polled on an interval (a stale board gets no SSE events) AND on SSE
    # refresh so it clears promptly after a push/pull.
    assert "every 30s" in _BASE_HTML
    assert "refresh from:body" in _BASE_HTML
