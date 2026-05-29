"""bd subprocess client.

bdboard talks to bd through the bd CLI (`bd list`, `bd show`, `bd history`
with `--json`). The JSONL export is not used as a runtime source of truth.

Design notes:
- list_all is the primary call: returns every non-infra issue (open + closed),
  no limit, JSON output. Powers Store.refresh and therefore all lane/count/
  activity renders.
- show_long / history power bead-detail views and are cached with TTL +
  in-flight dedup.
- All three share _subprocess_gate, an asyncio.Semaphore(1). bd's embedded
  dolt server is single-writer and can lock under concurrent CLI invocations,
  so process-wide serialization keeps requests reliable.
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
MEMORIES_TIMEOUT_S = 8.0
REMEMBER_TIMEOUT_S = 10.0  # writes may be slower (dolt commit)
FORGET_TIMEOUT_S = 10.0
SUCCESS_TTL_S = 10.0
ERROR_TTL_S = 30.0

# bd memories --json carries a metadata sentinel alongside the key->body
# entries; it is not a memory and must be stripped before rendering. An
# empty/no-match result still carries this key (and nothing else), so
# 'only schema_version present' means zero results.
SCHEMA_VERSION_KEY = "schema_version"


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
        self._memories_cache: dict[str, CacheEntry] = {}
        # bd's embedded dolt server can lock-wait under concurrent CLI calls;
        # serialize requests so one slow command cannot deadlock peers.
        self._subprocess_gate = asyncio.Semaphore(1)
        # In-flight dedup: if a request for bead X arrives while another
        # request for bead X is already running its subprocess, the second
        # request awaits the first's Future instead of starting a new
        # subprocess. Prevents duplicate requests from racing each other.
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
                "workspace is missing a .beads/ directory — "
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

    # ----- memories: browse + search (cached, in-flight deduped) -----

    async def memories(self, query: str | None = None) -> list[dict[str, str]]:
        """Fetch bd memories via `bd memories [term] --json`.

        Returns a list of ``{"key", "body"}`` dicts sorted alphabetically
        by key (deterministic, matching the CLI's human ordering). With a
        ``query`` this shells `bd memories <term> --json`, which performs
        bd's own server-side case-insensitive substring match across key
        and body — we reuse that logic rather than re-implementing it in
        the browser or here.

        The raw JSON is a flat key->body object plus a ``schema_version``
        sentinel. We strip the sentinel; a payload of *only* the sentinel
        (the empty / no-match shape) yields an empty list. Inherits the
        module's semaphore + timeout + TTL-cache + in-flight dedup via
        ``_cached``. Raises (like :meth:`list_all`) on subprocess failure
        or malformed JSON so callers can surface a friendly error.
        """
        term = (query or "").strip()
        args = ["memories"]
        if term:
            args.append(term)
        value, err = await self._cached(
            self._memories_cache,
            key=term,
            fetch_args=args,
            timeout=MEMORIES_TIMEOUT_S,
        )
        if err is not None:
            raise RuntimeError(err)
        if not isinstance(value, dict):
            raise RuntimeError(
                f"bd memories returned non-object ({type(value).__name__}); "
                "expected JSON object"
            )
        return [
            {"key": key, "body": body}
            for key, body in sorted(value.items())
            if key != SCHEMA_VERSION_KEY
        ]

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
                    "Request timed out while loading bead data. Please try again."
                )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Could not load bead data right now ({args[0]}). Please try again."
                )
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                raise RuntimeError(
                    "Received an unexpected response while loading bead data."
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
        avoid hammering a flaky bd. If a request for the same key is already
        in flight, await its result instead of spawning a duplicate subprocess.
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
        """Drop show/history/memories caches. Called by Store after a watcher
        fire so the next detail or memory request picks up post-mutation
        state instead of serving up-to-10s-old cached values."""
        self._show_cache.clear()
        self._history_cache.clear()
        self._memories_cache.clear()

    # ----- memory mutations: remember / forget -----

    async def remember(self, key: str, body: str) -> None:
        """Upsert a memory via `bd remember "<body>" --key <key>`.

        Creates a new memory if the key doesn't exist, or updates an
        existing one. This is bdboard's first write path to bd — it
        mutates the workspace's dolt store and triggers a watcher fire
        that will SSE-broadcast to all connected clients.

        Raises RuntimeError on subprocess failure.
        """
        # bd remember "<body>" --key <key>
        # Body is passed as a positional argument, key via --key flag.
        await self._run_mutate(
            ["remember", body, "--key", key],
            timeout=REMEMBER_TIMEOUT_S,
        )
        # Invalidate memories cache immediately so the next read picks up
        # the fresh state (watcher will also fire, but cache may be hit
        # before watcher completes).
        self._memories_cache.clear()

    async def forget(self, key: str) -> None:
        """Delete a memory via `bd forget <key>`.

        Raises RuntimeError on subprocess failure (including key-not-found).
        """
        await self._run_mutate(
            ["forget", key],
            timeout=FORGET_TIMEOUT_S,
        )
        self._memories_cache.clear()

    async def _run_mutate(self, args: list[str], timeout: float) -> None:
        """Run a bd mutation command (no --json, no parse, check exit only).

        Serialized via _subprocess_gate like read commands; mutations are
        single-writer so we must avoid concurrent writes from multiple
        browser tabs / users on the same workspace.
        """
        async with self._subprocess_gate:
            proc = await asyncio.create_subprocess_exec(
                self.bd_bin,
                *args,
                cwd=str(self.workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise RuntimeError(
                    "Request timed out while saving memory. Please try again."
                )
            if proc.returncode != 0:
                # bd forget on a non-existent key exits non-zero with a
                # descriptive stderr; surface it.
                err_text = stderr.decode(errors="replace").strip()
                raise RuntimeError(
                    err_text
                    or f"bd {args[0]} failed (exit {proc.returncode}). Please try again."
                )
