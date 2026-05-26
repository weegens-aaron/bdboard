"""FastAPI application — composes routes over BdClient + Store + derive."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from watchfiles import awatch

from bdboard import __version__, derive, md
from bdboard.bd import BdClient
from bdboard.events import EventBus
from bdboard.store import Store

log = logging.getLogger(__name__)


def _safe_cwd() -> str:
    """Return current working directory, surviving macOS TCC sandboxing.

    os.getcwd() raises PermissionError in iCloud / Documents / Desktop
    folders for unsigned binaries. Fall back to $PWD (the shell always
    knows where it is and TCC doesn't gate env vars), then to '/' as a
    last resort so import doesn't crash. The CLI's _resolve_workspace
    handles the real user-facing error — this just keeps import alive.
    """
    try:
        return os.getcwd()
    except (PermissionError, OSError):
        return os.environ.get("PWD") or "/"

# ----- module-level singletons (one per process) -----

_PKG_DIR = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(_PKG_DIR / "templates"))
TEMPLATES.env.filters["humanize_ts"] = derive.humanize_ts
# md filter: renders markdown to HTML. Marked safe via Jinja's |safe in the
# template so we don't double-escape. Source content is bd-authored prose
# and the renderer has html=False, so script-injection is not possible.
TEMPLATES.env.filters["md"] = md.render
# Footer + masthead always have access to these.
TEMPLATES.env.globals["version"] = __version__
# Cache-bust query param for /static assets. Every server restart gets a
# fresh value — means no more 'why is my CSS old?' moments during dev,
# and zero cost in prod (HTTP caches see a new URL only on redeploy).
TEMPLATES.env.globals["asset_v"] = str(int(time.time()))

# Workspace + bd binary are picked up from env, set by the CLI before the app
# is imported. Sensible defaults for `uvicorn bdboard.app:app --reload` dev.
#
# IMPORTANT: do NOT pass os.getcwd() as the default arg to os.environ.get().
# Python evaluates default args eagerly, so getcwd() runs every time — even
# when BDBOARD_WORKSPACE is set — which crashes under macOS TCC sandboxing.
# Use the `or` short-circuit instead: env wins, getcwd() only runs if needed,
# and we wrap getcwd() to fall back to $PWD when sandboxed.
_WORKSPACE = Path(os.environ.get("BDBOARD_WORKSPACE") or _safe_cwd())
_BD_BIN = os.environ.get("BDBOARD_BD_BIN", "bd")

bd = BdClient(bd_bin=_BD_BIN, workspace=_WORKSPACE)
store = Store(bd)


def _validate_or_warn() -> str | None:
    """Validate workspace lazily so import doesn't crash in tests."""
    try:
        bd.validate()
        return None
    except RuntimeError as e:
        return str(e)


# ----- app -----

bus = EventBus()

# Watcher tuning, ported from mantoni/beads-ui server/watcher.js.
#
# DEBOUNCE: a single `bd update` typically writes 3-5 files inside
# .beads/embeddeddolt/ in quick succession (manifest, journal.idx, lock
# file, ...). Without a quiet-window, we'd fire 3-5 refreshes per
# logical mutation. 250ms is comfortably longer than the burst and far
# shorter than human perception.
#
# COOLDOWN: after a refresh completes, suppress further refreshes for
# 1s. Stops a sustained write storm (e.g. bd's dolt commit + auto-export
# fan-out + git-add hook) from chain-firing refreshes at full FS speed.
WATCHER_DEBOUNCE_S = 0.25
WATCHER_COOLDOWN_S = 1.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Spin up the .beads/ directory watcher on app boot.

    bdboard is a pure OBSERVER on the dolt-native source of truth:

      bd writes dolt  →  files mutate inside .beads/embeddeddolt/
        →  watchfiles fires  →  Store.refresh() runs `bd list --json`
        →  if data changed, broadcast SSE  →  browser refetches partials

    We do NOT read .beads/issues.jsonl directly any more — per
    COMMUNITY_TOOLS.md that path is deprecated. bd list --json is the
    only source of truth in this process.
    """
    watcher_task = asyncio.create_task(_watch_beads(), name="bdboard.watcher")
    log.info("watcher started for %s", bd.beads_dir)
    try:
        yield
    finally:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass
        log.info("watcher stopped")


async def _watch_beads() -> None:
    """React to ANY change inside .beads/ (dolt files included).

    Implementation mirrors mantoni/beads-ui server/watcher.js: a trailing
    debounce window absorbs burst-writes from one logical bd command;
    a cooldown after each refresh prevents back-to-back refreshes from
    sustained activity.

    Why recursive .beads/ instead of just issues.jsonl:
    dolt writes happen inside .beads/embeddeddolt/jira_beads/.dolt/noms/
    on every bd update — INSTANTLY, no throttle. The legacy issues.jsonl
    is a throttled secondary export that can lag up to export.interval
    (default 60s). Watching dolt's storage directly gives us sub-second
    latency for free.
    """
    target_dir = bd.beads_dir
    while True:
        try:
            # watchfiles.awatch yields a batch (set of (change, path))
            # roughly every 50ms of FS activity — it already does light
            # batching for us. Our debounce sits on top of that to collapse
            # multi-batch bursts (a bd update often spans 2-3 batches).
            async for _changes in awatch(target_dir, recursive=True):
                await _settle_then_refresh()
        except FileNotFoundError:
            # .beads dir not there yet — wait and retry
            await asyncio.sleep(2)
        except Exception:
            log.exception("watcher crashed; restarting in 2s")
            await asyncio.sleep(2)


_last_refresh_at: float = 0.0
_pending_settle: asyncio.Task | None = None


async def _settle_then_refresh() -> None:
    """Debounce + cooldown wrapper around Store.refresh().

    Called for every batch of FS events. Cancels any in-flight settle
    task and starts a fresh one — so a continuous stream of events keeps
    pushing the actual refresh out by debounce_s, until the writes
    finally stop and the timer fires.
    """
    global _pending_settle
    if _pending_settle is not None and not _pending_settle.done():
        _pending_settle.cancel()
    _pending_settle = asyncio.create_task(_settle_task())


async def _settle_task() -> None:
    """Sleep one debounce window; if we get cancelled by a new event,
    silently exit. Otherwise refresh + broadcast (respecting cooldown)."""
    global _last_refresh_at
    try:
        await asyncio.sleep(WATCHER_DEBOUNCE_S)
    except asyncio.CancelledError:
        return
    now = time.monotonic()
    if now - _last_refresh_at < WATCHER_COOLDOWN_S:
        # Within cooldown — swallow this event. The next event after
        # cooldown expires will trigger a fresh debounce + refresh, so
        # we don't miss real subsequent changes.
        return
    try:
        changed = await store.refresh()
    except Exception:
        log.exception("watcher: store.refresh raised; continuing")
        return
    _last_refresh_at = time.monotonic()
    if changed:
        await bus.broadcast("beads_changed")


app = FastAPI(title="bdboard", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")


@app.get("/api/events")
async def sse_events(request: Request) -> StreamingResponse:
    """Server-Sent Events stream. Browser subscribes once per page load;
    every file-change event causes the browser to refresh its lanes/counts
    panels. Periodic heartbeat keeps proxies / load balancers
    from killing the long-lived connection (typical idle timeout is 30-60s,
    so 15s heartbeat has comfortable margin)."""

    async def stream():
        async with bus.subscribe() as q:
            # Initial bootstrap event so a freshly-connected client renders
            # immediately rather than waiting for the first file change.
            yield "event: beads_changed\ndata: bootstrap\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"event: {event}\ndata: {int(time.time())}\n\n"
                except asyncio.TimeoutError:
                    # heartbeat — a comment line keeps the connection alive
                    # without firing any client-side event handler
                    yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
        },
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    err = _validate_or_warn()
    if err:
        return TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {"error": err, "workspace": str(_WORKSPACE)},
            status_code=500,
        )
    beads = await store.snapshot()
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        {
            "workspace": _WORKSPACE.name,
            "workspace_path": str(_WORKSPACE),
            "counts": derive.counts(beads),
            "lanes": derive.lanes(beads),
            "activity": derive.activity(beads),
        },
    )


# ----- HTMX partials (polled every few seconds by the dashboard) -----


@app.get("/api/lanes", response_class=HTMLResponse)
async def api_lanes(request: Request) -> HTMLResponse:
    """Renders the swim lanes including the Activity column. Activity ships
    inside the same partial (and the same /api/lanes refresh) because it's
    now a regular lane — no separate sidebar, no separate endpoint."""
    beads = await store.snapshot()
    return TEMPLATES.TemplateResponse(
        request,
        "partials/lanes.html",
        {
            "lanes": derive.lanes(beads),
            "activity": derive.activity(beads),
        },
    )


@app.get("/api/counts", response_class=HTMLResponse)
async def api_counts(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "partials/counts.html",
        {"counts": derive.counts(await store.snapshot())},
    )


# ----- bead detail (the bug fix the user actually asked for) -----


@app.get("/api/bead/{bead_id}", response_class=HTMLResponse)
async def api_bead(request: Request, bead_id: str) -> HTMLResponse:
    """Synchronous bead-detail render. Tries `bd show --long --json` for the
    full field set; falls back to the cached bd-list snapshot if the show
    call fails or times out, so the modal *always* renders something
    useful — that's the whole point of this rewrite."""
    full, err = await bd.show_long(bead_id)
    bead: dict[str, Any] | None = full
    source = "bd show --long"
    if bead is None:
        # Ensure the snapshot is populated for the fallback lookup.
        await store.snapshot()
        bead = store.bead(bead_id)
        source = "bd list (fallback — bd show failed)"
    if bead is None:
        return HTMLResponse(
            f"<div class='modal-error'>bead <code>{bead_id}</code> not found</div>",
            status_code=404,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "partials/bead_modal.html",
        {
            "bead": bead,
            "fields": _ordered_fields(bead),
            "source": source,
            "warning": err if full is None and err else None,
        },
    )


@app.get("/api/bead/{bead_id}/audit", response_class=HTMLResponse)
async def api_bead_audit(request: Request, bead_id: str) -> HTMLResponse:
    """Async audit-trail render. Failures here render a graceful 'unavailable'
    partial — they do NOT block the modal (the modal loads /api/bead first,
    then this lazily via hx-trigger='load')."""
    entries, err = await bd.history(bead_id)
    if entries is None:
        return TEMPLATES.TemplateResponse(
            request,
            "partials/bead_audit.html",
            {"entries": None, "error": err},
        )
    rendered = _shape_audit(entries)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/bead_audit.html",
        {"entries": rendered, "error": None},
    )


@app.get("/api/bead/{bead_id}/raw", response_class=JSONResponse)
async def api_bead_raw(bead_id: str) -> JSONResponse:
    """Escape hatch: dump every field bd knows about as raw JSON. Useful
    when the modal layout hides something you need."""
    full, err = await bd.show_long(bead_id)
    if full is None:
        await store.snapshot()
        full = store.bead(bead_id) or {"error": err or "not found"}
    return JSONResponse(full)


# ----- helpers -----

# Field display order in the modal: identity first, then state, then
# everything else. Anything not in this list gets appended alphabetically
# so we never silently hide a new bd field.
# Field display order in the modal: identity anchors first, then the
# CONTENT (what does this work entail? — description, acceptance criteria,
# dependencies), then meta/state info, then bulk/diagnostic at the bottom.
# Anything not in this list gets appended alphabetically so we never
# silently hide a new bd field.
_FIELD_ORDER = [
    # ─ identity anchors ─
    "id",
    "title",
    # ─ content: what is this work? (Aaron's preferred top-of-modal) ─
    "description",
    "acceptance_criteria",
    "deps",
    "dependencies",
    "dependents",
    "notes",
    # ─ state & meta ─
    "issue_type",
    "status",
    "priority",
    "assignee",
    "owner",
    "created_by",
    "created_at",
    "started_at",
    "updated_at",
    "closed_at",
    "close_reason",
    "parent",
    "labels",
    "external_ref",
    "estimate",
    "story_points",
    "dependency_count",
    "dependent_count",
    "comment_count",
    # ─ bulk content (conversation log lives at the bottom) ─
    "comments",
    "metadata",
]

_HIDDEN = {"_type"}  # bd internal

# Field-kind classification for the modal renderer. Keeps the template
# stupid (just dispatches on the kind string) and the smarts here in Python
# where they belong. Adding a new kind is one entry here + one branch in
# the template — no logic creep across files.
_KIND_CHIPS = {"labels", "tags"}
_KIND_DEPS = {"deps", "dependencies", "dependents"}
_KIND_COMMENTS = {"comments"}
# Fields whose string value is markdown prose. Rendered through md.render
# and inserted via |safe in the template. close_reason and acceptance_criteria
# are short prose that still benefit from inline link / emphasis support.
_KIND_MARKDOWN = {"description", "notes", "close_reason", "acceptance_criteria"}


def _classify_field(key: str, val: Any) -> str:
    """Pick a render kind for a (key, value) pair. The template uses this
    to choose between chips / deps-list / paragraph / scalar / json."""
    if val is None or val == [] or val == {} or val == "":
        return "empty"
    if key in _KIND_CHIPS and isinstance(val, list):
        return "chips"
    if key in _KIND_DEPS and isinstance(val, list):
        return "deps"
    if key in _KIND_COMMENTS and isinstance(val, list):
        return "comments"
    if key in _KIND_MARKDOWN and isinstance(val, str):
        return "markdown"
    if isinstance(val, (dict, list)):
        return "json"
    return "scalar"


def _ordered_fields(bead: dict[str, Any]) -> list[dict[str, Any]]:
    """Return field rows in display order, exposing every non-hidden bd field
    so v0 ships with zero 'oh that's not shown' surprises. Each row carries
    a 'kind' so the template can dispatch on render style."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for k in _FIELD_ORDER:
        if k in bead and k not in _HIDDEN:
            out.append({"key": k, "val": bead[k], "kind": _classify_field(k, bead[k])})
            seen.add(k)
    for k in sorted(bead.keys()):
        if k in seen or k in _HIDDEN:
            continue
        out.append({"key": k, "val": bead[k], "kind": _classify_field(k, bead[k])})
    return out


def _shape_audit(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Diff consecutive history snapshots into human-readable change rows.

    bd's underlying dolt commits include no-op rewrites (auto-export re-
    serializing the same content); those produce empty diffs and would
    otherwise spam the audit panel with N identical '(initial)' rows.
    We skip them — same trick bcc uses in its audit handler.

    The oldest entry (last in the list, since bd history returns descending)
    is always shown as 'created' regardless of diff, so the audit has a
    legitimate origin row.
    """
    rows: list[dict[str, Any]] = []
    n = len(entries)
    for i, hist in enumerate(entries):
        issue = hist.get("Issue") or {}
        is_oldest = (i == n - 1)
        if is_oldest:
            what = "created"
        else:
            prev_issue = entries[i + 1].get("Issue") or {}
            what = _diff_issue(prev_issue, issue)
            if not what:
                continue  # no-op dolt commit, skip
        rows.append(
            {
                "when": hist.get("CommitDate"),
                "who": hist.get("Committer") or "—",
                "what": what,
                "commit": (hist.get("CommitHash") or "")[:8],
            }
        )
    return rows


def _diff_issue(old: dict[str, Any], new: dict[str, Any]) -> str:
    """Field-by-field diff with old→new values for high-signal keys.
    Returns a comma-separated change summary, or '' if no changes."""
    changes: list[str] = []
    keys = set(old.keys()) | set(new.keys())
    # updated_at always changes; skip it. _type is internal.
    skip = {"updated_at"} | _HIDDEN
    for k in sorted(keys):
        if k in skip:
            continue
        ov, nv = old.get(k), new.get(k)
        if ov == nv:
            continue
        if k in ("status", "priority", "assignee"):
            changes.append(f"{k}: {_short(ov)} → {_short(nv)}")
        elif ov is None:
            changes.append(f"set {k}")
        elif nv is None:
            changes.append(f"cleared {k}")
        else:
            changes.append(f"changed {k}")
    return ", ".join(changes)


def _short(v: Any) -> str:
    """Short representation of a value for the audit diff summary."""
    if v is None:
        return "∅"
    s = str(v)
    return s if len(s) <= 40 else s[:37] + "…"
