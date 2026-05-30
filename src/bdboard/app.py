"""FastAPI application — composes routes over BdClient + Store + derive."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Header, HTTPException, Request
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


def _dep_label(dep_type: str | None, direction: str) -> str:
    """Return the correct dependency label based on type and direction.

    Args:
        dep_type: The dependency type (blocks, related, parent-child, etc.)
        direction: Either 'dependencies' (inbound) or 'dependents' (outbound)

    Returns:
        Human-readable label for the relationship from this bead's perspective.

    Examples:
        _dep_label('blocks', 'dependencies') → 'blocked by'
        _dep_label('blocks', 'dependents') → 'blocks'
        _dep_label('related', 'dependencies') → 'related'
        _dep_label('parent-child', 'dependents') → 'parent of'
    """
    dep_type = (dep_type or "related").lower()
    is_inbound = direction == "dependencies"

    # Map each type to (inbound_label, outbound_label)
    label_map = {
        "blocks": ("blocked by", "blocks"),
        "related": ("related", "related"),
        "relates-to": ("related", "related"),
        "parent-child": ("child of", "parent of"),
        "discovered-from": ("discovered from", "discovered"),
        "validates": ("validated by", "validates"),
        "caused-by": ("caused by", "causes"),
        "tracks": ("tracked by", "tracks"),
        "supersedes": ("superseded by", "supersedes"),
        "until": ("until", "until"),
    }

    inbound_label, outbound_label = label_map.get(
        dep_type,
        (dep_type, dep_type),  # fallback: show raw type
    )
    return inbound_label if is_inbound else outbound_label


TEMPLATES = Jinja2Templates(directory=str(_PKG_DIR / "templates"))
TEMPLATES.env.filters["humanize_ts"] = derive.humanize_ts
TEMPLATES.env.filters["humanize_hours"] = derive.humanize_hours
# md filter: renders markdown to HTML. Marked safe via Jinja's |safe in the
# template so we don't double-escape. Source content is bd-authored prose
# and the renderer has html=False, so script-injection is not possible.
TEMPLATES.env.filters["md"] = md.render
TEMPLATES.env.filters["dep_label"] = _dep_label
# Footer + masthead always have access to these.
TEMPLATES.env.globals["version"] = __version__
# Cache-bust query param for /static assets. Every server restart gets a
# fresh value — means no more 'why is my CSS old?' moments during dev,
# and zero cost in prod (HTTP caches see a new URL only on redeploy).
TEMPLATES.env.globals["asset_v"] = str(int(time.time()))

# ----- CSRF protection -----
# bdboard introduces its first write paths in bdboard-12f.3 (memory curate).
# CSRF posture: a per-process token generated at startup, included in all
# mutation forms via a hidden input, and validated on POST/DELETE. This is
# minimal-but-sufficient for a single-user localhost dashboard:
# - No cookie auth (no session hijacking vector), but we still guard against
#   accidental or malicious cross-origin form submission.
# - Token persists for the process lifetime — simple, no DB, no expiry logic.
# - HTMX posts include the token via hx-vals or hidden inputs; we check the
#   X-CSRF-Token header OR the _csrf form field.
_CSRF_TOKEN = secrets.token_urlsafe(32)
TEMPLATES.env.globals["csrf_token"] = _CSRF_TOKEN

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
    epic_lane = derive.epic_lane(await _hydrate_epic_dependencies(beads))
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        {
            "workspace": _WORKSPACE.name,
            "workspace_path": str(_WORKSPACE),
            "active": "board",
            "counts": derive.counts(beads),
            "epic_lane": epic_lane,
            "lanes": derive.lanes(beads),
            "activity": derive.activity(beads),
        },
    )


# ----- HTMX partials (polled every few seconds by the dashboard) -----


@app.get("/memory", response_class=HTMLResponse)
async def page_memory(request: Request) -> HTMLResponse:
    """Full-page memory view, symmetric with the dashboard index at `/`.

    Extends base.html and renders the search strip + list region; the list
    region itself is filled by an HTMX `load` fetch to /api/memory (and
    re-swapped on debounced search), so this route stays trivially cheap
    and never blocks on a bd subprocess. We still surface the workspace
    validation error here for parity with `/` so a broken workspace fails
    visibly rather than rendering an empty memory page.
    """
    err = _validate_or_warn()
    if err:
        return TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {"error": err, "workspace": str(_WORKSPACE)},
            status_code=500,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "memory.html",
        {
            "workspace": _WORKSPACE.name,
            "workspace_path": str(_WORKSPACE),
            "active": "memory",
        },
    )


@app.get("/history", response_class=HTMLResponse)
async def page_history(request: Request) -> HTMLResponse:
    """Full-page History view, symmetric with `/` and `/memory` (design §D4).

    Extends base.html and renders the masthead (with the History nav entry
    active) plus the #history-region swap target; that region is filled by an
    HTMX `load` fetch to /api/history and re-fetched on `refresh from:body`
    (the existing SSE pipeline, design §D7), so this route stays trivially
    cheap and never blocks on a bd subprocess. We surface the workspace
    validation error here for parity with `/` and `/memory` so a broken
    workspace fails visibly rather than rendering an empty history page.
    """
    err = _validate_or_warn()
    if err:
        return TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {"error": err, "workspace": str(_WORKSPACE)},
            status_code=500,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "history.html",
        {
            "workspace": _WORKSPACE.name,
            "workspace_path": str(_WORKSPACE),
            "active": "history",
        },
    )


@app.get("/api/lanes", response_class=HTMLResponse)
async def api_lanes(request: Request) -> HTMLResponse:
    """Renders the swim lanes including the Activity column. Activity ships
    inside the same partial (and the same /api/lanes refresh) because it's
    now a regular lane — no separate sidebar, no separate endpoint."""
    beads = await store.snapshot()
    epic_lane = derive.epic_lane(await _hydrate_epic_dependencies(beads))
    return TEMPLATES.TemplateResponse(
        request,
        "partials/lanes.html",
        {
            "epic_lane": epic_lane,
            "lanes": derive.lanes(beads),
            "activity": derive.activity(beads),
        },
    )


@app.get("/api/history", response_class=HTMLResponse)
async def api_history(
    request: Request,
    range: str = derive.DEFAULT_HISTORY_RANGE,
    page: int = 1,
    page_size: int | None = None,
) -> HTMLResponse:
    """Render the History swap region (HTMX target), symmetric with /api/lanes.

    Pure derivation over the existing snapshot (design §4): no new bd call.
    ``range`` selects the window (7d/30d/90d/all, default 30d; unknown values
    degrade to the default inside derive). ``page`` drives server-side
    pagination of the closed list (design §D5). ``page_size`` (bdboard-3jj)
    is clamped to the allowed set {25,50,100}, defaulting to 50 on a
    missing/invalid value so a bad query param can never break paging. We
    compute the views from one snapshot — the paginated closed list plus the
    throughput-per-day and created-per-day series — and hand them to
    partials/history.html.
    """
    beads = await store.snapshot()
    # Normalise the range once so the template's active-state cues and the
    # derive calls agree on the same key (a bad ?range= degrades to default).
    range_key = (range or "").strip().lower()
    if range_key not in derive.HISTORY_RANGES:
        range_key = derive.DEFAULT_HISTORY_RANGE
    page = max(1, page)
    # Clamp page_size to the allowed set; missing/invalid -> default 50.
    size = derive.clamp_page_size(page_size)
    window = derive.history_window(
        beads, range_key=range_key, page=page, page_size=size
    )
    series = derive.throughput(beads, range_key=range_key)
    # Beads created per day (bdboard-5t5): day-bucketed by created_at,
    # complementing the closed-by-closed_at throughput series. Range-scoped
    # the same way so both charts read against the same window.
    created_series = derive.created(beads, range_key=range_key)
    peak = max((d["count"] for d in series), default=0)
    created_peak = max((d["count"] for d in created_series), default=0)
    created_total = sum(d["count"] for d in created_series)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/history.html",
        {
            "range_key": range_key,
            "ranges": list(derive.HISTORY_RANGES.keys()),
            "page_size": size,
            "page_sizes": list(derive.HISTORY_PAGE_SIZES),
            "window": window,
            "series": series,
            "peak": peak,
            "created_series": created_series,
            "created_peak": created_peak,
            "created_total": created_total,
        },
    )


@app.get("/api/memory", response_class=HTMLResponse)
async def api_memory(request: Request, q: str = "") -> HTMLResponse:
    """Render the memory list region (HTMX swap target), symmetric with
    /api/lanes. Server-side search via Bd.memories(q): an empty q lists
    all memories. Bodies render through the shared `md` Jinja filter; keys
    are shown as monospace headings. On a bd failure we degrade to a
    friendly inline message rather than 500-ing the partial swap.
    """
    term = q.strip()
    try:
        memories = await bd.memories(term)
    except RuntimeError as err:
        log.warning("bd memories failed: %s", err)
        return HTMLResponse(
            (
                '<p class="memory-empty muted" role="status" aria-live="polite">'
                "Couldn\u2019t load memories right now. "
                "Please try again in a moment."
                "</p>"
            ),
            status_code=200,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "partials/memory_list.html",
        {"memories": memories, "query": term},
    )


# ----- memory mutations (remember / forget) -----


def _check_csrf(
    csrf_header: str | None = None,
    csrf_form: str | None = None,
) -> None:
    """Validate CSRF token from header or form field.

    Raises HTTPException 403 if neither matches. HTMX sends the header
    via hx-headers; fallback form field supports non-JS form posts.
    """
    if csrf_header == _CSRF_TOKEN or csrf_form == _CSRF_TOKEN:
        return
    raise HTTPException(
        status_code=403,
        detail="Invalid or missing CSRF token. Please refresh the page and try again.",
    )


@app.post("/api/memory", response_class=HTMLResponse)
async def api_memory_create(
    request: Request,
    key: str = Form(...),
    body: str = Form(...),
    csrf: str = Form(None, alias="csrf_token"),
    x_csrf_token: str | None = Header(None),
) -> HTMLResponse:
    """Create or update a memory via `bd remember`.

    Upsert semantics: if the key exists, its body is replaced; if not, a
    new memory is created. After mutation we re-render the full memory
    list so the HTMX swap shows the updated state immediately (optimistic
    refresh). The watcher will also fire an SSE event, but this ensures
    the acting user sees their change without waiting for debounce.
    """
    _check_csrf(x_csrf_token, csrf)
    key = key.strip()
    body_text = body.strip()
    if not key:
        return HTMLResponse(
            '<p class="memory-error" role="alert">Key cannot be empty.</p>',
            status_code=400,
        )
    if not body_text:
        return HTMLResponse(
            '<p class="memory-error" role="alert">Body cannot be empty.</p>',
            status_code=400,
        )
    try:
        await bd.remember(key, body_text)
    except RuntimeError as err:
        log.warning("bd remember failed: %s", err)
        return HTMLResponse(
            f'<p class="memory-error" role="alert">Could not save: {err}</p>',
            status_code=500,
        )
    # Broadcast SSE so other tabs/clients refresh too.
    await bus.broadcast("beads_changed")
    # Return fresh list for swap.
    memories = await bd.memories()
    return TEMPLATES.TemplateResponse(
        request,
        "partials/memory_list.html",
        {"memories": memories, "query": ""},
    )


@app.delete("/api/memory/{key:path}", response_class=HTMLResponse)
async def api_memory_delete(
    request: Request,
    key: str,
    x_csrf_token: str | None = Header(None),
) -> HTMLResponse:
    """Delete a memory via `bd forget`.

    The key is path-encoded so keys with slashes work. After deletion we
    re-render the list so the HTMX swap shows the updated state. Callers
    should confirm before invoking (UI implements confirm-before-forget).
    """
    _check_csrf(x_csrf_token, None)
    key = key.strip()
    if not key:
        return HTMLResponse(
            '<p class="memory-error" role="alert">Key cannot be empty.</p>',
            status_code=400,
        )
    try:
        await bd.forget(key)
    except RuntimeError as err:
        log.warning("bd forget failed: %s", err)
        return HTMLResponse(
            f'<p class="memory-error" role="alert">Could not delete: {err}</p>',
            status_code=500,
        )
    await bus.broadcast("beads_changed")
    memories = await bd.memories()
    return TEMPLATES.TemplateResponse(
        request,
        "partials/memory_list.html",
        {"memories": memories, "query": ""},
    )


@app.get("/api/counts", response_class=HTMLResponse)
async def api_counts(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "partials/counts.html",
        {"counts": derive.counts(await store.snapshot())},
    )


# ----- bead detail -----


@app.get("/api/bead/{bead_id}", response_class=HTMLResponse)
async def api_bead(request: Request, bead_id: str) -> HTMLResponse:
    """Render bead detail.

    Prefer `bd show --long --json` for full fields. If that call fails,
    fall back to the cached list snapshot so the modal still renders useful
    content instead of hard-failing.
    """
    full, err = await bd.show_long(bead_id)
    bead: dict[str, Any] | None = full
    source = "Live details"
    if bead is None:
        # Ensure the snapshot is populated for the fallback lookup.
        await store.snapshot()
        bead = store.bead(bead_id)
        source = "Cached snapshot"
    if bead is None:
        return HTMLResponse(
            (
                "<div class='modal-error'>"
                "We couldn’t find that bead. "
                "Please refresh the board and try again."
                "</div>"
            ),
            status_code=404,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "partials/bead_modal.html",
        {
            "bead": bead,
            "fields": _ordered_fields(bead),
            "source": source,
            "warning": (
                "Showing cached details while live data is temporarily unavailable."
                if full is None and err
                else None
            ),
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
            {"entries": None, "timeline": None, "error": err},
        )
    rendered = _shape_audit(entries)
    # Deferred bead E (bdboard-7r8): the per-bead status-transition timeline
    # is derived from the SAME history payload we just fetched, so the
    # lifecycle view costs no extra `bd history` subprocess call.
    timeline = derive.status_timeline(entries)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/bead_audit.html",
        {"entries": rendered, "timeline": timeline, "error": None},
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


async def _hydrate_epic_dependencies(
    beads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich epics with dependency edges for sequencing.

    `bd list` omits expanded dependency arrays; fetch per-epic long view and
    graft only the dependency fields we need, preserving the original snapshot
    for everything else.
    """
    enriched = [dict(b) for b in beads]
    epics = [b for b in enriched if (b.get("issue_type") or "").lower() == "epic"]
    if not epics:
        return enriched

    async def _load(epic: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        bead_id = epic.get("id")
        if not bead_id:
            return "", None
        full, _err = await bd.show_long(bead_id)
        return bead_id, full

    rows = await asyncio.gather(*(_load(epic) for epic in epics))
    by_id = {bead_id: full for bead_id, full in rows if bead_id and full}
    for epic in enriched:
        bead_id = epic.get("id")
        full = by_id.get(bead_id)
        if not full:
            continue
        # Use helper to normalize dependency field access
        dep_list = derive.get_dependency_list(full)
        if dep_list:
            epic["dependencies"] = dep_list
        # Also preserve dependency_count if present
        if "dependency_count" in full:
            epic["dependency_count"] = full["dependency_count"]
    return enriched


# Field display order in the modal: identity anchors first, then
# content (what does this work entail?), then state/meta, then bulk
# diagnostic fields at the bottom. Anything not listed is appended
# alphabetically so we never silently hide new bd fields.
_FIELD_ORDER = [
    # ─ identity anchors ─
    "id",
    "title",
    # ─ content: what is this work? ─
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

# Short scalar-ish metadata fields that benefit from a compact two-column
# layout in the modal (less vertical churn, faster scanning).
_SHORT_META_FIELDS = {
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
    "parent",
    "external_ref",
    "estimate",
    "story_points",
    "dependency_count",
    "dependent_count",
    "comment_count",
}


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


def _is_short_meta_field(key: str, kind: str) -> bool:
    """Whether this field should render in the compact half-width metadata grid."""
    if key not in _SHORT_META_FIELDS:
        return False
    return kind in {"scalar", "empty", "chips"}


def _ordered_fields(bead: dict[str, Any]) -> list[dict[str, Any]]:
    """Return field rows in display order, exposing every non-hidden bd field.

    Each row carries render hints so the template can stay mostly declarative.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for k in _FIELD_ORDER:
        if k in bead and k not in _HIDDEN:
            kind = _classify_field(k, bead[k])
            out.append(
                {
                    "key": k,
                    "val": bead[k],
                    "kind": kind,
                    "short_meta": _is_short_meta_field(k, kind),
                }
            )
            seen.add(k)
    for k in sorted(bead.keys()):
        if k in seen or k in _HIDDEN:
            continue
        kind = _classify_field(k, bead[k])
        out.append(
            {
                "key": k,
                "val": bead[k],
                "kind": kind,
                "short_meta": _is_short_meta_field(k, kind),
            }
        )
    return out


def _shape_audit(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Diff consecutive history snapshots into human-readable change rows.

    bd's underlying dolt commits include no-op rewrites (auto-export re-
    serializing the same content); those produce empty diffs and would
    otherwise spam the audit panel with repeated no-op rows.
    We skip them for signal-to-noise quality.

    The oldest entry (last in the list, since bd history returns descending)
    is always shown as 'created' regardless of diff, so the audit has a
    legitimate origin row.
    """
    rows: list[dict[str, Any]] = []
    n = len(entries)
    for i, hist in enumerate(entries):
        issue = hist.get("Issue") or {}
        is_oldest = i == n - 1
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
