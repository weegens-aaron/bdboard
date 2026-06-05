# GET /api/bead/{id}/raw

> [!NOTE]
> The route is registered as `GET /api/bead/{bead_id}/raw`
> (`@app.get("/api/bead/{bead_id}/raw", response_class=JSONResponse)`). The path
> parameter is the bead id (`bdboard-x1`, `bdboard-mol-q7j.26`, …). This is the
> **escape hatch** for the [Bead Detail Modal](../Features/index.md): it dumps
> every field `bd` knows about as raw JSON, for when the curated modal layout
> (`GET /api/bead/{id}`) hides something you need. It is a pure read — no CSRF, no mutation, no SSE
> broadcast.

## Overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/bead/{bead_id}/raw` | None (single-user localhost dashboard; no cookies/session/CSRF) | Return the **complete** bead record from `bd show <id> --long --json` as unformatted JSON, bypassing the modal's field selection/ordering/redaction so a maintainer can inspect every field bd emits |

## Request

A bare `GET` — no body, no headers required. The browser reaches it via the
`raw JSON` link rendered in the modal header
(`partials/bead_modal.html`: `<a href="/api/bead/{{ bead.id }}/raw"
target="_blank">raw JSON</a>`), which opens the payload in a new tab.

### Path/Query Params

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `bead_id` | path | string | yes | The bead to dump (e.g. `bdboard-mol-q7j.26`). Passed straight to `bd show <bead_id> --long`. An unknown id does **not** raise — it falls through to the cached snapshot and then to an `{"error": …}` body (still HTTP `200`). |

### Headers

| Header | Required | Notes |
| --- | --- | --- |
| _(none)_ | no | No auth, CSRF, or content negotiation. The handler always responds `application/json` regardless of the request `Accept` header. |

### Body

```json
(none — GET request carries no body)
```

### Validation Rules

| Field | Rule | Error |
| --- | --- | --- |
| `bead_id` | None enforced at the route. Existence is delegated to `bd show`; a miss degrades gracefully rather than 4xx-ing | None — a miss returns `200` with `{"error": "not found"}` (or bd's error string) |

### Rate Limit

| Limit | Window | Scope |
| --- | --- | --- |
| None (no rate limiter) | — | bdboard is a single-user localhost dashboard. The only throttle is structural: `bd show` reads are serialized on `BdClient._subprocess_gate` (`asyncio.Semaphore(1)`) and memoized in `_show_cache` (`SUCCESS_TTL_S = 10.0s`), so repeated raw-JSON opens of the same bead within the TTL hit the cache instead of re-spawning `bd`. |

## Response

`Content-Type: application/json` (`response_class=JSONResponse`). The body is the
**verbatim bead dict** as bd returns it (FastAPI's `JSONResponse` re-serializes
it), not an HTML fragment — this is the one bdboard route whose response is
machine-shaped rather than server-rendered HTMX.

### Success

`200 OK` — the full bead object, one JSON dict. The exact key set is whatever
`bd show --long --json` emits for that bead (bdboard does **not** whitelist or
reorder it here); a representative payload for a task bead:

```json
{
  "id": "bdboard-mol-q7j.26",
  "title": "FlowDoc maintainer: Endpoint: GET /api/bead/{id}/raw",
  "description": "Write __docs/Endpoints/GetApiBeadRaw.md following the Endpoint template…",
  "status": "in_progress",
  "priority": 2,
  "issue_type": "task",
  "assignee": "Aaron Weegens",
  "owner": "aaron.weegens@walmart.com",
  "created_at": "2026-06-05T02:37:36Z",
  "created_by": "Aaron Weegens",
  "updated_at": "2026-06-05T04:53:54Z",
  "started_at": "2026-06-05T04:53:54Z",
  "labels": ["discover", "docs", "flowdoc"],
  "dependencies": [
    {
      "id": "bdboard-mol-q7j",
      "title": "FlowDoc maintainer: discover & scaffold, then spawn one bead per doc"
    }
  ],
  "parent": "bdboard-mol-q7j"
}
```

> [!NOTE]
> `bd show --long --json` returns a JSON **array**; `BdClient.show_long` unwraps
> `value[0]` before this route ever sees it, so the response is a single object,
> not a one-element list. Keys are sparse — bd omits fields that are empty for a
> given bead (a bead with no parent simply has no `parent` key), so consumers
> must treat every key as optional.

> [!WARNING]
> Because the live read and the modal (`GET /api/bead/{id}`) share
> `BdClient._show_cache`, the raw dump can be up to `SUCCESS_TTL_S` (10s) stale
> relative to disk — it reflects the last cached `bd show`, not a guaranteed live
> read. (The field-edit write path,
> [POST /api/bead/{id}/field](PostApiBeadField.md), uses
> `show_long(fresh=True)` to bypass this; the raw endpoint deliberately does
> not, trading freshness for a free cache hit.)

The two degraded shapes (still `200`, because the route never raises):

```json
{ "error": "Could not load bead data right now (show). Please try again." }
```

is returned when the live `bd show` failed **and** the bead is also absent from
the cached snapshot — `full = store.bead(bead_id) or {"error": err or "not found"}`.
If bd failed but the bead exists in the active/closed snapshot, the snapshot
dict is returned instead (a smaller field set than `--long`, but useful).

### Errors

| Status | Code | When |
| --- | --- | --- |
| `200` | `{"error": "<bd error string>"}` | `bd show` failed (non-zero exit/timeout/parse error) AND the bead is not in the cached snapshot. The bd error message (e.g. "Request timed out while loading bead data. Please try again.") is surfaced verbatim. |
| `200` | `{"error": "not found"}` | `bd show` returned no value, no cached error string was available, and the bead is not in the snapshot. |
| `500` | (FastAPI default) | Only if an unexpected exception escapes the handler (not expected — `show_long` already converts bd failures into `(None, err)` tuples rather than raising). |

> [!IMPORTANT]
> This endpoint intentionally **never returns 404**. Unlike the modal read
> `GET /api/bead/{id}` (which renders a 404 "we couldn't find that bead" modal),
> the raw dump is a
> diagnostic tool: a maintainer opening it for a missing/typo'd id gets a JSON
> `{"error": …}` body they can read, not an HTTP error page. Don't build alerting
> that keys off the status code here — inspect the `error` key instead.

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |
| Route handler (live read → fallback → JSON) | `src/bdboard/app.py` | `api_bead_raw` |
| Live (cached) `bd show <id> --long --json` read + array unwrap | `src/bdboard/bd.py` | `BdClient.show_long` |
| TTL cache + in-flight dedup shared with the modal | `src/bdboard/bd.py` | `BdClient._cached`, `BdClient._show_cache`, `CacheEntry` |
| Serialized subprocess invocation (fd-leak-safe) | `src/bdboard/bd.py` | `BdClient._run_json`, `BdClient._subprocess_gate` |
| Snapshot fallback when bd is unavailable | `src/bdboard/store.py` | `Store.snapshot`, `Store.bead` |
| JSON serialization of the response | `src/bdboard/app.py` | `JSONResponse` (from `fastapi.responses`) |
| The modal link that opens this route | `src/bdboard/templates/partials/bead_modal.html` | `<a href="/api/bead/{{ bead.id }}/raw">` |

```mermaid
sequenceDiagram
    participant Browser as Browser (new tab)
    participant Route as api_bead_raw
    participant BD as BdClient.show_long
    participant Cache as _show_cache (TTL 10s)
    participant Proc as bd show --long --json
    participant Store as Store (snapshot fallback)
    Browser->>Route: GET /api/bead/{id}/raw
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
        Route-->>Browser: 200 JSON {full bead dict}
    else bd failed
        Route->>Store: snapshot(); bead(id)
        alt found in snapshot
            Store-->>Route: snapshot dict
            Route-->>Browser: 200 JSON {snapshot bead}
        else not found
            Store-->>Route: None
            Route-->>Browser: 200 JSON {"error": err or "not found"}
        end
    end
```

## Example

Dump every field bd knows about for `bdboard-mol-q7j.26` and pretty-print it:

```bash
curl -s http://127.0.0.1:8000/api/bead/bdboard-mol-q7j.26/raw | python3 -m json.tool
```

Pull a single field out of the raw dump with `jq` (handy when the modal hides
it):

```bash
curl -s http://127.0.0.1:8000/api/bead/bdboard-mol-q7j.26/raw | jq '.owner'
```

Confirm the graceful-miss behavior for an unknown id (note: still `200`, with an
`error` key, not a 404):

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8000/api/bead/bdboard-does-not-exist/raw
# -> 200
curl -s http://127.0.0.1:8000/api/bead/bdboard-does-not-exist/raw
# -> {"error":"not found"}   (or bd's live error string)
```

## Testing

There is no dedicated route test for `api_bead_raw` (it is a thin pass-through
over already-covered machinery). Its behavior is exercised transitively:

- `tests/test_field_edit.py::test_show_long_fresh_bypasses_show_cache` covers the
  shared `BdClient.show_long` / `_show_cache` read-and-unwrap path this endpoint
  depends on.
- `tests/test_api_bead_audit.py` exercises the sibling `/api/bead/{id}/*` route
  wiring and the same FastAPI handler-invocation harness.
- `tests/test_build_docs_site.py` validates this very doc (source↔output parity,
  links resolve, no stray fences/callouts, no source-path leaks).

To smoke-test it by hand, start the server (`bdboard` / `uvicorn
bdboard.app:app`) and run the `curl` invocations above, including the
unknown-id case to confirm the `200 + {"error": …}` graceful miss.

## Related

- [Endpoints index](index.md) — every route bdboard exposes, including the
  curated **modal** read [GET /api/bead/{id}](GetApiBead.md) (this endpoint is its raw escape
  hatch — the two share `BdClient.show_long` and `_show_cache`) and its
  lazily-loaded [GET /api/bead/{id}/audit](GetApiBeadAudit.md) sibling.
- [POST /api/bead/{id}/field](PostApiBeadField.md) — the write half of the modal;
  uses `show_long(fresh=True)` to deliberately bypass the cache this read relies
  on.
- [Feature: Bead Detail Modal](../Features/index.md) — the feature whose `raw
  JSON` link surfaces this endpoint.
- [Concept: Subprocess Serialization & Caching](../Concepts/SubprocessSerializationAndCaching.md)
  — the `_subprocess_gate` + `_show_cache` machinery behind every `bd show`.
- [Concept: bd CLI as Source of Truth](../Concepts/BdCliSourceOfTruth.md) — why
  the raw payload is literally `bd show --long --json`.
- [Back to docs index](../index.md)
