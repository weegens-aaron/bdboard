"""bd subprocess client.

bdboard talks to bd EXCLUSIVELY through the bd CLI (bd list / bd show /
bd history with --json). The legacy .beads/issues.jsonl path is a
throttled, deprecated export — per COMMUNITY_TOOLS.md, "Tools that read
the old .beads/issues.jsonl format directly are not compatible with
current versions." We follow that guidance.

Design notes:
- list_all is the BREAD-AND-BUTTER call: returns every non-infra issue
  (open + closed), no limit, --json. Powers Store.refresh, which is the
  upstream of every lane/count/activity render. ~700ms on a ~50-bead
  workspace, ~150ms warm.
- show_long / history are the BEAD-DETAIL calls, kept cached with the
  same TTL + in-flight dedup the bcc/bdboard v0 used.
- All three share _subprocess_gate, an asyncio.Semaphore(1). bd's
  embedded dolt server is single-writer and will lock up under
  concurrent CLI invocations (same gotcha beads-ui documents). One
  process-wide queue keeps us safe.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Timeouts and cache TTLs.
LIST_TIMEOUT_S = 15.0  # generous: large workspaces with many issues
HISTORY_TIMEOUT_S = 8.0
SHOW_TIMEOUT_S = 8.0
SUCCESS_TTL_S = 10.0
ERROR_TTL_S = 30.0


@dataclass(frozen=True)
class CacheEntry:
    fetched_at: float
    value: Any | None
    error: str | None

    def fresh(self, now: float) -> bool:
        ttl = ERROR_TTL_S if self.error else SUCCESS_TTL_S
        return (now - self.fetched_at) < ttl


class BdClient:
    """Thin async wrapper around the bd CLI.

    Constructor args:
        bd_bin: path to the bd binary (default: 'bd' from PATH)
        workspace: directory containing .beads/ (default: cwd)
    """

    def __init__(self, bd_bin: str = "bd", workspace: Path | None = None) -> None:
        self.bd_bin = bd_bin
        self.workspace = (workspace or Path.cwd()).resolve()
        self._history_cache: dict[str, CacheEntry] = {}
        self._show_cache: dict[str, CacheEntry] = {}
        # bd's embedded dolt server doesn't tolerate concurrent CLI invocations
        # well — you can get into a lock-wait situation where one slow call
        # makes a second call hang. Serialize ourselves to be a good neighbor.
        # (Same gotcha documented in mantoni/beads-ui server/bd.js
        # withBdRunQueue.)
        self._subprocess_gate = asyncio.Semaphore(1)
        # In-flight dedup: if a request for bead X arrives while another
        # request for bead X is already running its subprocess, the second
        # request awaits the first's Future instead of starting a new
        # subprocess. Kills the bcc-style "clicked too fast = 404" failure.
        self._inflight: dict[tuple[str, str], asyncio.Future] = {}

    # ----- workspace discovery -----

    @property
    def beads_dir(self) -> Path:
        """The .beads/ directory we observe. Watcher walks this recursively
        so dolt-internal writes (manifest, journal.idx, ...) trigger
        refresh, not the throttled issues.jsonl export."""
        return self.workspace / ".beads"

    def validate(self) -> None:
        """Raise a helpful error if the workspace isn't a bd workspace.

        We deliberately do NOT require .beads/issues.jsonl to exist —
        modern bd workspaces are dolt-backed and the JSONL is just a
        secondary export that may be absent or stale. We only need the
        .beads dir + a working bd binary; bd list --json is the source
        of truth.
        """
        if not self.beads_dir.is_dir():
            raise RuntimeError(
                f"no .beads/ directory in {self.workspace} — "
                "cd into a bd workspace first, or pass --dir"
            )
        if not shutil.which(self.bd_bin):
            raise RuntimeError(
                f"bd binary not found on PATH (looking for {self.bd_bin!r}) — "
                "install bd or pass --bd <path>"
            )

    # ----- bread-and-butter: full issue list (dolt-native, always fresh) -----

    async def list_all(self) -> list[dict[str, Any]]:
        """Fetch every non-infra issue (any status, unlimited) via
        `bd list --all --no-pager --limit 0 --json`.

        Returns a list of bead dicts. Raises on subprocess failure or
        malformed JSON — Store wraps the call in try/except and falls
        back to its previous cache so a transient bd hiccup doesn't
        flash an empty dashboard.

        Flag rationale:
        - --all: include closed issues (default hides them).
        - --no-pager: prevent bd from invoking less in non-TTY contexts.
        - --limit 0: unlimited (default 50 would silently drop beads on
          larger workspaces).
        - We deliberately omit --include-infra/--include-templates/
          --include-gates: bdboard renders user-visible work, not bd's
          coordination plumbing.
        """
        value = await self._run_json(
            ["list", "--all", "--no-pager", "--limit", "0"],
            timeout=LIST_TIMEOUT_S,
        )
        if not isinstance(value, list):
            raise RuntimeError(
                f"bd list returned non-list ({type(value).__name__}); "
                "expected JSON array"
            )
        return value

    # ----- bead detail: show + history (cached, in-flight deduped) -----

    async def _run_json(self, args: list[str], timeout: float) -> Any:
        """Run `bd <args> --json` and parse stdout. Raise on non-zero exit
        or timeout. Caller is responsible for converting raised errors into
        cached failure entries. Serialized via _subprocess_gate so two
        concurrent requests can't deadlock on bd's dolt lock."""
        async with self._subprocess_gate:
            proc = await asyncio.create_subprocess_exec(
                self.bd_bin,
                *args,
                "--json",
                cwd=str(self.workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise RuntimeError(
                    f"bd {' '.join(args)} timed out after {timeout}s"
                )
            if proc.returncode != 0:
                msg = stderr.decode("utf-8", errors="replace").strip().splitlines()
                first = msg[0] if msg else "(no stderr)"
                raise RuntimeError(f"bd {' '.join(args)} failed: {first}")
            try:
                return json.loads(stdout)
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"bd {' '.join(args)} returned invalid JSON: {e}"
                )

    async def _cached(
        self,
        cache: dict[str, CacheEntry],
        key: str,
        fetch_args: list[str],
        timeout: float,
    ) -> tuple[Any | None, str | None]:
        """TTL-cache + in-flight dedup around _run_json.

        Returns (value, error_msg). Caches failures (with shorter TTL) to
        avoid hammering a flaky bd. If a request for the same key is
        already in flight, awaits its result instead of starting a parallel
        subprocess — this is the fix for bcc's 'clicked too fast = error'.
        """
        now = time.monotonic()
        cached = cache.get(key)
        if cached and cached.fresh(now):
            return cached.value, cached.error

        # In-flight dedup: cache key includes the subcommand to avoid mixing
        # show vs history requests for the same bead id.
        flight_key = (fetch_args[0], key)
        existing = self._inflight.get(flight_key)
        if existing is not None:
            return await existing

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._inflight[flight_key] = future
        try:
            try:
                value = await self._run_json(fetch_args, timeout=timeout)
                cache[key] = CacheEntry(fetched_at=now, value=value, error=None)
                result = (value, None)
            except Exception as exc:  # noqa: BLE001 — we want to cache anything
                err = str(exc)
                cache[key] = CacheEntry(fetched_at=now, value=None, error=err)
                result = (None, err)
            future.set_result(result)
            return result
        finally:
            self._inflight.pop(flight_key, None)

    async def show_long(self, bead_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch the full bead detail via `bd show <id> --long --json`.
        Returns (bead_dict, error_msg). bd returns a JSON array; we unwrap."""
        value, err = await self._cached(
            self._show_cache,
            key=bead_id,
            fetch_args=["show", bead_id, "--long"],
            timeout=SHOW_TIMEOUT_S,
        )
        if value is None:
            return None, err
        if isinstance(value, list) and value:
            return value[0], None
        if isinstance(value, dict):
            return value, None
        return None, "bd show returned unexpected shape"

    async def history(
        self, bead_id: str
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch audit history via `bd history <id> --json`.
        Returns (entries_list, error_msg). Failure is normal and surfaced."""
        return await self._cached(
            self._history_cache,
            key=bead_id,
            fetch_args=["history", bead_id],
            timeout=HISTORY_TIMEOUT_S,
        )

    def invalidate_caches(self) -> None:
        """Drop show/history caches. Called by Store after a watcher fire
        so the next bead-detail request picks up post-mutation state
        instead of serving up-to-10s-old cached values."""
        self._show_cache.clear()
        self._history_cache.clear()
