# POST /api/memory

> [!NOTE]
> The route is registered as `POST /api/memory`
> (`@app.post("/api/memory", response_class=HTMLResponse)`). This is the
> **upsert (remember) half** of [Memory Curation](../Features/index.md): it
> creates *or* replaces ONE `bd` memory via `bd remember <body> --key <key>`,
> broadcasts an SSE `beads_changed`, then returns the re-rendered memory list
> for an HTMX swap. It is the constructive sibling of the destructive path
> [DELETE /api/memory/{key}](DeleteApiMemory.md) and shares the exact same
> CSRF + serialized-mutation + SSE-broadcast + `memory_list.html` plumbing —
> the one asymmetry is that this path **also accepts a form-field CSRF
> fallback** (`csrf_token`), whereas DELETE accepts the header only.

## Overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/memory` | CSRF token (header `X-CSRF-Token` **or** form field `csrf_token` — either matches); no cookies/session | Upsert one `bd` memory by key via `bd remember <body> --key <key>` (create if new, replace body if the key exists), broadcast an SSE `beads_changed`, then return the re-rendered `partials/memory_list.html` for an in-place HTMX swap of `#memory-list` |

## Request

`Content-Type: application/x-www-form-urlencoded`. The `<dialog>` form in
`memory.html` posts three form fields (`key`, `body`, `csrf_token`) and also
sends the CSRF token via `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'`.
The "Save Memory" submit button fires the `hx-post="/api/memory"`, targeting
`#memory-list` with `hx-swap="innerHTML"`. The same dialog serves both create
("+ New Memory") and edit (per-card edit button, which pre-fills the form and
makes the key field `readonly` — you cannot rename a key via `bd remember`,
only replace its body).

### Path/Query Params

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| _(none)_ | — | — | — | This route takes no path or query parameters; all inputs arrive in the form body (and the CSRF header). The key is a form field here, NOT a path segment (contrast [DELETE /api/memory/{key}](DeleteApiMemory.md), where the key is a `:path` URL segment). |

### Headers

| Header | Required | Notes |
| --- | --- | --- |
| `X-CSRF-Token` | conditionally | Process-lifetime CSRF token. HTMX sends it via `hx-headers` on the form. `_check_csrf(x_csrf_token, csrf)` passes if **either** the header **or** the `csrf_token` form field matches `_CSRF_TOKEN`, so supplying the header satisfies auth even with no form field — see [CSRF Protection](../Concepts/CsrfProtection.md). |
| `Content-Type` | yes | `application/x-www-form-urlencoded` — the handler declares `key`/`body`/`csrf` as `Form(...)`, so FastAPI parses a urlencoded (or multipart) body. A JSON body would 422 on the missing form fields. |

### Body

Form-encoded fields (shown as a JSON map of field → value for clarity; the wire
encoding is `application/x-www-form-urlencoded`):

```json
{
  "key": "dev-workflow",
  "body": "Always run ruff check --fix before committing.",
  "csrf_token": "<process CSRF token (form-field fallback for the header)>"
}
```

### Validation Rules

| Field | Rule | Error |
| --- | --- | --- |
| `X-CSRF-Token` / `csrf_token` | At least one must equal the process `_CSRF_TOKEN` (header OR form fallback) | `403` (HTTPException) `Invalid or missing CSRF token. Please refresh the page and try again.` |
| `key` | Required form field; must be non-blank after `.strip()` | `400` `Key cannot be empty.` |
| `body` | Required form field; must be non-blank after `.strip()` | `400` `Body cannot be empty.` |
| `key` / `body` presence | Both are `Form(...)` (required) — an entirely missing field is a FastAPI validation failure, not the handler's `400` | `422` Unprocessable Entity (FastAPI request validation) |
| upsert semantics | NOT validated — an existing key is replaced, a new key is created; `bd remember` is the authority | — (no error; replace-or-create) |

### Rate Limit

| Limit | Window | Scope |
| --- | --- | --- |
| None (no rate limiter) | — | bdboard is a single-user localhost dashboard. There is no token-bucket / IP throttle; the only throttle is structural: every `bd` mutation is serialized on `BdClient._subprocess_gate` (Dolt is single-writer), so a concurrent remember/forget queues behind the in-flight one rather than racing. |

## Response

`Content-Type: text/html` (`response_class=HTMLResponse`). The body is an HTML
**fragment**, not JSON — bdboard is server-rendered HTMX, so the route returns
the re-rendered memory list that HTMX swaps into `#memory-list` via
`hx-swap="innerHTML"`.

### Success

`200 OK` — the re-rendered `partials/memory_list.html` (built from a fresh
`bd.memories()` read with an empty query, so the full list returns *including*
the just-saved memory). Shape:

```html
<p class="memory-count" role="status" aria-live="polite">
  4 memories
</p>
<ul class="memory-list" role="list">
  <li class="memory-card">
    <div class="memory-card-head">
      <h3 class="memory-key">dev-workflow</h3>
      <div class="memory-card-actions">
        <button type="button" class="memory-action-btn memory-edit-btn"
                aria-label="Edit dev-workflow" title="Edit"
                data-key="dev-workflow" data-body="…"
                onclick="editMemory(this.dataset.key, this.dataset.body)"></button>
        <button type="button" class="memory-action-btn memory-forget-btn"
                aria-label="Forget dev-workflow" title="Forget"
                onclick="confirmForget('dev-workflow')"></button>
      </div>
    </div>
    <div class="memory-body prose"><!-- markdown-rendered body --></div>
  </li>
  <!-- … remaining cards (sorted alphabetically by key) … -->
</ul>
```

> [!IMPORTANT]
> On success the handler ALSO calls `bus.broadcast("beads_changed")` BEFORE
> re-reading the list. That SSE event makes every *other* open tab re-fetch
> `GET /api/memory` (via `refresh from:body`), while the swap returned to *this*
> tab is an optimistic refresh so the acting user sees their new/updated memory
> immediately without waiting for the watcher debounce.

> [!NOTE]
> The re-read uses `bd.memories()` with an **empty query**, so the returned
> list is the *full* list, not filtered by whatever search term was active in
> the box. After a save the user sees the complete memory set (sorted
> alphabetically by key, `schema_version` sentinel stripped).

### Errors

| Status | Code | When |
| --- | --- | --- |
| `403` | `Invalid or missing CSRF token. Please refresh the page and try again.` | `_check_csrf(x_csrf_token, csrf)` failed — neither the `X-CSRF-Token` header nor the `csrf_token` form field matched `_CSRF_TOKEN` (e.g. a server restart minted a new token). Raised as `HTTPException`; no `bd` mutation runs. |
| `400` | `<p class="memory-error" role="alert">Key cannot be empty.</p>` | The `key` form field was blank after `.strip()`. |
| `400` | `<p class="memory-error" role="alert">Body cannot be empty.</p>` | The `body` form field was blank after `.strip()`. |
| `422` | FastAPI request-validation error | A required `Form(...)` field (`key` or `body`) was entirely absent from the request body. |
| `500` | `<p class="memory-error" role="alert">Could not save: <bd stderr></p>` | `bd.remember` raised `RuntimeError` — `bd remember <body> --key <key>` exited non-zero (surfaces bd's stderr) or timed out (`REMEMBER_TIMEOUT_S = 10.0s` → "Request timed out while saving. Please try again."). |

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |
| Route handler (validate → remember → broadcast → re-render) | `src/bdboard/app.py` | `api_memory_create` |
| CSRF guard (header OR form fallback) | `src/bdboard/app.py` | `_check_csrf`, `_CSRF_TOKEN` |
| Form-field binding (`key`, `body`, `csrf_token` alias) | `src/bdboard/app.py` | `api_memory_create` (`Form(...)`, `Header(None)`) |
| Serialized `bd remember <body> --key <key>` write | `src/bdboard/bd.py` | `BdClient.remember` |
| Generic gated mutation runner (drain-safe subprocess) | `src/bdboard/bd.py` | `BdClient._run_mutate` |
| Remember timeout budget | `src/bdboard/bd.py` | `REMEMBER_TIMEOUT_S` |
| Memories cache invalidation after the write | `src/bdboard/bd.py` | `BdClient.remember` (clears `self._memories_cache`) |
| Fresh post-save list read for the swap | `src/bdboard/bd.py` | `BdClient.memories` |
| `schema_version` sentinel strip + alpha sort | `src/bdboard/bd.py` | `BdClient.memories`, `SCHEMA_VERSION_KEY` |
| SSE broadcast so other tabs refresh | `src/bdboard/events.py` | `bus.broadcast("beads_changed")` |
| Re-rendered list partial returned for the swap | `src/bdboard/templates/partials/memory_list.html` | (list markup + empty states) |
| Create/edit dialog + `hx-post` + CSRF wiring | `src/bdboard/templates/memory.html` | `#memory-form-dialog`, `editMemory()` |
| Markdown rendering of each memory body | `src/bdboard/md.py` | `render` (the `md` Jinja filter) |
| Endpoint regression coverage | `tests/test_memory_mutations.py` | `test_create_memory_*` |

```mermaid
sequenceDiagram
    participant Browser as Browser (memory dialog)
    participant Route as api_memory_create
    participant BD as BdClient (bd subprocess)
    participant Bus as SSE bus
    Browser->>Route: POST /api/memory<br/>form: key, body, csrf_token<br/>X-CSRF-Token header
    Route->>Route: _check_csrf(header, form)
    alt CSRF invalid
        Route-->>Browser: 403 Invalid CSRF (HTTPException)
    else CSRF ok
        Route->>Route: key=key.strip(); body=body.strip()
        alt key blank
            Route-->>Browser: 400 Key cannot be empty
        else body blank
            Route-->>Browser: 400 Body cannot be empty
        else both present
            Route->>BD: remember(key, body)
            BD->>BD: bd remember <body> --key <key> (gated)<br/>clear _memories_cache
            alt bd exits non-zero / timeout
                BD-->>Route: raise RuntimeError(stderr)
                Route-->>Browser: 500 Could not save: <err>
            else ok
                BD-->>Route: None
                Route->>Bus: broadcast("beads_changed")
                Route->>BD: memories() (fresh full list)
                BD-->>Route: [{key, body}, …] sorted, sentinel stripped
                Route-->>Browser: 200 re-rendered memory_list.html<br/>(swap #memory-list)
            end
        end
    end
```

## Example

Create (or replace) the memory keyed `dev-workflow` (CSRF via header AND form
fallback; form-encoded body):

```bash
curl -i -X POST "http://127.0.0.1:8000/api/memory" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  --data-urlencode "key=dev-workflow" \
  --data-urlencode "body=Always run ruff check --fix before committing." \
  --data-urlencode "csrf_token=$CSRF_TOKEN"
```

A successful call returns `200` with the re-rendered memory list (the new/updated
key present, alphabetically sorted); HTMX swaps it into `#memory-list` via
`hx-swap="innerHTML"`, and every other open tab re-fetches `GET /api/memory`
off the `beads_changed` SSE.

A blank body is rejected before any `bd` mutation runs:

```bash
curl -i -X POST "http://127.0.0.1:8000/api/memory" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  --data-urlencode "key=dev-workflow" \
  --data-urlencode "body=   "
# → 400  <p class="memory-error" role="alert">Body cannot be empty.</p>
```

A stale or missing token (neither header nor form matches) is a hard `403`:

```bash
curl -i -X POST "http://127.0.0.1:8000/api/memory" \
  --data-urlencode "key=dev-workflow" \
  --data-urlencode "body=anything"
# → 403  Invalid or missing CSRF token. Please refresh the page and try again.
```

## Related

- [Endpoints index](index.md) — every route bdboard exposes.
- [DELETE /api/memory/{key}](DeleteApiMemory.md) — the destructive sibling
  (forget); shares the exact CSRF + serialized-mutation + SSE-broadcast plumbing
  and returns the same `memory_list.html` partial (that delete path accepts the
  header CSRF only; this create path *also* accepts a form-field fallback).
- [GET /api/memory](index.md) — the read half that renders the list this
  endpoint mutates (see the Endpoints index until its own doc lands); it's what
  other tabs re-fetch on the `beads_changed` SSE, and what the active search box
  drives.
- [POST /api/bead/{id}/field](PostApiBeadField.md) — the other CSRF-guarded,
  serialized `bd`-mutation write path; same `_check_csrf` + gate + broadcast idiom.
- [Memory (/memory)](../Views/MemoryView.md) — the page surface whose
  create/edit `<dialog>` fires this POST.
- [Feature: Memory Curation](../Features/index.md) — the feature this endpoint
  implements.
- [CSRF Protection](../Concepts/CsrfProtection.md) — the token guard fronting
  this write (and why this path accepts a form fallback in addition to the header).
- [Subprocess Serialization & Caching](../Concepts/SubprocessSerializationAndCaching.md)
  — the semaphore + cache-invalidation behind `BdClient.remember`.
- [SSE Event Bus](../Concepts/SseEventBus.md) — the `beads_changed` broadcast
  that keeps every tab's list live after a save.
- [bd CLI as Source of Truth](../Concepts/BdCliSourceOfTruth.md) — why this path
  shells `bd remember` instead of touching `.beads/` directly.
- [Back to docs index](../index.md)
