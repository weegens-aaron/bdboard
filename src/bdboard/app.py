"""FastAPI application — composes routes over BdClient + Store + derive."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from watchfiles import awatch

from bdboard import derive, md
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
# Cache-bust query param for /static assets. Every server restart gets a
# fresh value — means no more 'why is my CSS old?' moments during dev,
# and zero cost in prod (HTTP caches see a new URL only on redeploy).
TEMPLATES.env.globals["asset_v"] = str(int(time.time()))

# ----- CSRF protection -----
# bdboard introduces its first write paths with the memory-curate feature.
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

# Optional actor override for the audit trail on manual field edits. When unset
# bd falls back to $BEADS_ACTOR / git user.name / $USER, so this is just a way
# to force a human-edit attribution distinct from any agent identity that may
# also be writing to the same workspace (auditability).
_ACTOR = os.environ.get("BDBOARD_ACTOR") or None

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
    """React to bd writes inside .beads/ (dolt files included).

    Implementation mirrors mantoni/beads-ui server/watcher.js: a trailing
    debounce window absorbs burst-writes from one logical bd command;
    a cooldown after each refresh prevents back-to-back refreshes from
    sustained activity.

    Watch scope: we watch a SMALL, fixed set of directories
    NON-recursively (bd.watch_targets() — the per-db dolt noms/ dirs plus
    .beads/ itself) instead of the whole .beads/ tree recursively. The
    recursive whole-tree watch opened one kqueue fd per directory on macOS
    and, with dolt's churning noms/ object store, exhausted RLIMIT_NOFILE
    — which then broke `bd list --json` and `bd show` subprocess spawning
    (OSError [Errno 24] Too many open files). Every meaningful bd write
    still touches manifest/journal.idx in a noms/ dir, so we keep
    sub-second latency without the fd blowup.
    """
    while True:
        try:
            targets = bd.watch_targets()
            if not targets:
                # .beads dir not there yet — wait and retry
                await asyncio.sleep(2)
                continue
            log.info(
                "watcher observing %d target(s) (non-recursive): %s",
                len(targets),
                ", ".join(str(t) for t in targets),
            )
            # watchfiles.awatch yields a batch (set of (change, path))
            # roughly every 50ms of FS activity — it already does light
            # batching for us. Our debounce sits on top of that to collapse
            # multi-batch bursts (a bd update often spans 2-3 batches).
            async for _changes in awatch(*targets, recursive=False):
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
                except TimeoutError:
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
    """Full-page board view — a cheap, non-blocking shell.

    Previously this route awaited ``store.snapshot()`` AND a per-epic
    ``bd show`` hydration pass before returning ANY HTML, so the board
    froze on the bd CLI before painting a single pixel — the worst TTFP
    of the three pages. It is now symmetric with /memory and /history:
    render base.html + skeleton placeholders instantly, then hydrate the
    counts strip and swim lanes via HTMX `load` fetches to /api/counts and
    /api/lanes (which keep the snapshot + epic-hydration cost). The result
    is an immediate paint with shimmer affordances, no blank screen, and
    no layout jump when real data arrives. We still surface the workspace
    validation error here (parity with /memory and /history) so a broken
    workspace fails visibly rather than rendering an empty board.
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
        "dashboard.html",
        {
            "workspace": _WORKSPACE.name,
            "workspace_path": str(_WORKSPACE),
            "active": "board",
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
    from_date: str | None = None,
    to_date: str | None = None,
) -> HTMLResponse:
    """Render the History swap region (HTMX target), symmetric with /api/lanes.

    Pure derivation over the existing snapshot (design §4): no new bd call.
    ``range`` selects the window (7d/30d/90d/all, default 30d; unknown values
    degrade to the default inside derive). ``page`` drives server-side
    pagination of the closed list (design §D5). ``page_size``
    is clamped to the allowed set {25,50,100}, defaulting to 50 on a
    missing/invalid value so a bad query param can never break paging. We
    compute the views from one snapshot — the paginated closed list plus the
    throughput-per-day and created-per-day series — and hand them to
    partials/history.html.

    ``from_date``/``to_date`` (``YYYY-MM-DD``) carry an explicit custom
    window. When either parses, it supersedes ``range=`` for
    every series, the closed list, and the KPIs (the derive layer resolves
    the precedence in one place via :func:`derive._resolve_bounds`); the
    range control marks the synthetic ``custom`` preset active so the UI
    reflects the custom selection after each HTMX swap.
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
    # Custom date window. Resolve the bounds once so we know
    # whether a valid custom selection is active; if so the template's range
    # control highlights the synthetic 'custom' option instead of a preset.
    custom_lo, custom_hi = derive.custom_bounds(from_date, to_date)
    is_custom = custom_lo is not None or custom_hi is not None
    active_range = "custom" if is_custom else range_key
    window = derive.history_window(
        beads,
        range_key=range_key,
        page=page,
        page_size=size,
        from_date=from_date,
        to_date=to_date,
    )
    series = derive.throughput(beads, range_key=range_key, from_date=from_date, to_date=to_date)
    stats = derive.lead_time_stats(beads, range_key=range_key, from_date=from_date, to_date=to_date)
    # Beads created per day: day-bucketed by created_at. The
    # standalone series is no longer charted on its own (it was merged
    # into the combined chart), but we still tally it for the legend's
    # range-scoped 'Created' count.
    created_series = derive.created(
        beads, range_key=range_key, from_date=from_date, to_date=to_date
    )
    # Combined created+closed series: created and closed counts
    # zipped onto ONE continuous timeline so the History page renders a single
    # grouped-bar chart instead of two stacked strips, making created-vs-closed
    # throughput (net flow / backlog burn) readable at a glance. Range/custom
    # window semantics match the sibling series exactly.
    combined_series = derive.combined(
        beads, range_key=range_key, from_date=from_date, to_date=to_date
    )
    created_total = sum(d["count"] for d in created_series)
    # Shared y-axis peak for the combined chart so created and closed bars are
    # scaled against the SAME maximum and stay visually comparable per day.
    combined_peak = max((max(d["created"], d["closed"]) for d in combined_series), default=0)
    avg_per_day = round(stats["n"] / len(series), 1) if series else 0
    # Optional headline KPI (design §6, bead F): bd's own aggregate summary
    # (incl. average_lead_time_hours). These are workspace-global, point-in-
    # time totals — NOT range-scoped — so we surface them as a distinct
    # "via bd" headline in the masthead stats strip. It's pure sugar:
    # status_summary() returns None on any bd hiccup and the template simply
    # omits the headline cells, leaving the range-derived KPIs as the primary
    # surface so the masthead degrades gracefully when bd is unavailable.
    bd_summary = await store.bd.status_summary()
    return TEMPLATES.TemplateResponse(
        request,
        "partials/history.html",
        {
            "range_key": range_key,
            "active_range": active_range,
            "is_custom": is_custom,
            "from_date": from_date or "",
            "to_date": to_date or "",
            "ranges": list(derive.HISTORY_RANGES.keys()),
            "page_size": size,
            "page_sizes": list(derive.HISTORY_PAGE_SIZES),
            "window": window,
            "created_total": created_total,
            "combined_series": combined_series,
            "combined_peak": combined_peak,
            "stats": stats,
            "avg_per_day": avg_per_day,
            "bd_summary": bd_summary,
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


# ----- formula pour -----


def _short_pour_id(new_epic_id: str) -> str:
    """Derive the short, human-readable disambiguator for the pour's title.

    bd already mints globally-unique bead ids (e.g. ``...-mol-u72``), so the
    title just needs a token that distinguishes two pours of the SAME formula
    on the board. Reusing the suffix bd already assigned to ``new_epic_id``
    (the segment after the last ``-``) is the lowest-risk, zero-new-entropy
    option and is already collision-free. Falls back
    to the whole id if there is no ``-`` to split on.
    """
    suffix = new_epic_id.rsplit("-", 1)[-1]
    return suffix or new_epic_id


def _pour_counts(result: dict[str, Any]) -> tuple[int, int, bool]:
    """Reconcile what bd *created* with what the board will actually *show*.

    bd's ``created`` counts every node it materialized, INCLUDING the molecule
    wrapper that bdboard deliberately hides from the board (Option A).
    Reporting the raw ``created`` therefore over-counts by one
    and tells the user '6 beads added' when only 5 are ever visible — a
    count-honesty bug.

    We also guard against *partial* materialization. ``id_mapping`` maps every
    step (plus the wrapper) to a real bead id, so a healthy pour has
    ``len(id_mapping) == created``. A mismatch means not every node landed
    (a bd-layer vapor-pour regression, or a formula that lost its top-level
    ``pour: true``) — exactly the failure mode that used to leave empty
    wrapper epics accumulating while the UI still cried success. We surface it
    instead of masking it.

    Returns ``(visible_count, created, fully_materialized)``:
      - ``visible_count`` = beads the board will show (``created`` minus the
        one hidden wrapper, floored at 0).
      - ``created`` = bd's raw node count (echoed for diagnostics).
      - ``fully_materialized`` = whether every reported node has a real id.
    """
    created = int(result.get("created", 0) or 0)
    id_mapping = result.get("id_mapping")
    mapped = len(id_mapping) if isinstance(id_mapping, dict) else 0
    # Healthy pour: id_mapping has an entry per created node. If id_mapping is
    # absent we can't prove a shortfall, so we don't cry wolf (treat as full).
    fully_materialized = mapped == created if isinstance(id_mapping, dict) else True
    # One hidden wrapper, but never report a negative count.
    visible_count = max(created - 1, 0)
    return visible_count, created, fully_materialized


@app.get("/api/formulas", response_class=HTMLResponse)
async def api_formulas(request: Request) -> HTMLResponse:
    """Render the formula picker (HTMX swap target).

    Lists formulas via ``bd formula list --json`` (name + description). On a
    bd failure we degrade to a friendly inline message rather than 500-ing
    the partial swap — symmetric with /api/memory.
    """
    try:
        formulas = await bd.list_formulas()
    except RuntimeError as err:
        log.warning("bd formula list failed: %s", err)
        return HTMLResponse(
            (
                '<p class="formula-empty muted" role="status" aria-live="polite">'
                "Couldn\u2019t load formulas right now. "
                "Please try again in a moment."
                "</p>"
            ),
            status_code=200,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "partials/formula_list.html",
        {"formulas": formulas},
    )


@app.get("/api/formulas/{name}/form", response_class=HTMLResponse)
async def api_formula_form(request: Request, name: str) -> HTMLResponse:
    """Render the variable form for one formula (HTMX swap target).

    Variables are read by PARSING the ``*.formula.json`` file directly (path
    from ``source`` in ``formula list --json``) — NOT from
    ``formula show --json`` (omits variables) nor the ``vars`` count (always
    0). See the bd CLI formula gotchas documented in docs/design/.

    One field per variable: ``description`` is the label/help, ``default`` is
    the prefilled value, and no-default variables are marked ``required`` so
    the pour button pre-flight (§4.4) blocks until they are filled.
    """
    try:
        formulas = await bd.list_formulas()
    except RuntimeError as err:
        log.warning("bd formula list failed: %s", err)
        return HTMLResponse(
            '<p class="formula-error" role="alert">Couldn\u2019t load that '
            "formula right now. Please try again.</p>",
            status_code=200,
        )
    match = next((f for f in formulas if f.get("name") == name), None)
    if match is None:
        return HTMLResponse(
            '<p class="formula-error" role="alert">No such formula.</p>',
            status_code=404,
        )
    source = match.get("source") or ""
    try:
        variables = bd.read_formula_variables(source)
    except RuntimeError as err:
        log.warning("read_formula_variables(%s) failed: %s", source, err)
        return HTMLResponse(
            '<p class="formula-error" role="alert">Couldn\u2019t read this '
            "formula\u2019s variables. Please try again.</p>",
            status_code=200,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "partials/formula_form.html",
        {
            "name": name,
            "description": match.get("description") or "",
            "variables": variables,
        },
    )


@app.post("/api/formulas/{name}/pour", response_class=HTMLResponse)
async def api_formula_pour(
    request: Request,
    name: str,
    csrf: str = Form(None, alias="csrf_token"),
    x_csrf_token: str | None = Header(None),
) -> HTMLResponse:
    """Pour a formula onto the board (CSRF-checked write path).

    Flow:
      1. CSRF guard (same posture as memory/field writes).
      2. Pre-flight: re-read the formula's variables and block the pour until
         every required (no-default) variable is filled. We collect the
         submitted form values, falling back to each variable's default when
         the field was left blank. This is the server-side mirror of the
         form's ``required`` attribute (§4.4) — a crafted POST can't skip it.
      3. Pour via ``bd mol pour ... --json``. bd's stderr is still surfaced on
         failure because ``--dry-run`` can't catch every pour-blocking bug
         (§4.2) — pre-flight is necessary but not sufficient.
      4. Rename the grouping node (``new_epic_id``) to ``<formula> <id>`` so
         two pours of the same formula are distinguishable on the board.
      5. Optimistic ``bus.broadcast('beads_changed')`` so the acting tab
         refreshes immediately; the watcher→Store.refresh→SSE pipeline also
         fires for other tabs.
    """
    _check_csrf(x_csrf_token, csrf)
    name = name.strip()
    # Resolve the formula + its declared variables so we can pre-flight and
    # only forward vars we actually parsed (unknown --var is silently ignored
    # by bd anyway, §4.4).
    try:
        formulas = await bd.list_formulas()
    except RuntimeError as err:
        log.warning("bd formula list failed during pour: %s", err)
        return HTMLResponse(
            '<p class="formula-error" role="alert">Couldn\u2019t load the '
            "formula. Please try again.</p>",
            status_code=500,
        )
    match = next((f for f in formulas if f.get("name") == name), None)
    if match is None:
        return HTMLResponse(
            '<p class="formula-error" role="alert">No such formula.</p>',
            status_code=404,
        )
    try:
        declared = bd.read_formula_variables(match.get("source") or "")
    except RuntimeError as err:
        log.warning("read_formula_variables failed during pour: %s", err)
        return HTMLResponse(
            '<p class="formula-error" role="alert">Couldn\u2019t read this '
            "formula\u2019s variables. Please try again.</p>",
            status_code=500,
        )
    form = await request.form()
    submitted: dict[str, str] = {}
    missing: list[str] = []
    for var in declared:
        var_name = var["name"]
        raw = form.get(f"var_{var_name}")
        value = (raw if isinstance(raw, str) else "").strip()
        if not value and var.get("default") is not None:
            value = str(var["default"])
        if not value and var.get("required"):
            missing.append(var_name)
        if value:
            submitted[var_name] = value
    # Pre-flight: block until required vars are filled (§4.4).
    if missing:
        names = ", ".join(missing)
        return HTMLResponse(
            f'<p class="formula-error" role="alert">Please fill required variable(s): {names}.</p>',
            status_code=400,
        )
    try:
        result = await bd.pour_formula(name, submitted)
    except RuntimeError as err:
        # Surface bd's real stderr — --dry-run can't catch every pour-blocker.
        log.warning("bd mol pour %s failed: %s", name, err)
        return HTMLResponse(
            f'<p class="formula-error" role="alert">Pour failed: {err}</p>',
            status_code=500,
        )
    # Rename the grouping node to '<formula> <id>' so repeat pours are
    # distinguishable. Best-effort: a rename failure must NOT lose the (atomic,
    # successful) pour — the beads are already on the board, just under the bare
    # formula name. Surface a soft warning rather than a hard error.
    new_epic_id = result.get("new_epic_id")
    rename_warning = ""
    if new_epic_id:
        title = f"{name} {_short_pour_id(new_epic_id)}"
        try:
            await bd.rename_bead(new_epic_id, title)
        except RuntimeError as err:
            log.warning("pour rename of %s failed: %s", new_epic_id, err)
            rename_warning = (
                " (poured, but couldn\u2019t rename the grouping node — "
                "it will show under the bare formula name)."
            )
    # Reconcile bd's raw node count with what the board will actually show:
    # the molecule wrapper is hidden (so visible == created - 1), and a
    # shortfall between id_mapping and created means a partial materialization
    # we must NOT report as a clean success.
    visible_count, created, fully_materialized = _pour_counts(result)
    # Optimistic SSE so the acting tab refreshes immediately; the watcher
    # pipeline also fires for everyone else.
    await bus.broadcast("beads_changed")
    if not fully_materialized:
        log.warning(
            "pour of %s under-materialized: created=%s but id_mapping has %s entries",
            name,
            created,
            len(result.get("id_mapping") or {}),
        )
    return TEMPLATES.TemplateResponse(
        request,
        "partials/formula_pour_result.html",
        {
            "name": name,
            "created": visible_count,
            "rename_warning": rename_warning,
            "fully_materialized": fully_materialized,
        },
    )


# ----- field edits (manual value editing) -----


@app.post("/api/bead/{bead_id}/field", response_class=HTMLResponse)
async def api_bead_field_update(
    request: Request,
    bead_id: str,
    field: str = Form(...),
    value: str = Form(""),
    expected_updated_at: str = Form("", alias="expected_updated_at"),
    csrf: str = Form(None, alias="csrf_token"),
    x_csrf_token: str | None = Header(None),
) -> HTMLResponse:
    """Edit one bead field VALUE via `bd update`, return the re-rendered row.

    The write half of manual field editing. Reuses the exact
    remember/forget plumbing: CSRF guard,
    serialized bd mutation, SSE broadcast, optimistic re-render.

    Safety: the `field` name is validated against _FIELD_REGISTRY and rejected
    unless it is explicitly `editable`. Read-only is the default for anything
    not whitelisted, so non-editable / shape / lifecycle / immutable fields
    (status, parent, id, story_points, timestamps, ...) can never be written
    here even if a crafted request asks for them. The registry's `flag` is the
    ONLY flag passed to bd — we never let the client choose the flag.

    Concurrency (multi-writer races): the
    _subprocess_gate serializes the *writes*, but a stale form posted from
    one tab can clobber a concurrent edit made from another tab (or by an
    agent) — last-write-wins. To prevent silent clobber we run an
    optimistic-lock precondition: the edit form carries the
    `updated_at` the row was rendered with; before writing we re-read the
    bead LIVE (cache-bypassing) and, if its `updated_at` has moved on, we
    reject the stale submit with a friendly "bead changed, please refresh"
    instead of overwriting the newer value. Append-only fields (notes) are
    exempt — an append never clobbers existing content.

    On success we return the freshly re-rendered field row (partials/
    field_row.html) for an in-place HTMX swap of `#field-row-<field>`.
    """
    _check_csrf(x_csrf_token, csrf)
    field = field.strip()
    spec = _field_spec(field)
    if not spec.editable or not spec.flag:
        # Not whitelisted (or whitelisted but missing a flag, which would be a
        # registry bug). Either way: refuse to write a non-editable field.
        return HTMLResponse(
            f'<p class="field-error" role="alert">Field “{field}” is not editable.</p>',
            status_code=400,
        )
    # Append-only fields (notes) must never be sent with --notes (which
    # REPLACES and would nuke agent verification history). The registry pins
    # the safe flag (--append-notes); an append with no content is a no-op we
    # reject rather than silently swallow.
    new_value = value if spec.editor == "md" else value.strip()
    if spec.append_only and not new_value.strip():
        return HTMLResponse(
            '<p class="field-error" role="alert">Nothing to add.</p>',
            status_code=400,
        )
    # Status gate + optimistic-lock precondition
    # share a single LIVE read of the bead so we never double-shell bd.
    #
    # Status gate: manual field editing only applies to OPEN beads. Once a
    # bead is in_progress (claimed / work-in-flight) or closed (historical
    # record), its fields are read-only — editing invites clobbering an
    # agent's in-flight change or rewriting completed history. The UI already
    # hides the edit affordances (see _bead_is_editable / _field_row), but a
    # crafted POST could still reach here, so we enforce server-side too. We
    # read LIVE (fresh=True) so a freshly-claimed bead can't slip an edit
    # through a stale cache. If the live read fails we degrade gracefully
    # rather than blocking — the registry whitelist already bounds the blast
    # radius to value edits on whitelisted fields.
    #
    # Optimistic lock: only meaningful for replace-semantics edits where a
    # stale form would clobber a concurrent change; append-only edits (notes)
    # can never clobber so we skip that check for them. A missing/empty token
    # (older form, or a client that didn't send it) skips the lock and
    # degrades to last-write-wins rather than blocking edits outright.
    current, _lock_err = await bd.show_long(bead_id, fresh=True)
    if current is not None:
        # Status gate first: a locked (in_progress / closed) bead rejects ALL
        # field writes, value-edit or append alike, before we even look at the
        # optimistic-lock token.
        if not _bead_is_editable(current):
            live_status = (current.get("status") or "").lower()
            log.info(
                "locked field edit rejected: %s %s status=%s",
                bead_id,
                field,
                live_status,
            )
            return HTMLResponse(
                '<p class="field-error" role="alert">This bead is '
                f"{live_status or 'no longer open'} and can no longer be "
                "edited — only open beads are editable.</p>",
                status_code=403,
            )
        if expected_updated_at and not spec.append_only:
            live_updated_at = str(current.get("updated_at") or "")
            if live_updated_at and live_updated_at != expected_updated_at.strip():
                log.info(
                    "stale field edit rejected: %s %s expected=%s live=%s",
                    bead_id,
                    field,
                    expected_updated_at,
                    live_updated_at,
                )
                return HTMLResponse(
                    '<p class="field-error" role="alert">This bead changed since '
                    "you opened it — please refresh and re-apply your edit so "
                    "you don’t overwrite someone else’s change.</p>",
                    status_code=409,
                )
    try:
        await bd.update_field(bead_id, spec.flag, new_value, actor=_ACTOR)
    except RuntimeError as err:
        log.warning("bd update %s %s failed: %s", bead_id, spec.flag, err)
        return HTMLResponse(
            f'<p class="field-error" role="alert">Could not save: {err}</p>',
            status_code=500,
        )
    # Broadcast SSE so other tabs/clients refresh too.
    await bus.broadcast("beads_changed")
    # Optimistic re-render: fetch the post-edit bead and return JUST the
    # affected field row for an in-place swap. Falls back to the cached
    # snapshot if the live read momentarily fails, so the user still sees a
    # row (it will reconcile on the SSE-driven refresh).
    full, _err = await bd.show_long(bead_id)
    bead: dict[str, Any] | None = full
    if bead is None:
        await store.snapshot()
        bead = store.bead(bead_id)
    if bead is None:
        # The edit succeeded but we can't re-read — nudge the client to reload
        # the whole modal rather than leaving a stale row.
        return HTMLResponse(
            '<p class="field-error" role="alert">Saved, but could not refresh — '
            "reopen the bead to see the change.</p>",
            status_code=200,
        )
    row = next((r for r in _ordered_fields(bead) if r["key"] == field), None)
    if row is None:
        # Field saved but no longer present in the rendered set (e.g. cleared
        # to empty and filtered): re-render is best-effort, so acknowledge.
        return HTMLResponse(
            '<p class="field-saved" role="status">Saved.</p>',
            status_code=200,
        )
    row_html = TEMPLATES.TemplateResponse(
        request,
        "partials/field_row.html",
        {"f": row, "bead_id": bead_id, "bead_updated_at": bead.get("updated_at")},
    ).body.decode()
    # When priority changes, the modal-header badge would otherwise stay
    # stale until the modal is closed/reopened. Append an
    # out-of-band copy of the header badge so HTMX swaps it in the same
    # response — same OOB idiom the audit endpoint uses for #lifecycle-slot.
    if field == "priority":
        badge_html = TEMPLATES.TemplateResponse(
            request,
            "partials/bead_priority_badge.html",
            {"bead": bead, "oob": True},
        ).body.decode()
        row_html += badge_html
    return HTMLResponse(row_html)


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
    # The per-bead status-transition timeline
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
# trivial (it just dispatches on the kind string) and the logic here in Python
# where it belongs. Adding a new kind is one entry here + one branch in
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


# ─────────────────────────────────────────────────────────────────────────
# Field editability registry
#
# Single source of truth mapping each bd field key to *how* (if at all) its
# VALUE may be manually edited from bdboard. This is the extensibility seam
# manual field editing is built on: adding a newly-
# editable field later is ONE entry here, mirroring how the _KIND_* sets
# above let you add a render kind in one place. DRY + open/closed.
#
# _ordered_fields() consults this to decorate each modal field row with
# `editable` + `editor` hints; nothing here invokes `bd update`.
#
# Scope guardrail: we whitelist
# only fields whose *existing VALUE* can be edited in place via `bd update`.
# Fields that edit shape/graph/lifecycle (labels, parent, metadata kv,
# status) or that have no `bd update` flag at all (story_points, timestamps,
# id, derived counts) are intentionally NOT editable here. "Edit anything
# scalar-looking" is a known foot-gun — story_points has no update flag.
#
# Editor kinds: "text" | "textarea" | "md" | "select" | "number".
#   - text:     single-line free string scalar.
#   - textarea: multi-line plain text.
#   - md:       multi-line markdown prose (rendered via md.render on display).
#   - select:   constrained enum; render a dropdown from `enum_options`.
#   - number:   integer value.
# `flag` is the exact `bd update` flag the write path
# will pass. `enum_options` is populated only for select editors so the
# dropdown can be built server-side from one source (no enum drift).
# `append_only` flags fields where the safe edit semantics are append rather
# than replace — notably `notes`, where `bd update --notes` REPLACES and
# would destroy agent verification history (spike §3.2, §4). The write path
# MUST honour this; here it just rides along as a hint.


@dataclass(frozen=True)
class FieldSpec:
    """How a single bd field's value may be manually edited.

    Frozen so the registry is an immutable source of truth (mirrors the
    frozen CacheEntry dataclass in bd.py). A field absent from the registry
    is implicitly non-editable — read-only is the safe default.
    """

    editable: bool
    flag: str | None = None  # the `bd update` flag the write path will use
    editor: str | None = None  # text | textarea | md | select | number
    enum_options: tuple[str, ...] | None = None  # only for select editors
    append_only: bool = False  # safe semantics are append, not replace


# Priority is an integer enum P0..P4 in bd; expose the option *values* as
# strings so the future <select> can label them "P0".."P4" while posting the
# bare int. issue_type enum mirrors bd's built-in set (custom-config aside).
_PRIORITY_OPTIONS = ("0", "1", "2", "3", "4")
_ISSUE_TYPE_OPTIONS = ("bug", "feature", "task", "epic", "chore", "decision")

# The registry. Only the v1 whitelist (spike §5) is marked editable; every
# other field bd emits is intentionally absent (=> read-only). Keep this the
# ONLY place that knows a field's edit affordances.
_FIELD_REGISTRY: dict[str, FieldSpec] = {
    # ─ low-risk scalars / prose (v1 editable set) ─
    "title": FieldSpec(editable=True, flag="--title", editor="text"),
    "description": FieldSpec(editable=True, flag="--description", editor="md"),
    "acceptance_criteria": FieldSpec(editable=True, flag="--acceptance", editor="md"),
    "design": FieldSpec(editable=True, flag="--design", editor="md"),
    "priority": FieldSpec(
        editable=True,
        flag="--priority",
        editor="select",
        enum_options=_PRIORITY_OPTIONS,
    ),
    "assignee": FieldSpec(editable=True, flag="--assignee", editor="text"),
    "issue_type": FieldSpec(
        editable=True,
        flag="--type",
        editor="select",
        enum_options=_ISSUE_TYPE_OPTIONS,
    ),
    "external_ref": FieldSpec(editable=True, flag="--external-ref", editor="text"),
    "estimate": FieldSpec(editable=True, flag="--estimate", editor="number"),
    # notes: editable but append-only. `bd update --notes` REPLACES and would
    # nuke agent verification history; the safe path is `--append-notes`.
    "notes": FieldSpec(
        editable=True,
        flag="--append-notes",
        editor="md",
        append_only=True,
    ),
}

# Read-only fallback for any field not in the registry. Shared instance so
# every non-editable row points at the same immutable spec.
_READONLY_SPEC = FieldSpec(editable=False)


def _field_spec(key: str) -> FieldSpec:
    """Return the FieldSpec for a bd field key, defaulting to read-only.

    Read-only is the safe default: a field nobody has explicitly whitelisted
    must never be presented as editable.
    """
    return _FIELD_REGISTRY.get(key, _READONLY_SPEC)


# Statuses that LOCK a bead against manual field editing.
# Manual editing only applies while a bead is still open:
#   - in_progress => work is in-flight / claimed; editing risks clobbering
#     a change an agent is actively making.
#   - closed/resolved/done => the bead is historical record; editing rewrites
#     completed work.
# Everything else (open, and pre-work states like blocked / deferred that are
# neither claimed nor completed) stays editable. CLOSED_STATUSES is reused
# from derive so the closed set has ONE definition (DRY).
_LOCKED_EDIT_STATUSES: frozenset[str] = derive.CLOSED_STATUSES | {"in_progress"}


def _bead_is_editable(bead: dict[str, Any]) -> bool:
    """Whether a bead's fields may be manually edited, gated by status.

    Single source of truth for the open-vs-locked decision so the UI hint
    pass (_ordered_fields) and the server-side write guard
    (api_bead_field_update) can never disagree. A bead with no status falls
    back to editable — absence of a lifecycle marker is treated as "open".
    """
    status = (bead.get("status") or "").lower()
    return status not in _LOCKED_EDIT_STATUSES


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


def _field_row(key: str, val: Any, *, bead_editable: bool = True) -> dict[str, Any]:
    """Build one modal field row with render + editability hints.

    Single source of the row shape so the two passes in _ordered_fields
    (ordered keys, then alphabetical leftovers) can't drift apart (DRY).
    The `editor`/`enum_options`/`append_only` hints come straight from the
    field registry; the template stays declarative and just reads them.

    `bead_editable` gates the per-field `editable` hint by the
    bead's lifecycle status: even a registry-editable field renders read-only
    once the bead is in_progress or closed, so the modal exposes no edit
    affordances for claimed / completed work. The registry still decides
    WHICH fields are ever editable; status decides WHEN.
    """
    kind = _classify_field(key, val)
    spec = _field_spec(key)
    return {
        "key": key,
        "val": val,
        "kind": kind,
        "short_meta": _is_short_meta_field(key, kind),
        "editable": spec.editable and bead_editable,
        "editor": spec.editor,
        "flag": spec.flag,
        "enum_options": spec.enum_options,
        "append_only": spec.append_only,
    }


def _ordered_fields(bead: dict[str, Any]) -> list[dict[str, Any]]:
    """Return field rows in display order, exposing every non-hidden bd field.

    Each row carries render hints (kind/short_meta) AND editability hints
    (editable/editor/flag/enum_options/append_only) so the template can stay
    mostly declarative. The editability hints are sourced from
    _FIELD_REGISTRY — the single source of truth for manual editing.
    """
    bead_editable = _bead_is_editable(bead)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for k in _FIELD_ORDER:
        if k in bead and k not in _HIDDEN:
            out.append(_field_row(k, bead[k], bead_editable=bead_editable))
            seen.add(k)
    for k in sorted(bead.keys()):
        if k in seen or k in _HIDDEN:
            continue
        out.append(_field_row(k, bead[k], bead_editable=bead_editable))
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
