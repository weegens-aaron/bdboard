"""bd subprocess client.

bdboard talks to bd through the bd CLI (`bd list`, `bd show`, `bd history`
with `--json`). The JSONL export is not used as a runtime source of truth.

Design notes:
- The board uses two fetches that Store caches separately so the header
  CLOSED KPI and the Closed lane reflect the SAME set (bdboard-p8v):
    - list_active: active issues (open, in_progress, blocked, deferred),
      no limit. Fast path for first paint.
    - list_closed: closed issues bounded by the board's date window
      (BOARD_CLOSED_WINDOW_DAYS) via --closed-after, NOT a static count
      cap. Powers the Closed lane and the closed header count.
- list_closed_history: the closed record for the long-window History page,
  sorted by closed_at desc and never *count*-capped (bd list --limit 0,
  bdboard-a194) — a static count cap would make anything older than the cap
  unreachable. It IS bounded by the page's active filter *window* though:
  closed_after pushes the range / custom-date lower bound down to the query
  via --closed-after (bdboard-gp06), so a narrow range fetches only its
  beads instead of slurping the whole closed table. The 'all' range passes
  closed_after=None and stays a genuine full-table read by design.
- show_long / history power bead-detail views and are cached with TTL +
  in-flight dedup.
- All share _subprocess_gate, an asyncio.Semaphore(1). bd's embedded
  dolt server is single-writer and can lock under concurrent CLI invocations,
  so process-wide serialization keeps requests reliable.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Timeouts and cache TTLs.
LIST_TIMEOUT_S = 15.0  # generous: large workspaces with many issues
HISTORY_TIMEOUT_S = 8.0
STATUS_TIMEOUT_S = 8.0
SHOW_TIMEOUT_S = 8.0
MEMORIES_TIMEOUT_S = 8.0
REMEMBER_TIMEOUT_S = 10.0  # writes may be slower (dolt commit)
FORGET_TIMEOUT_S = 10.0
UPDATE_TIMEOUT_S = 10.0  # field edits: dolt commit, possibly long markdown
FORMULA_LIST_TIMEOUT_S = 8.0
GATE_LIST_TIMEOUT_S = 8.0
MERGE_SLOT_TIMEOUT_S = 8.0
MOL_PROGRESS_TIMEOUT_S = 8.0  # cheap children-rollup count (~0.7s observed)
SWARM_TIMEOUT_S = 15.0  # swarm status/validate walk the DAG; on-demand only
POUR_TIMEOUT_S = 30.0  # pour cooks inline + materializes a whole formula tree
DOLT_SYNC_TIMEOUT_S = 8.0  # masthead sync badge: cheap local-vs-remote ref read
SUCCESS_TTL_S = 10.0
ERROR_TTL_S = 30.0

# A Dolt branch/remote name is only safe to interpolate into a dolt_log() ref
# if it matches this charset. Names come from bd/dolt config (not user input),
# but we validate before f-stringing them into SQL anyway — defense in depth
# against a hostile remote name becoming SQL injection.
_DOLT_REF_SAFE = re.compile(r"^[A-Za-z0-9._/-]+$")

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


def _safe_kill(proc: asyncio.subprocess.Process) -> None:
    """Kill ``proc``, tolerating an already-exited process.

    The cleanup branches in our subprocess helpers call ``proc.kill()`` when a
    request times out or is cancelled. But the subprocess may have already
    exited by then (it was, after all, in the middle of finishing). Under
    uvloop, ``UVProcessTransport._check_proc`` raises ``ProcessLookupError``
    when killing a dead pid. That stray error is poisonous in two ways:

    1. In the ``except BaseException`` branch it MASKS the original
       ``CancelledError``, breaking cooperative cancellation, and it skips the
       follow-up draining ``communicate()`` (the fd leak the docstrings warn
       about).
    2. Being a plain ``Exception`` (not ``BaseException``), it propagates up
       through ``list_active`` into ``Store.refresh``'s ``except Exception``,
       which logs 'bd list failed; keeping previous snapshot' and returns
       False — so no SSE broadcast fires and the board stops syncing.

    A process that is already dead is exactly the outcome ``kill()`` wants, so
    swallowing ``ProcessLookupError`` is correct: it is a successful no-op.
    """
    try:
        proc.kill()
    except ProcessLookupError:
        # Already exited — nothing to kill. Treat as success so the caller
        # can proceed to drain pipes / re-raise the real (cancellation) error.
        pass


class BdClient:
    """Thin async wrapper around the bd CLI.

    Constructor args:
        bd_bin: path to the bd binary (default: 'bd' from PATH)
        workspace: directory containing .beads/ (default: cwd)
        dolt_bin: path to the standalone dolt binary (default: 'dolt' from
            PATH). Used ONLY by :meth:`dolt_sync_status` to read local-vs-remote
            commit counts — bd's own `dolt status` reports engine state, not
            ahead/behind — and degrades gracefully (state='unknown') when the
            binary is absent.
    """

    def __init__(
        self,
        bd_bin: str = "bd",
        workspace: Path | None = None,
        dolt_bin: str = "dolt",
    ) -> None:
        self.bd_bin = bd_bin
        self.dolt_bin = dolt_bin
        self.workspace = (workspace or Path.cwd()).resolve()
        self._history_cache: dict[str, CacheEntry] = {}
        self._show_cache: dict[str, CacheEntry] = {}
        self._memories_cache: dict[str, CacheEntry] = {}
        self._status_cache: dict[str, CacheEntry] = {}
        # Resolved lazily once: the embedded dolt db directory whose ahead/
        # behind the sync badge reports. None until first resolved; cached for
        # the process lifetime (the active db doesn't change under a running
        # board).
        self._dolt_db_dir: Path | None = None
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
        """The .beads/ directory we observe. We do NOT watch this whole tree
        recursively (see watch_targets for why) — only the dolt noms/
        directories whose manifest/journal.idx mutate on every bd write."""
        return self.workspace / ".beads"

    def watch_targets(self) -> list[Path]:
        """Directories the watcher should observe NON-recursively.

        Why not recursive .beads/: dolt's content-addressed object store
        (.beads/embeddeddolt/<db>/.dolt/noms/) contains a large, constantly
        churning set of files. On macOS the watchfiles kqueue backend opens
        one fd PER watched directory/file when recursive=True, so watching
        the whole .beads/ tree (hundreds of dirs) exhausts the process's
        RLIMIT_NOFILE soft limit (often 256). Once fds run out, EVERYTHING
        needing a new fd fails — most visibly asyncio.create_subprocess_exec
        can no longer open pipes, so `bd list --json` (snapshot refresh) and
        `bd show` (bead detail) both crash with OSError [Errno 24].

        Every meaningful bd write touches manifest + journal.idx inside each
        database's noms/ dir, so watching those directories NON-recursively
        (a fixed, tiny handful of fds) gives the same sub-second latency
        without the fd blowup. We also include .beads/ itself so a workspace
        that adds a new dolt db (or recreates noms/) is picked up on the
        next refresh.
        """
        targets: list[Path] = []
        embedded = self.beads_dir / "embeddeddolt"
        if embedded.is_dir():
            for db_dir in sorted(embedded.iterdir()):
                noms = db_dir / ".dolt" / "noms"
                if noms.is_dir():
                    targets.append(noms)
        # Always include .beads/ itself (non-recursive) as a cheap catch-all
        # for new dbs / the legacy issues.jsonl export landing.
        if self.beads_dir.is_dir():
            targets.append(self.beads_dir)
        return targets

    def watch_signature(self) -> frozenset[tuple[str, int, int]]:
        """Identity fingerprint of the current watch targets (bdboard-xbc7).

        Returns a frozenset of ``(path, st_dev, st_ino)`` for every target
        from :meth:`watch_targets`. The watcher enumerates targets ONCE
        before entering ``awatch``'s ``async for`` loop, so two post-startup
        events go unnoticed:

          1. A NEW dolt db (or a recreated ``.dolt/noms/``) appears — its
             directory was never handed to ``awatch``, so writes there are
             invisible.
          2. dolt atomically REPLACES a ``noms/`` dir (rename-over). On
             macOS the kqueue backend watches the INODE, not the path, so
             the watch now points at a dead inode and never fires again.

        Both manifest as a change in this signature: (1) adds a tuple, (2)
        swaps the ``st_ino`` for the same path. The watcher polls this on a
        cadence and restarts ``awatch`` with fresh targets whenever it
        differs — so the watch survives noms/ replacement and new-db
        creation without a process restart.
        """
        sig: set[tuple[str, int, int]] = set()
        for t in self.watch_targets():
            try:
                st = t.stat()
            except OSError:
                # Raced with a delete/replace — just omit it; the next poll
                # picks up the settled state.
                continue
            sig.add((str(t), st.st_dev, st.st_ino))
        return frozenset(sig)

    def revision_signature(self) -> frozenset[tuple[str, bytes]]:
        """Content fingerprint of every dolt db's committed state (bdboard-ywep).

        Returns a frozenset of ``(manifest_path, manifest_bytes)`` for every
        ``.dolt/noms/manifest`` under ``.beads/embeddeddolt/``. The manifest is
        a tiny (~150 byte) file whose payload is dolt's current ROOT HASH —
        it changes IFF the database content actually changed.

        Why this exists — the self-feedback loop it breaks:
        ``store.refresh()`` runs ``bd list --json``. Even a *read-only*
        ``bd list`` makes dolt re-touch ``journal.idx`` and rewrite
        ``manifest`` inside the watched ``noms/`` dir (new inode + bumped
        mtime), so the watcher fires for our OWN read. Pre-fix that re-trigger
        chained refreshes forever AND — because ``bd list`` is slower than the
        self-trigger latency on a large noms/ — cancelled each in-flight
        refresh before it could finish, so the board never updated until
        relaunch. Crucially the manifest *content* (root hash) is IDENTICAL
        across read-only churn and only flips on a real write, so comparing it
        lets the watcher distinguish "dolt actually changed" from "our own
        read jiggled the files" — and skip the expensive ``bd list`` entirely
        when nothing really changed, which is what stops the loop.

        Cheap by construction: one tiny file read per db (a handful of bytes),
        no subprocess, no dolt lock contention. Returns an empty set when the
        workspace has no embedded dolt dbs (e.g. legacy JSONL-only) so callers
        treat "no signal" as "always refresh" rather than "never refresh".
        """
        sig: set[tuple[str, bytes]] = set()
        embedded = self.beads_dir / "embeddeddolt"
        if not embedded.is_dir():
            return frozenset(sig)
        for db_dir in sorted(embedded.iterdir()):
            manifest = db_dir / ".dolt" / "noms" / "manifest"
            try:
                sig.add((str(manifest), manifest.read_bytes()))
            except OSError:
                # Manifest missing or mid-rotation — omit it. A partial
                # signature simply means the next refresh can't be skipped,
                # which is the safe direction (refresh rather than miss).
                continue
        return frozenset(sig)

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

    async def list_active(self) -> list[dict[str, Any]]:
        """Fetch only active issues (open/in_progress/blocked/deferred).

        This is the fast path for initial paint — ~5KB vs ~500KB for full
        fetch on a typical workspace. Blocked-by detection against closed
        issues will treat unknown targets as blocked (conservative), but
        most active→active dependencies are correctly resolved.

        Raises on subprocess failure or malformed JSON.
        """
        active = await self._run_json(
            ["list", "--no-pager", "--limit", "0"],
            timeout=LIST_TIMEOUT_S,
        )
        if not isinstance(active, list):
            raise RuntimeError(
                f"bd list (active) returned non-list ({type(active).__name__}); expected JSON array"
            )
        return active

    async def list_closed(self, window_days: int | None = None) -> list[dict[str, Any]]:
        """Fetch closed issues for the BOARD, bounded by a date window.

        The board is a recent-activity surface: its time-filter strip caps at
        12h / 1d / 3d, so the Closed lane (and the header CLOSED KPI that
        counts the same set) are bounded by the widest of those windows at
        fetch time -- NOT by a static count cap (bdboard-p8v). This keeps the
        two numbers consistent: both reflect the same date-bounded set,
        narrowed further client-side to the user's selected window.

        Issues closed before the window live on the History page, which has
        its own unbounded data path (:meth:`list_closed_history`).

        Args:
            window_days: Look-back window in days. Defaults to
                BOARD_CLOSED_WINDOW_DAYS from derive.lanes.

        Raises on subprocess failure or malformed JSON.
        """
        from bdboard.derive.lanes import BOARD_CLOSED_WINDOW_DAYS

        days = window_days if window_days is not None else BOARD_CLOSED_WINDOW_DAYS
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        closed = await self._run_json(
            [
                "list",
                "--status",
                "closed",
                "--closed-after",
                cutoff,
                "--sort",
                "closed",
                "--no-pager",
                "--limit",
                "0",
            ],
            timeout=LIST_TIMEOUT_S,
        )
        if not isinstance(closed, list):
            raise RuntimeError(
                f"bd list (closed) returned non-list ({type(closed).__name__}); expected JSON array"
            )
        return closed

    async def list_closed_history(
        self,
        limit: int | None = None,
        closed_after: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch the closed record for the HISTORY page, count-uncapped.

        Distinct from :meth:`list_closed` (the board path): History is the
        long-window retrospective surface, so it never applies a *count* cap
        (``--limit 0``); a static fetch cap would silently truncate to the
        newest N closures and make anything older unreachable regardless of
        the filters (bdboard-a194).

        It IS, however, bounded by the page's active filter *window* when one
        is supplied: ``closed_after`` pushes the range / custom-date lower
        bound down to the bd query via ``--closed-after`` (mirroring the
        board path), so a narrow range fetches only the beads closed inside
        it rather than slurping every closed bead into memory on every
        History snapshot (bdboard-gp06). The unbounded ``all`` view passes
        ``closed_after=None`` and stays a genuine full-table read by design.

        Args:
            limit: Optional explicit fetch cap. Defaults to ``None`` =
                count-unbounded (``--limit 0``). Pass a positive int only
                when a caller genuinely wants a truncated fetch (e.g. a
                smoke test).
            closed_after: Optional inclusive lower bound on ``closed_at``.
                When supplied, shells ``--closed-after <iso>`` so the result
                set is bounded by the chosen filter window. ``None`` (the
                default) issues an unbounded query for the ``all`` range.

        Raises on subprocess failure or malformed JSON.
        """
        cap = 0 if limit is None else limit
        args = ["list", "--status", "closed", "--sort", "closed", "--no-pager", "--limit", str(cap)]
        if closed_after is not None:
            cutoff = closed_after.astimezone(UTC) if closed_after.tzinfo else closed_after
            args += ["--closed-after", cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")]
        closed = await self._run_json(
            args,
            timeout=LIST_TIMEOUT_S,
        )
        if not isinstance(closed, list):
            raise RuntimeError(
                f"bd list (closed-history) returned non-list "
                f"({type(closed).__name__}); expected JSON array"
            )
        return closed

    # ----- gates & merge-slot: coordination overview (uncached, on-demand) -----

    async def list_gates(self) -> list[dict[str, Any]]:
        """List OPEN async-coordination gates via ``bd gate list --json``.

        A *gate* is a bead (``issue_type == "gate"``) that makes another bead
        WAIT on an external/async condition (a PR merge, a GitHub Actions run,
        a timer, a cross-rig bead, or a manual resolve). ``bd gate list``
        without ``--all`` returns only the OPEN (pending) gates — exactly the
        "Open Gates (N)" set the coordination panel surfaces.

        bd emits a JSON ``null`` (not ``[]``) when there are zero open gates,
        so we normalise ``null`` -> empty list rather than treating it as a
        malformed payload. Any other non-list shape is a genuine error.

        Raises RuntimeError on subprocess failure or a malformed (non-null,
        non-list) payload so the route can degrade to a friendly inline
        message instead of 500-ing the partial swap.
        """
        value = await self._run_json(["gate", "list"], timeout=GATE_LIST_TIMEOUT_S)
        if value is None:
            # bd serialises an empty open-gate set as JSON null, not [].
            return []
        if not isinstance(value, list):
            raise RuntimeError(
                f"bd gate list returned non-list ({type(value).__name__}); expected JSON array"
            )
        return value

    async def merge_slot_check(self) -> dict[str, Any]:
        """Check this rig's merge-slot availability via ``bd merge-slot check``.

        A merge-slot is bd's exclusive-access primitive: a single ``gt:slot``
        bead (``<prefix>-merge-slot``) that serialises conflict resolution.
        ``bd merge-slot check --json`` reports availability, e.g.::

            {"available": false, "error": "not found", "id": "x-merge-slot"}
            {"available": true,  "id": "x-merge-slot"}
            {"available": false, "holder": "agent-7", "id": "x-merge-slot"}

        A missing slot is a NORMAL state (most rigs never create one), reported
        by bd as ``{"available": false, "error": "not found"}`` with exit 0 —
        NOT a subprocess failure. We return whatever dict bd emits and let the
        caller decide how to frame it. A non-dict payload is a genuine error.

        Raises RuntimeError on subprocess failure or a non-dict payload.
        """
        value = await self._run_json(["merge-slot", "check"], timeout=MERGE_SLOT_TIMEOUT_S)
        if not isinstance(value, dict):
            raise RuntimeError(
                f"bd merge-slot check returned non-object "
                f"({type(value).__name__}); expected JSON object"
            )
        return value

    # ----- epic rollup + swarm: molecule progress & swarm coordination -----

    async def mol_progress(self, epic_id: str) -> dict[str, Any]:
        """Roll up an epic's children via ``bd mol progress <id> --json``.

        ``bd mol progress`` walks the epic's child tree and returns a compact
        rollup the epic strip surfaces back on the parent (audit FB-10 /
        formulas#2): ``{total, completed, in_progress, percent, molecule_id,
        molecule_title, current_step_id}``. It works on ANY epic with
        children, not just poured molecules, so the strip can show a
        count/progress rollup for hand-built epics too.

        Cheap enough (~0.7s observed) to fan out concurrently on the lanes
        hot path. Raises RuntimeError on subprocess failure or a non-dict
        payload; the caller gathers with ``return_exceptions=True`` so a
        rollup that can't be computed (e.g. a childless epic) simply omits
        the badge rather than breaking the board.
        """
        value = await self._run_json(
            ["mol", "progress", epic_id],
            timeout=MOL_PROGRESS_TIMEOUT_S,
        )
        if not isinstance(value, dict):
            raise RuntimeError(
                f"bd mol progress returned non-object "
                f"({type(value).__name__}); expected JSON object"
            )
        return value

    async def swarm_status(self, epic_id: str) -> dict[str, Any]:
        """Compute a swarm's live state via ``bd swarm status <id> --json``.

        Returns bd's computed swarm state (audit FB-10 / swarms#2): the
        ``progress_percent`` plus the four work cohorts —
        ``completed`` / ``active`` / ``ready`` / ``blocked`` (each a list of
        ``{id, title, assignee?}`` plus a matching ``*_count``) — and the
        ``epic_id`` / ``epic_title`` header. This is the only place bd's
        Completed/Active/Ready/Blocked breakdown is exposed.

        Slower than :meth:`mol_progress` (it resolves the readiness front), so
        callers fetch it ON DEMAND (when an epic modal opens), never on the
        lanes hot path. Raises RuntimeError on subprocess failure or a
        non-dict payload.
        """
        value = await self._run_json(
            ["swarm", "status", epic_id],
            timeout=SWARM_TIMEOUT_S,
        )
        if not isinstance(value, dict):
            raise RuntimeError(
                f"bd swarm status returned non-object "
                f"({type(value).__name__}); expected JSON object"
            )
        return value

    async def swarm_validate(self, epic_id: str) -> dict[str, Any]:
        """Validate an epic's swarmability via ``bd swarm validate <id> --json``.

        Returns bd's structural analysis (audit FB-10 / swarms#3): whether the
        epic is ``swarmable``, its ``max_parallelism`` and
        ``estimated_sessions``, any ``errors`` / ``warnings``, and the WAVE
        model — ``ready_fronts``, a list of ``{wave, issues, titles}`` groups
        that can run in parallel. bd emits ``errors`` / ``warnings`` as JSON
        ``null`` when empty (NOT ``[]``); callers normalise downstream.

        On-demand only (DAG walk, ~2.6s observed). Raises RuntimeError on
        subprocess failure or a non-dict payload.
        """
        value = await self._run_json(
            ["swarm", "validate", epic_id],
            timeout=SWARM_TIMEOUT_S,
        )
        if not isinstance(value, dict):
            raise RuntimeError(
                f"bd swarm validate returned non-object "
                f"({type(value).__name__}); expected JSON object"
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
        ``_cached``. Raises (like :meth:`list_active`) on subprocess failure
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
                f"bd memories returned non-object ({type(value).__name__}); expected JSON object"
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
        concurrent requests can't deadlock on bd's dolt lock.

        IMPORTANT: This method is carefully structured to avoid fd leaks.
        asyncio.create_subprocess_exec with PIPE opens file descriptors
        that are only closed when communicate() completes. If the coroutine
        is interrupted (TimeoutError, CancelledError) before communicate()
        finishes, the pipes leak. We MUST call communicate() on every exit
        path — even when killing the process — to drain the pipes and close
        the transport. The debounce task in app.py can cancel refresh() at
        any time, so CancelledError can arrive mid-communicate; without
        cleanup, each cancellation leaks ~3 fds (stdin/stdout/stderr pipes)
        until RLIMIT_NOFILE is exhausted.
        """
        async with self._subprocess_gate:
            proc = await asyncio.create_subprocess_exec(
                self.bd_bin,
                *args,
                "--json",
                cwd=str(self.workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timed_out = False
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                timed_out = True
                _safe_kill(proc)
                # MUST call communicate() to drain pipes and close transport
                stdout, stderr = await proc.communicate()
            except BaseException:
                # CancelledError or other unexpected error — cleanup then re-raise.
                # _safe_kill swallows ProcessLookupError so the draining
                # communicate() still runs and the original error propagates.
                _safe_kill(proc)
                await proc.communicate()  # drain + close
                raise
            if timed_out:
                raise RuntimeError("Request timed out while loading bead data. Please try again.")
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Could not load bead data right now ({args[0]}). Please try again."
                )
            try:
                return json.loads(stdout)
            except json.JSONDecodeError as err:
                raise RuntimeError(
                    "Received an unexpected response while loading bead data."
                ) from err

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

    async def show_long(
        self, bead_id: str, fresh: bool = False
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch the full bead detail via `bd show <id> --long --json`.
        Returns (bead_dict, error_msg). bd returns a JSON array; we unwrap.

        ``fresh=True`` drops any cached entry for this bead first, forcing a
        live read. The optimistic-lock precondition check (the field-edit
        route) needs this: a stale cache (up to SUCCESS_TTL_S
        old) could report an out-of-date ``updated_at`` and let a concurrent
        edit slip through undetected, silently clobbering the other writer.
        """
        if fresh:
            self._show_cache.pop(bead_id, None)
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

    async def history(self, bead_id: str) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch audit history via `bd history <id> --json`.
        Returns (entries_list, error_msg). Failure is normal and surfaced."""
        return await self._cached(
            self._history_cache,
            key=bead_id,
            fetch_args=["history", bead_id],
            timeout=HISTORY_TIMEOUT_S,
        )

    async def status_summary(self) -> dict[str, Any] | None:
        """Fetch bd's aggregate status summary via `bd status --json`.

        Returns the ``summary`` sub-object (``closed_issues``,
        ``in_progress_issues``, ``average_lead_time_hours``,
        ``total_issues``, …) or None when bd is unavailable / the payload
        is malformed. The History page uses this as an *optional* headline
        KPI (design §6, bead F): bd's own point-in-time numbers, rendered
        alongside the client-derived range stats. Because it is optional
        sugar, callers treat None as "just hide the headline" rather than
        an error — the range-derived KPIs remain the primary surface.

        Cached + in-flight-deduped via ``_cached`` (single shared key,
        since the summary is workspace-global, not per-bead).
        """
        value, err = await self._cached(
            self._status_cache,
            key="",
            fetch_args=["status"],
            timeout=STATUS_TIMEOUT_S,
        )
        if err is not None or not isinstance(value, dict):
            return None
        summary = value.get("summary")
        return summary if isinstance(summary, dict) else None

    def invalidate_caches(self) -> None:
        """Drop show/history/memories/status caches. Called by Store after a
        watcher fire so the next detail, memory, or status request picks up
        post-mutation state instead of serving up-to-10s-old cached values."""
        self._show_cache.clear()
        self._history_cache.clear()
        self._memories_cache.clear()
        self._status_cache.clear()

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

    # ----- formulas: list + variable enumeration + pour -----

    async def list_formulas(self) -> list[dict[str, Any]]:
        """List available formulas via `bd formula list --json`.

        Returns a list of formula dicts, each carrying at least ``name``,
        ``description`` and ``source`` (the absolute path to the on-disk
        ``*.formula.json`` template). The picker uses ``name`` + ``description``;
        ``source`` is the hook :meth:`read_formula_variables` reads to enumerate
        variables.

        ⚠️ The ``vars`` count in this payload is unreliable (bd reports ``0``
        even when variables exist), so do
        NOT use it to decide whether a formula has variables. Read the source
        file instead.

        Raises RuntimeError on subprocess failure or malformed JSON.
        """
        value = await self._run_json(
            ["formula", "list"],
            timeout=FORMULA_LIST_TIMEOUT_S,
        )
        if not isinstance(value, list):
            raise RuntimeError(
                f"bd formula list returned non-list ({type(value).__name__}); expected JSON array"
            )
        return value

    def read_formula_variables(self, source: str) -> list[dict[str, Any]]:
        """Parse a formula's ``variables`` block from its ``*.formula.json`` file.

        ``source`` is the absolute path bd reports in ``formula list --json``.
        We read the template file directly because the bd CLI does NOT expose
        variables any other way:
          - ``bd formula show <name> --json`` OMITS the ``variables`` block.
          - the ``vars`` count in ``formula list --json`` is wrong (always 0).

        Returns an ordered list of variable descriptors:
            [{"name": str, "description": str, "default": str | None,
              "required": bool}, ...]
        ``required`` is True when the variable has no ``default`` — the pour
        pre-flight blocks until every required var is filled (§4.4).

        Reading ``*.formula.json`` is consistent with bdboard's
        CLI-as-source-of-truth posture: the template is a *different* file from
        the issue store, and we only reach it via the absolute path the CLI
        handed us. If a future bd release adds ``variables`` to
        ``formula show --json``, switch to that and drop the file read.

        Raises RuntimeError if the file is missing or unparseable.
        """
        return self._parse_variables(self._load_formula_json(source))

    def read_formula_detail(self, source: str) -> dict[str, Any]:
        """Parse a formula's full description + variables + steps in one read.

        ``source`` is the absolute path bd reports in ``formula list --json``.
        We read the on-disk ``*.formula.json`` template because it is the ONLY
        reliable source for BOTH the untruncated description and the step list:
          - ``formula list --json`` TRUNCATES the description (trailing ``…``).
          - ``formula show --json`` omits variables and isn't relied on here.

        Returns::

            {"description": str,                 # full, untruncated
             "variables": [ {name, description,  # same shape as
                             default, required} ],#   read_formula_variables
             "steps": [ {id, title, description, type, priority} ]}

        Sharing :meth:`_load_formula_json` keeps this single-read and DRY with
        :meth:`read_formula_variables` (which the pour route still uses on its
        own). Raises RuntimeError if the file is missing or unparseable.
        """
        data = self._load_formula_json(source)
        return {
            "description": data.get("description") or "",
            "variables": self._parse_variables(data),
            "steps": self._parse_steps(data),
        }

    @staticmethod
    def _load_formula_json(source: str) -> dict[str, Any]:
        """Read + parse a ``*.formula.json`` file into a dict.

        Shared loader for :meth:`read_formula_variables` and
        :meth:`read_formula_detail`. Raises RuntimeError on a missing file,
        invalid JSON, or a non-object top level.
        """
        path = Path(source)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as err:
            raise RuntimeError(f"Could not read formula file: {err}") from err
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"Formula file is not valid JSON: {err}") from err
        if not isinstance(data, dict):
            raise RuntimeError(f"Formula file is not a JSON object ({type(data).__name__})")
        return data

    @staticmethod
    def _parse_variables(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the ordered variable descriptors from parsed formula data."""
        variables = data.get("variables")
        if not isinstance(variables, dict):
            # No variables block (or a malformed one) → an empty form, which is
            # a valid "pour with no inputs" case, not an error.
            return []
        result: list[dict[str, Any]] = []
        for name, spec in variables.items():
            spec = spec if isinstance(spec, dict) else {}
            default = spec.get("default")
            result.append(
                {
                    "name": name,
                    "description": spec.get("description") or "",
                    "default": default,
                    "required": default is None,
                }
            )
        return result

    @staticmethod
    def _parse_steps(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the ordered step descriptors from parsed formula data.

        Each step exposes the fields the modal surfaces: ``id``, ``title``,
        ``description``, ``type`` and ``priority``. Non-dict entries (a
        malformed steps array) are skipped rather than raising — a partial
        step list is more useful in the disclosure than a hard error.
        """
        steps = data.get("steps")
        if not isinstance(steps, list):
            return []
        result: list[dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            result.append(
                {
                    "id": step.get("id") or "",
                    "title": step.get("title") or "",
                    "description": step.get("description") or "",
                    "type": step.get("type") or "",
                    "priority": step.get("priority"),
                }
            )
        return result

    async def pour_formula(self, name: str, variables: dict[str, str]) -> dict[str, Any]:
        """Pour a formula onto the board via `bd mol pour <name> --var k=v ... --json`.

        A hybrid call: it MUTATES the workspace (pour cooks the formula inline
        and materializes its bead tree) AND returns parsed JSON. The result
        carries ``new_epic_id`` (the molecule wrapper node that parents the
        whole tree), ``id_mapping`` (stepId → real bead id) and ``created``
        (node count).

        Serialized on ``_subprocess_gate`` (bd's embedded dolt is single-writer).
        On non-zero exit we surface bd's stderr verbatim (same posture as
        ``_run_mutate``) so pre-flight-passing pours that still fail at the bd
        layer — e.g. the broken-formula dependency bug in §4.2, which
        ``--dry-run`` does NOT catch — show the real reason. Pour is atomic:
        a failed pour rolls back to zero new beads (§4.3), so the board is
        never left with orphans.

        After a successful pour we invalidate caches so follow-up reads (the
        rename, the list refresh) see post-pour state.

        On success we ALSO capture bd's stderr (not just on the failure path):
        ``bd mol pour`` exits 0 but warns on stderr when a ``phase: "vapor"``
        formula — one the author marked ephemeral (wisp) — is poured as a
        persistent, git-synced tree. When that warning is present we attach it
        to the returned dict under ``_wisp_warning`` so the route can surface a
        "this recommends wisp — poured as persistent" notice (bdboard-6nl8).

        Raises RuntimeError (bd's stderr) on failure or malformed JSON.

        Subprocess cleanup mirrors _run_json: we MUST call communicate() on
        every exit path to drain pipes and close the transport, preventing
        fd leaks on timeout or cancellation.
        """
        args = ["mol", "pour", name]
        for key, val in variables.items():
            args += ["--var", f"{key}={val}"]
        args.append("--json")
        async with self._subprocess_gate:
            proc = await asyncio.create_subprocess_exec(
                self.bd_bin,
                *args,
                cwd=str(self.workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timed_out = False
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=POUR_TIMEOUT_S)
            except TimeoutError:
                timed_out = True
                _safe_kill(proc)
                stdout, stderr = await proc.communicate()  # drain + close
            except BaseException:
                _safe_kill(proc)
                await proc.communicate()  # drain + close
                raise
            if timed_out:
                raise RuntimeError(
                    "Pour timed out. The formula may still be materializing — refresh in a moment."
                )
            if proc.returncode != 0:
                err_text = stderr.decode(errors="replace").strip()
                raise RuntimeError(err_text or f"bd mol pour failed (exit {proc.returncode}).")
            # bd prints a vapor-phase recommendation on stderr with EXIT 0 when a
            # formula authored as ephemeral (phase: "vapor") is poured as a
            # persistent, git-synced tree. We read stderr on the SUCCESS path too
            # (it was previously consumed only on non-zero exit) so we can surface
            # the author's "this should be a wisp" intent instead of silently
            # honoring it. The pour itself still succeeded — this is a notice, not
            # an error.
            warn_text = stderr.decode(errors="replace").strip()
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError as err:
                raise RuntimeError("Pour succeeded but returned an unexpected response.") from err
        self.invalidate_caches()
        if not isinstance(result, dict):
            raise RuntimeError(
                f"bd mol pour returned non-object ({type(result).__name__}); expected JSON object"
            )
        # Attach the vapor-phase recommendation (if bd emitted one) under a
        # synthetic underscore key so it rides alongside bd's own payload without
        # clobbering it. Matched on the STABLE phrase bd prints — "recommends
        # vapor phase" — so a future emoji/wording tweak won't silently drop it.
        if "recommends vapor phase" in warn_text.lower():
            result["_wisp_warning"] = warn_text
        return result

    async def rename_bead(self, bead_id: str, title: str) -> None:
        """Rename a bead's title via `bd update <id> --title <title>`.

        Used by the pour route to retitle the molecule wrapper / epic root
        step to ``<formula> <id>``. Serialized on the
        subprocess gate; surfaces bd's stderr on failure. Caches are
        invalidated so the post-rename list reflects the new title.
        """
        await self._run_mutate(
            ["update", bead_id, "--title", title],
            timeout=UPDATE_TIMEOUT_S,
        )
        self.invalidate_caches()

    # Flags whose value bd can read from a file/stdin instead of a positional
    # arg. Long markdown (description, design) goes through stdin via these
    # *-file variants with '-' to dodge shell-arg length limits and any
    # quoting fragility. Every other flag (title,
    # priority, append-notes, ...) takes its value directly as an arg — which
    # is already shell-safe because we use create_subprocess_exec (no shell).
    _STDIN_FLAG_ALIASES = {
        "--description": "--body-file",
        "--design": "--design-file",
    }

    async def update_field(
        self,
        bead_id: str,
        flag: str,
        value: str,
        actor: str | None = None,
    ) -> None:
        """Edit a single bead field value via `bd update <id> <flag> <value>`.

        Thin sibling of remember/forget: serialized on the same
        _subprocess_gate (bd's dolt store is single-writer), surfaces bd's
        stderr on failure, and invalidates caches so the next read returns
        post-edit state instead of an up-to-10s-stale snapshot.

        `flag` is the exact `bd update` flag the caller pulled from the field
        registry (e.g. '--title', '--priority', '--append-notes'). For long
        markdown flags (description/design) the value is streamed on stdin
        via the file-flag variant rather than passed as a positional arg.
        `actor` (when set) is forwarded as --actor so the audit trail
        attributes the human edit correctly rather than to an agent identity;
        when None, bd falls back to $BEADS_ACTOR / git user.name / $USER.

        Raises RuntimeError on subprocess failure (bd's stderr surfaced).
        """
        args = ["update", bead_id]
        stdin_data: str | None = None
        file_flag = self._STDIN_FLAG_ALIASES.get(flag)
        if file_flag is not None:
            args += [file_flag, "-"]
            stdin_data = value
        else:
            args += [flag, value]
        if actor:
            args += ["--actor", actor]
        await self._run_mutate(args, timeout=UPDATE_TIMEOUT_S, stdin_data=stdin_data)
        # Drop the per-bead detail cache immediately so the route's follow-up
        # show_long returns the freshly-edited value (the watcher will also
        # fire, but may lose the race against the optimistic re-render). We
        # also invalidate the sibling caches the edit may have shifted.
        self._show_cache.clear()
        self.invalidate_caches()

    async def _run_mutate(
        self,
        args: list[str],
        timeout: float,
        stdin_data: str | None = None,
    ) -> None:
        """Run a bd mutation command (no --json, no parse, check exit only).

        Serialized via _subprocess_gate like read commands; mutations are
        single-writer so we must avoid concurrent writes from multiple
        browser tabs / users on the same workspace. When stdin_data is
        provided it is written to the child's stdin (used to stream long
        markdown via bd's --body-file -/--design-file - so we never hit
        shell-arg length limits).

        Subprocess cleanup mirrors _run_json: we MUST call communicate() on
        every exit path to drain pipes and close the transport, preventing
        fd leaks on timeout or cancellation.
        """
        async with self._subprocess_gate:
            proc = await asyncio.create_subprocess_exec(
                self.bd_bin,
                *args,
                cwd=str(self.workspace),
                stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            input_bytes = stdin_data.encode() if stdin_data is not None else None
            timed_out = False
            try:
                _stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=input_bytes), timeout=timeout
                )
            except TimeoutError:
                timed_out = True
                _safe_kill(proc)
                _stdout, stderr = await proc.communicate()  # drain + close
            except BaseException:
                _safe_kill(proc)
                await proc.communicate()  # drain + close
                raise
            if timed_out:
                raise RuntimeError("Request timed out while saving. Please try again.")
            if proc.returncode != 0:
                # bd forget on a non-existent key (or update on a bad value)
                # exits non-zero with a descriptive stderr; surface it.
                err_text = stderr.decode(errors="replace").strip()
                raise RuntimeError(
                    err_text or f"bd {args[0]} failed (exit {proc.returncode}). Please try again."
                )

    # ----- dolt sync state (masthead badge) -----

    async def dolt_sync_status(self) -> dict[str, Any]:
        """Best-effort local-vs-remote Dolt sync state for the masthead badge.

        bdboard reads the LOCAL dolt store and otherwise never looks at the
        remote, so a teammate's ``bd dolt push`` (or your own un-pushed writes)
        leaves the board silently stale-vs-origin. This surfaces that drift.

        Returns a dict the route renders directly:
            ``state``  one of: ``no-remote`` | ``synced`` | ``ahead`` |
                       ``behind`` | ``diverged`` | ``unknown``
            ``ahead``  local commits not yet on the remote (un-pushed)
            ``behind`` remote commits not yet local (un-pulled)
            ``remote`` the remote name, or None
            ``branch`` the active branch, or None

        NEVER raises (CancelledError aside) — a 500 on the masthead would be
        worse than a quiet ``unknown``. Every shell-out degrades to ``unknown``
        on failure, so a missing remote, an absent ``dolt`` binary, or a
        never-fetched remote ref all fail soft.

        Why two binaries: ``bd dolt status`` reports engine state (embedded vs
        server), not ahead/behind — bd exposes no porcelain for commit drift.
        So we use bd for the offline checks (remote configured? engine ok?) and
        read the actual ahead/behind counts straight from the embedded dolt db
        via the standalone ``dolt`` binary. If ``dolt`` isn't on PATH we still
        report ``no-remote`` vs (remote-present-but-unknown) honestly.
        """
        result: dict[str, Any] = {
            "state": "unknown",
            "ahead": 0,
            "behind": 0,
            "remote": None,
            "branch": None,
        }

        # 1) Is a Dolt remote configured? bd-native, offline. No remote => the
        #    board can't be ahead/behind, so short-circuit to 'no-remote'.
        remotes = await self._bd_dolt_remotes()
        if remotes is None:
            return result  # couldn't even list remotes -> unknown
        if not remotes:
            result["state"] = "no-remote"
            return result
        result["remote"] = remotes[0]

        # 2) Liveness probe: `bd dolt status`. Its payload doesn't carry
        #    ahead/behind, but a failed/missing engine should read 'unknown'
        #    rather than a misleading 'synced'. Soft-fails (never 500).
        if not await self._bd_dolt_status_ok():
            return result

        # 3) Ahead/behind: compare local branch HEAD to its remote-tracking
        #    ref via the embedded dolt db. Degrades to 'unknown' when dolt is
        #    absent or the remote ref was never fetched.
        counts = await self._dolt_ahead_behind(remotes[0])
        if counts is None:
            return result
        branch, ahead, behind = counts
        result["branch"] = branch
        result["ahead"] = ahead
        result["behind"] = behind
        if ahead and behind:
            result["state"] = "diverged"
        elif ahead:
            result["state"] = "ahead"
        elif behind:
            result["state"] = "behind"
        else:
            result["state"] = "synced"
        return result

    async def _bd_dolt_remotes(self) -> list[str] | None:
        """Configured Dolt remote names (possibly empty), or None on error.

        ``bd dolt remote list --json`` emits a JSON array of
        ``{name, sql_url, ...}`` — or null/[] when none are configured. We
        normalise any non-list payload to ``[]`` (no remotes).
        """
        payload = await self._run_capture_json([self.bd_bin, "dolt", "remote", "list", "--json"])
        if payload is None:
            return None
        if not isinstance(payload, list):
            return []
        return [str(r["name"]) for r in payload if isinstance(r, dict) and r.get("name")]

    async def _bd_dolt_status_ok(self) -> bool:
        """True iff ``bd dolt status --json`` returns a parseable object."""
        payload = await self._run_capture_json([self.bd_bin, "dolt", "status", "--json"])
        return isinstance(payload, dict)

    async def _dolt_ahead_behind(self, remote: str) -> tuple[str, int, int] | None:
        """(branch, ahead, behind) from the embedded dolt db, or None on any
        failure (no dolt binary, db not found, remote ref never fetched)."""
        if not shutil.which(self.dolt_bin):
            return None
        if not _DOLT_REF_SAFE.match(remote):
            return None
        db_dir = await self._resolve_dolt_db_dir()
        if db_dir is None:
            return None
        branch_rows = await self._run_dolt_sql(db_dir, "SELECT active_branch() AS branch")
        if not branch_rows:
            return None
        branch = branch_rows[0].get("branch")
        if not isinstance(branch, str) or not _DOLT_REF_SAFE.match(branch):
            return None
        tracking = f"remotes/{remote}/{branch}"
        # COUNT commits each side has that the other lacks. dolt_log('A..B')
        # is B's commits not reachable from A. If the remote-tracking ref was
        # never fetched it doesn't exist and dolt_log errors -> None -> unknown.
        query = (
            f"SELECT (SELECT COUNT(*) FROM dolt_log('{tracking}..{branch}')) AS ahead, "
            f"(SELECT COUNT(*) FROM dolt_log('{branch}..{tracking}')) AS behind"
        )
        rows = await self._run_dolt_sql(db_dir, query)
        if not rows:
            return None
        try:
            return branch, int(rows[0]["ahead"]), int(rows[0]["behind"])
        except (KeyError, TypeError, ValueError):
            return None

    async def _resolve_dolt_db_dir(self) -> Path | None:
        """Locate (and cache) the active embedded dolt db directory.

        ``.beads/embeddeddolt/`` can hold several dbs (e.g. a stray ``beads``
        alongside the project db). We prefer the name from ``bd dolt show
        --json`` and fall back to the first subdir that actually has a
        ``.dolt/`` store. Cached for the process lifetime.
        """
        if self._dolt_db_dir is not None:
            return self._dolt_db_dir
        embedded = self.beads_dir / "embeddeddolt"
        if not embedded.is_dir():
            return None
        payload = await self._run_capture_json([self.bd_bin, "dolt", "show", "--json"])
        candidate: Path | None = None
        if isinstance(payload, dict) and isinstance(payload.get("database"), str):
            named = embedded / payload["database"]
            if (named / ".dolt").is_dir():
                candidate = named
        if candidate is None:
            for d in sorted(embedded.iterdir()):
                if (d / ".dolt").is_dir():
                    candidate = d
                    break
        if candidate is None:
            return None
        self._dolt_db_dir = candidate
        return candidate

    async def _run_dolt_sql(self, db_dir: Path, query: str) -> list[dict[str, Any]] | None:
        """Run a read-only ``dolt sql -r json -q <query>`` in ``db_dir`` and
        return its rows, or None on any failure. dolt's JSON result format is
        ``{"rows": [ {..}, .. ]}``.
        """
        payload = await self._run_capture_json(
            [self.dolt_bin, "sql", "-r", "json", "-q", query], cwd=db_dir
        )
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            return payload["rows"]
        return None

    async def _run_capture_json(self, argv: list[str], cwd: Path | None = None) -> Any:
        """Run ``argv``, capture stdout, parse JSON. Returns the parsed object,
        or None on ANY failure (binary missing, non-zero exit, timeout, bad
        JSON). NEVER raises except for CancelledError (which must propagate for
        clean task teardown) — the sync-badge path wants a quiet degrade to
        'unknown', not a 500.

        Serialized on ``_subprocess_gate`` so it can't race bd's single-writer
        embedded dolt, and drains pipes on every exit path to avoid fd leaks
        (same posture as :meth:`_run_json`).
        """
        async with self._subprocess_gate:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=str(cwd or self.workspace),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError:
                # Binary not found / fd exhaustion — degrade quietly.
                return None
            timed_out = False
            try:
                stdout, _stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=DOLT_SYNC_TIMEOUT_S
                )
            except TimeoutError:
                timed_out = True
                _safe_kill(proc)
                stdout, _stderr = await proc.communicate()  # drain + close
            except BaseException:
                # CancelledError etc. — cleanup then propagate.
                _safe_kill(proc)
                await proc.communicate()  # drain + close
                raise
            if timed_out or proc.returncode != 0:
                return None
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return None
