# Endpoint: Bead detail API (`/api/bead/{id}`, `/audit`, `/raw`)

## Overview

The **read half** of the bead modal: three GET endpoints that, together, render
everything the detail modal shows. Clicking a bead card fires the first; the
modal then lazily fires the second; the third is a debug escape hatch linked
from the modal header. They are read-only — the *write* half lives in the
[Bead field-edit API](bead-field-edit-api.md).

| METHOD | Path | Purpose |
| --- | --- | --- |
| GET | `/api/bead/{bead_id}` | Render the bead-detail modal (HTML partial) — header, status, ordered field rows, and the async-loaded audit shell. |
| GET | `/api/bead/{bead_id}/audit` | Render the lifecycle timeline (OOB into `#lifecycle-slot`) **and** the field-by-field audit trail, both from one `bd history` call. |
| GET | `/api/bead/{bead_id}/raw` | Dump every field `bd` knows about for the bead as raw JSON (debug escape hatch). |

> [!IMPORTANT]
> The split is deliberate. `/api/bead/{id}` must paint *fast* (it's the click
> response), so it makes at most one `bd show` call and never blocks on history.
> The slower `bd history` read is deferred to `/audit`, fetched by the modal via
> `hx-trigger="load"` once the shell is on screen. One user action, two
> sequential fetches, two render targets — the modal is never a frozen click.

## Request

### Headers

| Header | Required | Notes |
| --- | --- | --- |
| `HX-Request` | No | Sent by HTMX on the card-click and `load`-triggered fetches. Not inspected by the handlers — responses are plain partials/JSON either way, so the endpoints are equally usable from `curl`. |

(No authentication or CSRF header — these are idempotent GETs. CSRF only guards
the write path, see [Bead field-edit API](bead-field-edit-api.md).)

### Params / Query

| Name | Type | Required | Default | Validation |
| --- | --- | --- | --- | --- |
| `bead_id` | path string | Yes | — | Passed straight to `bd show {id} --long` / `bd history {id}`. No client-side format check; an unknown id surfaces as a graceful 404 (detail) or an error payload (raw), never a crash. |

None of the three endpoints take a query string — everything is in the path.

### Body

None. All three are GET requests with no body.

## Response

### Success

**`GET /api/bead/{bead_id}` → `200 OK`, HTML partial**
([`partials/bead_modal.html`](../../src/bdboard/templates/partials/bead_modal.html)).
Renders the full-screen modal backdrop + card: the bead id, an inline
priority badge, the status chip, the title, an optional degradation warning, a
`raw JSON` link, an empty `#lifecycle-slot` (filled later by `/audit`), the
ordered **field rows** (built by `_ordered_fields`), and an audit `<section>`
wired with `hx-get=".../audit" hx-trigger="load"`. The handler prefers a live
`bd show --long --json` read; if that fails it falls back to the cached list
snapshot so the modal still renders useful content, flips `source` to
`"Cached snapshot"`, and shows a `warning` banner instead of hard-failing.

**`GET /api/bead/{bead_id}/audit` → `200 OK`, HTML partial**
([`partials/bead_audit.html`](../../src/bdboard/templates/partials/bead_audit.html)).
Two views over the *same* `bd history` payload:
1. A **lifecycle timeline** (`derive.status_timeline`) — only the
   status-transition stops, each with dwell time — swapped **out-of-band** into
   `#lifecycle-slot` at the top of the modal scroll region (`hx-swap-oob`).
2. The full **audit trail** (`_shape_audit`) — a field-by-field change log —
   rendered in place where the section sits.

Even total failure is `200`: a failed `bd history` renders a friendly
"temporarily unavailable" panel (with neither view) rather than breaking the
already-open modal.

**`GET /api/bead/{bead_id}/raw` → `200 OK`, JSON**
(`JSONResponse`). The unshaped `bd show --long --json` object for the bead — the
exact dict the modal renders from, with nothing hidden or reordered.

> [!IMPORTANT]
> The lifecycle timeline and the audit trail cost **one** `bd history`
> subprocess between them. `/audit` fetches once, then `derive.status_timeline`
> and `_shape_audit` both consume that in-memory payload. This respects the
> single-writer Dolt gate and keeps the modal cheap — see
> [Concept: bd CLI as runtime source of truth](../Concepts/bd-cli-source-of-truth.md).

### Errors

| Status | When | Body |
| --- | --- | --- |
| `404` | `/api/bead/{id}`: neither the live `bd show` nor the cached snapshot can find the bead. | `<div class="modal-error">We couldn't find that bead. Please refresh the board and try again.</div>` |
| `200` (degraded) | `/api/bead/{id}`: live read failed but the snapshot has the bead. | The full modal, `source="Cached snapshot"`, plus a `warning` banner: "Showing cached details while live data is temporarily unavailable." |
| `200` (degraded) | `/api/bead/{id}/audit`: `bd history` failed. | The audit partial's error branch: "Audit history is temporarily unavailable." — no timeline, no trail; the rest of the modal is untouched. |
| `200` (empty) | `/api/bead/{id}/audit`: history is an empty list. | "no recorded history yet" note; no lifecycle timeline rendered. |
| `200` (error payload) | `/api/bead/{id}/raw`: live read failed and the bead isn't cached. | `{"error": "<bd error>"}` (or `"not found"`) — still HTTP `200`, JSON, so debugging tooling gets a parseable shape. |

> [!WARNING]
> Only the detail endpoint's "missing bead" case is a real `404`. Every other
> failure degrades to `200` with a friendly partial. This is intentional: once
> the modal is open, a backend hiccup must never blank it out — the user keeps
> whatever already rendered, and the failing region shows an inline "try again
> later" note instead of an HTTP error the browser would surface as a broken
> swap.

## Implementation Map

| Concern | Where |
| --- | --- |
| Detail handler | [`src/bdboard/app.py:api_bead`](../../src/bdboard/app.py) |
| Audit handler | [`src/bdboard/app.py:api_bead_audit`](../../src/bdboard/app.py) |
| Raw handler | [`src/bdboard/app.py:api_bead_raw`](../../src/bdboard/app.py) |
| Live detail read | [`src/bdboard/bd.py:BdClient.show_long`](../../src/bdboard/bd.py) (`bd show {id} --long --json`, cached) |
| History read | [`src/bdboard/bd.py:BdClient.history`](../../src/bdboard/bd.py) (`bd history {id} --json`, cached) |
| Snapshot fallback | [`src/bdboard/store.py:Store.snapshot` / `Store.bead`](../../src/bdboard/store.py) |
| Field ordering + render/edit hints | [`src/bdboard/app.py:_ordered_fields` / `_field_row` / `_FIELD_ORDER`](../../src/bdboard/app.py) |
| Audit diffing | [`src/bdboard/app.py:_shape_audit` / `_diff_issue`](../../src/bdboard/app.py) |
| Lifecycle timeline | [`src/bdboard/derive/history.py:status_timeline`](../../src/bdboard/derive/history.py) |
| Modal template | [`partials/bead_modal.html`](../../src/bdboard/templates/partials/bead_modal.html) |
| Audit/lifecycle template | [`partials/bead_audit.html`](../../src/bdboard/templates/partials/bead_audit.html) |
| Field row template | [`partials/field_row.html`](../../src/bdboard/templates/partials/field_row.html) |
| Card trigger | [`partials/bead_card.html`](../../src/bdboard/templates/partials/bead_card.html) (`hx-get="/api/bead/{id}"`, `hx-target="#bead-modal"`) |
| Modal host + instant skeleton | [`templates/base.html`](../../src/bdboard/templates/base.html) (`#bead-modal`, `#bead-modal-skeleton`) |

> [!IMPORTANT]
> `_ordered_fields` walks `_FIELD_ORDER` first (identity → content → meta →
> bulk), then appends any unlisted keys alphabetically. That trailing alpha pass
> is the guardrail: a **new bd field never silently disappears** from the modal —
> it shows up at the bottom even before anyone curates its position. The detail
> endpoint therefore stays correct as bd's schema grows.

## Diagram

```mermaid
sequenceDiagram
    actor User
    participant Card as bead_card.html
    participant App as app.py
    participant BD as BdClient (bd.py)
    participant Store as Store snapshot

    User->>Card: click bead card
    Card->>App: GET /api/bead/{id}  (hx-target=#bead-modal)
    App->>BD: show_long(id)  %% bd show --long --json
    alt live read ok
        BD-->>App: full bead
    else live read fails
        App->>Store: snapshot() / bead(id)
        Store-->>App: cached bead (source="Cached snapshot")
    end
    App-->>Card: 200 bead_modal.html (with empty #lifecycle-slot)

    Note over Card: modal shell painted; audit section fires on load
    Card->>App: GET /api/bead/{id}/audit  (hx-trigger=load)
    App->>BD: history(id)  %% bd history --json (one call)
    BD-->>App: snapshots (newest first)
    App->>App: status_timeline(entries) + _shape_audit(entries)
    App-->>Card: 200 audit trail + OOB lifecycle into #lifecycle-slot

    opt debug
        User->>App: GET /api/bead/{id}/raw (raw JSON link)
        App->>BD: show_long(id)
        BD-->>App: full bead
        App-->>User: 200 application/json (unshaped)
    end
```

## curl example

```sh
# 1. Render the detail modal partial (HTML).
curl -s http://127.0.0.1:7332/api/bead/bdboard-mol-gh2

# 2. Render the lifecycle timeline + audit trail (HTML; OOB lifecycle slot).
curl -s http://127.0.0.1:7332/api/bead/bdboard-mol-gh2/audit

# 3. Dump the raw, unshaped bead JSON — the debug escape hatch.
curl -s http://127.0.0.1:7332/api/bead/bdboard-mol-gh2/raw | jq .

# Unknown id: detail 404s with a friendly partial; raw returns {"error": ...}.
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7332/api/bead/nope
curl -s http://127.0.0.1:7332/api/bead/nope/raw | jq .
```

> [!CAUTION]
> `/raw` is a debug aid, not a stable API. It returns whatever shape
> `bd show --long --json` currently emits — field names and nesting can change
> with the bd version. Don't build client code against it; consume the curated
> modal partial (or the typed `BdClient` methods) instead. It exists so a
> maintainer can see fields the modal layout hides, nothing more.

## Testing

- [`tests/test_api_bead_audit.py`](../../tests/test_api_bead_audit.py) covers
  `/api/bead/{id}/audit` end to end with a stubbed `bd.history`:
  `test_lifecycle_timeline_renders_transitions_and_dwell` (both views render
  from one payload, dwell time computed, current status open-ended),
  `test_audit_error_skips_both_views` (a history error degrades to the
  "temporarily unavailable" panel with no timeline), and
  `test_no_history_shows_empty_note_without_timeline` (empty history → "no
  recorded history yet", no timeline).
- [`tests/test_derive_history.py`](../../tests/test_derive_history.py) unit-tests
  the lifecycle source, `status_timeline`:
  `test_status_timeline_empty_input`,
  `test_status_timeline_collapses_to_transitions_oldest_first`,
  `test_status_timeline_computes_dwell_hours`, and
  `test_status_timeline_skips_blank_status`.
- [`tests/test_api_history.py`](../../tests/test_api_history.py) asserts the
  board renders cards wired to open this modal
  (`hx-get="/api/bead/xyz"`), confirming the card→detail trigger contract.
- [`tests/test_field_edit_status_gate.py`](../../tests/test_field_edit_status_gate.py)
  exercises the `/api/bead/{id}` render path under various statuses to verify the
  modal exposes (or hides) edit affordances correctly — the read endpoint's
  editability hints in action.

> [!WARNING]
> There is currently no dedicated test asserting the `/api/bead/{id}` 404 / cached
> degradation branches or the `/api/bead/{id}/raw` error payload in isolation;
> those paths are covered indirectly (the audit suite and field-edit gate render
> the modal, `status_timeline` is unit-tested). A focused regression test for the
> detail-endpoint fallback and the raw error shape would tighten coverage.

## Related

- [Bead field-edit API](bead-field-edit-api.md) — the write half; consumes the editable field rows this endpoint renders.
- [Feature: Bead detail & inline editing](../Features/bead-detail-and-inline-editing.md) — the capability these endpoints power.
- [Flow: Inline field-edit write path](../Flows/field-edit-write-path.md) — what happens after a field rendered here is edited.
- [SSE events](sse-events.md) — the `beads_changed` stream that prompts the board (and re-opened modals) to refresh.
- [View: Board page](../Views/board-page.md) — hosts the `#bead-modal` target and the cards that open it.
- [Concept: bd CLI as runtime source of truth](../Concepts/bd-cli-source-of-truth.md) — why detail/history reads are `bd` subprocesses.
- [Concept: Store snapshot cache & change detection](../Concepts/store-snapshot-cache.md) — the cached snapshot the detail endpoint falls back to.
- [Concept: Derive layer (pure view shaping)](../Concepts/derive-layer.md) — where `status_timeline` lives and why shaping stays pure.
- [Concept: HTMX + server-rendered partials](../Concepts/htmx-partials-architecture.md) — the partial swap + out-of-band `#lifecycle-slot` idiom this modal uses.
