# GET /api/bead/{id}

> [!NOTE]
> The route is registered as `GET /api/bead/{bead_id}`
> (`@app.get("/api/bead/{bead_id}", response_class=HTMLResponse)`). The path
> parameter is the bead id (`bdboard-x1`, `bdboard-mol-q7j.24`, …). This is the
> **primary read** behind the [Bead Detail Modal](../Features/index.md): a bead
> card is clicked, HTMX fetches this route, and the returned HTML fragment is
> swapped into `#bead-modal`. Unlike its [raw escape hatch](GetApiBeadRaw.md),
> this endpoint returns **server-rendered HTML** (the curated modal), not JSON.
> It is a pure read — no CSRF, no mutation, no SSE broadcast.

## Overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/bead/{bead_id}` | None (single-user localhost dashboard; no cookies/session/CSRF) | Render the **curated Bead Detail Modal** — a server-rendered HTMX partial (`partials/bead_modal.html`) showing the full bead in display order with per-field edit affordances, a lifecycle/audit slot, and a `raw JSON` link — sourced from `bd show <id> --long --json`, with a cached-snapshot fallback so the modal still opens when bd is momentarily unavailable |

## Request

A bare `GET` — no body, no headers required. The browser reaches it three ways,
all via HTMX `hx-get` targeting `#bead-modal` with `hx-swap="innerHTML"`:

- a **bead card** click on the board / closed lane / History list
  (`partials/bead_card.html`: `hx-get="/api/bead/{{ b.id }}"`),
- an **epic / lane item** click (`partials/lanes.html`), and
- a **dependency chip** click *inside* an already-open modal
  (`partials/field_row.html`: `hx-get="/api/bead/{{ d.depends_on_id or d.target or d.id }}"`),
  which re-renders the modal for the linked bead — recursive navigation through
  the dependency graph.

### Path/Query Params

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `bead_id` | path | string | yes | The bead to render (e.g. `bdboard-mol-q7j.24`). Passed straight to `bd show <bead_id> --long`. An unknown id is the **one case** this route 4xx-es: after the live read and the cached-snapshot fallback both miss, it returns `404` with an HTML error fragment (contrast the raw endpoint, which never 404s). |

### Headers

| Header | Required | Notes |
| --- | --- | --- |
| _(none)_ | no | No auth, CSRF, or content negotiation. The handler always responds `text/html` (`response_class=HTMLResponse`) regardless of the request `Accept` header. HTMX adds `HX-Request: true` on its fetches, but the handler does not inspect it. |

### Body

```json
(none — GET request carries no body)
```

### Validation Rules

| Field | Rule | Error |
| --- | --- | --- |
| `bead_id` | No format validation at the route. Existence is delegated to `bd show`, then to the cached snapshot (`store.bead`). Only if **both** miss is it treated as invalid | `404` with an HTML `<div class='modal-error'>` fragment ("We couldn't find that bead. Please refresh the board and try again.") — there is no JSON error body |

### Rate Limit

| Limit | Window | Scope |
| --- | --- | --- |
| None (no rate limiter) | — | bdboard is a single-user localhost dashboard. The only throttle is structural: `bd show` reads are serialized on `BdClient._subprocess_gate` (`asyncio.Semaphore(1)`) and memoized in `_show_cache` (`SUCCESS_TTL_S = 10.0s`), with in-flight dedup so two near-simultaneous opens of the same bead share one subprocess. Repeated opens of the same bead within the TTL hit the cache instead of re-spawning `bd` (`SHOW_TIMEOUT_S = 8.0s` per live call). |

## Response

`Content-Type: text/html` (`response_class=HTMLResponse`). The body is the
rendered `partials/bead_modal.html` fragment — HTMX swaps it into `#bead-modal`.
This is **not** a JSON payload; for the machine-shaped dump use
[GET /api/bead/{id}/raw](GetApiBeadRaw.md).

### Success

`200 OK` — the rendered modal fragment. Its shape (abridged; real classes and
HTMX attributes from `partials/bead_modal.html`):

```html
<div class="modal-backdrop" onclick="…dismiss…">
  <article class="modal">
    <header class="modal-head">
      <div class="modal-head-row">
        <span class="bead-id">bdboard-mol-q7j.24</span>
        <!-- priority badge (partials/bead_priority_badge.html) -->
        <span class="bead-status status-in_progress">in_progress</span>
        <button class="modal-close" onclick="…"></button>
      </div>
      <h2 class="modal-title">FlowDoc maintainer: Endpoint: GET /api/bead/{id}</h2>
      <!-- {% if warning %}<div class="modal-warning"> …</div>{% endif %} -->
      <div class="modal-source muted">view: Live details ·
        <a href="/api/bead/bdboard-mol-q7j.24/raw" target="_blank">raw JSON</a></div>
    </header>
    <div class="modal-scroll">
      <div id="lifecycle-slot"></div>            <!-- OOB-filled by /audit -->
      <section class="modal-body">
        <h3 class="modal-section-title">Bead details</h3>
        <dl class="field-grid">
          <!-- one partials/field_row.html per _ordered_fields(bead) entry -->
        </dl>
      </section>
      <section class="modal-body"
               hx-get="/api/bead/bdboard-mol-q7j.24/audit"
               hx-trigger="load" hx-swap="innerHTML">
        <h3 class="modal-section-title">Audit trail</h3>
        <p class="muted">loading history…</p>
      </section>
    </div>
  </article>
</div>
```

The handler hands the template three context values beyond the bead itself:

```json
{
  "source": "Live details | Cached snapshot",
  "warning": "Showing cached details while live data is temporarily unavailable. | null",
  "fields": "[ list of field rows from _ordered_fields(bead) ]"
}
```

Each entry in `fields` is the row shape produced by `_field_row`, carrying both
render and editability hints (the registry decides *which* fields are editable;
the bead's lifecycle status decides *when*):

```json
{
  "key": "priority",
  "val": 2,
  "kind": "scalar",
  "short_meta": true,
  "editable": true,
  "editor": "select",
  "flag": "--priority",
  "enum_options": ["0", "1", "2", "3", "4"],
  "append_only": false
}
```

> [!NOTE]
> `bd show --long --json` returns a JSON **array**; `BdClient.show_long` unwraps
> `value[0]` before the route sees it, so the handler always works with a single
> bead dict. The field list is built by `_ordered_fields`, which walks
> `_FIELD_ORDER` first (identity → content → state/meta → bulk) and then appends
> any remaining bd keys alphabetically — so a newly-added bd field is never
> silently hidden, only sorted to the bottom. `_HIDDEN = {"_type"}` is the one
> field dropped.

> [!WARNING]
> The live read shares `BdClient._show_cache` with the
> [raw endpoint](GetApiBeadRaw.md) and the read side of the
> [field-edit endpoint](PostApiBeadField.md), so the modal can be up to
> `SUCCESS_TTL_S` (10s) stale relative to disk. The write path deliberately
> calls `show_long(fresh=True)` to bypass this for its optimistic-lock check;
> this read does not, trading freshness for a free cache hit. After a watcher
> fire, `Store` calls `BdClient.invalidate_caches()` so the next open is live.

The cached-fallback variant is still HTTP `200`, same template, but driven off
the in-memory snapshot instead of a live `bd show`:

```json
{
  "source": "Cached snapshot",
  "warning": "Showing cached details while live data is temporarily unavailable."
}
```

This is returned when the live `bd show` failed **but** the bead is present in
the cached snapshot (`store.bead(bead_id)`). The snapshot dict has a smaller
field set than `--long`, but the modal still opens with useful content and a
visible `modal-warning` banner instead of hard-failing.

### Errors

| Status | Code | When |
| --- | --- | --- |
| `404` | HTML `<div class='modal-error'>We couldn't find that bead. Please refresh the board and try again.</div>` | Both the live `bd show` **and** the cached-snapshot lookup (`store.bead(bead_id)`) returned nothing. The most common cause is a genuinely unknown/typo'd id; it can also occur if bd is down *and* the bead was never loaded into the snapshot (e.g. a closed bead outside the cached window). |
| `500` | (FastAPI default) | Only if an unexpected exception escapes the handler (not expected — `show_long` converts bd failures into `(None, err)` tuples rather than raising, and the template render is the only other failure surface). |

> [!IMPORTANT]
> This is the **only** `/api/bead/{id}*` read that returns `404`. The
> [raw endpoint](GetApiBeadRaw.md) deliberately returns `200` + `{"error": …}`
> for a miss (it's a diagnostic tool), and the
> [audit endpoint](GetApiBeadAudit.md) returns `200` with a graceful
> "unavailable" partial (it loads lazily *after* this modal and must never block
> it). Here, a miss means the user clicked something that no longer exists, so an
> HTML error fragment in the modal is the right UX — and because HTMX swaps a
> `404` response body into the target by default, that error fragment still
> renders inside `#bead-modal` as intended.

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |
| Route handler (live read → snapshot fallback → 404 → render) | `src/bdboard/app.py` | `api_bead` |
| Live (cached) `bd show <id> --long --json` read + array unwrap | `src/bdboard/bd.py` | `BdClient.show_long` |
| TTL cache + in-flight dedup shared across bead reads | `src/bdboard/bd.py` | `BdClient._cached`, `BdClient._show_cache`, `CacheEntry` |
| Serialized subprocess invocation (fd-leak-safe) | `src/bdboard/bd.py` | `BdClient._run_json`, `BdClient._subprocess_gate` |
| Snapshot fallback + single-bead lookup when bd is unavailable | `src/bdboard/store.py` | `Store.snapshot`, `Store.bead` |
| Field ordering + render/editability hint rows | `src/bdboard/app.py` | `_ordered_fields`, `_field_row`, `_FIELD_ORDER`, `_HIDDEN` |
| Per-field edit affordances (which/how editable) | `src/bdboard/app.py` | `_field_spec`, `_FIELD_REGISTRY`, `FieldSpec`, `_bead_is_editable`, `_LOCKED_EDIT_STATUSES` |
| Dependency relationship labelling in dep rows | `src/bdboard/app.py` | `_dep_label` (Jinja filter `dep_label`) |
| Modal template (header, field grid, lifecycle slot, audit trigger) | `src/bdboard/templates/partials/bead_modal.html` | `bead_modal.html` |
| Per-field row render (scalar / chips / deps / comments / markdown / json) | `src/bdboard/templates/partials/field_row.html` | `field_row.html` |
| The cards/lanes that open this route | `src/bdboard/templates/partials/bead_card.html`, `src/bdboard/templates/partials/lanes.html` | `hx-get="/api/bead/{{ … }}"` |

```mermaid
sequenceDiagram
    participant Browser as Browser (HTMX)
    participant Route as api_bead
    participant BD as BdClient.show_long
    participant Cache as _show_cache (TTL 10s)
    participant Proc as bd show --long --json
    participant Store as Store (snapshot fallback)
    participant Tmpl as bead_modal.html
    Browser->>Route: GET /api/bead/{id}  (hx-target=#bead-modal)
    Route->>BD: show_long(id)
    BD->>Cache: lookup id
    alt cache fresh
        Cache-->>BD: cached bead
    else cache miss / stale
        BD->>Proc: bd show id --long --json (gated)
        alt bd ok
            Proc-->>BD: [ {bead} ]
            BD->>Cache: store(bead, ttl=10s)
        else bd error/timeout
            Proc-->>BD: non-zero / timeout
            BD->>Cache: store(error, ttl=30s)
        end
    end
    BD-->>Route: (full | None, err)
    alt full is not None
        Route->>Tmpl: render(source="Live details")
    else bd failed
        Route->>Store: snapshot(); bead(id)
        alt found in snapshot
            Store-->>Route: snapshot dict
            Route->>Tmpl: render(source="Cached snapshot", warning=…)
        else not found
            Store-->>Route: None
            Route-->>Browser: 404 HTML modal-error
        end
    end
    Tmpl-->>Browser: 200 HTML modal fragment
    Note over Browser: modal swaps in; then fires<br/>hx-get /api/bead/{id}/audit (load)
```

## Example

Fetch the rendered modal fragment for a bead (HTMX would normally do this; the
`HX-Request` header just mimics a real browser fetch):

```bash
curl -s -H 'HX-Request: true' \
  http://127.0.0.1:8000/api/bead/bdboard-mol-q7j.24
# -> <div class="modal-backdrop">…full modal HTML…</div>
```

Confirm the live vs. not-found behavior (note: this read *does* 404 for a truly
unknown id, unlike the raw endpoint):

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8000/api/bead/bdboard-mol-q7j.24
# -> 200
curl -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8000/api/bead/bdboard-does-not-exist
# -> 404
curl -s http://127.0.0.1:8000/api/bead/bdboard-does-not-exist
# -> <div class='modal-error'>We couldn’t find that bead. …</div>
```

## Testing

The endpoint's machinery is well covered; the route itself is a thin
orchestration over already-tested pieces:

- `tests/test_field_edit.py::test_show_long_fresh_bypasses_show_cache` covers the
  shared `BdClient.show_long` / `_show_cache` read-and-unwrap path this endpoint
  depends on (and proves this read *uses* the cache the write path bypasses).
- `tests/test_api_bead_audit.py` exercises the sibling `/api/bead/{id}/*` route
  wiring and the same FastAPI handler-invocation harness, including the modal's
  lazy audit trigger that this fragment emits.
- `tests/test_build_docs_site.py` validates this very doc (source↔output parity,
  links resolve, no stray fences/callouts, no source-path leaks).

To smoke-test by hand, start the server (`bdboard` / `uvicorn bdboard.app:app`),
open the board, click a bead card, and confirm the modal opens with field rows,
the `raw JSON` link, and the lazily-loaded audit trail; then click a dependency
chip to confirm recursive re-render. The `curl` invocations above cover the
live, fallback, and 404 paths without a browser.

## Related

- [Endpoints index](index.md) — every route bdboard exposes.
- [GET /api/bead/{id}/audit](GetApiBeadAudit.md) — the lazily-loaded lifecycle +
  audit trail this modal triggers on load (`hx-trigger="load"`), OOB-filling the
  `#lifecycle-slot`.
- [GET /api/bead/{id}/raw](GetApiBeadRaw.md) — the raw-JSON escape hatch reached
  via this modal's `raw JSON` link; the two share `BdClient.show_long` and
  `_show_cache`.
- [POST /api/bead/{id}/field](PostApiBeadField.md) — the write half of the modal;
  re-renders a single `field_row.html` and uses `show_long(fresh=True)` to bypass
  the cache this read relies on.
- [Concept: Subprocess Serialization & Caching](../Concepts/SubprocessSerializationAndCaching.md)
  — the `_subprocess_gate` + `_show_cache` machinery behind every `bd show`.
- [Concept: Store Snapshot & Change Detection](../Concepts/StoreSnapshotChangeDetection.md)
  — the in-memory snapshot this route falls back to when bd is unavailable.
- [Concept: Field Editability Registry](../Concepts/FieldEditabilityRegistry.md)
  — `_FIELD_REGISTRY`, the single source of truth for which modal fields are
  editable and how.
- [Concept: bd CLI as Source of Truth](../Concepts/BdCliSourceOfTruth.md) — why
  the modal payload is literally `bd show --long --json`.
- [Back to docs index](../index.md)
