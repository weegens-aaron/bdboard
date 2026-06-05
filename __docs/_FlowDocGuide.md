# _FlowDocGuide — Authoring Contract (audience: maintainer)

This is the **sole carrier** of template/section/naming fidelity for the
bdboard maintainer documentation set. There is no external "flowdoc" skill —
every doc bead reads THIS file and reproduces output identical in *shape*
(section order, table column headers, mermaid scaffolds, callout markers,
naming) to the templates below.

Document **what the code DOES**, not a file inventory. Prefer
features-not-files, flows-not-functions, why-over-what, behavior-first framing.

## Global rules (every doc bead enforces these)

1. **Features, not files.** Lead with behavior and purpose.
2. **Flows, not functions.** Describe the journey end to end.
3. **Why over what.** Explain the problem each thing solves.
4. **Behavior-first framing.** Start each doc with observable behavior.
5. **Link every reference bidirectionally.** If A links to B, B links back to A.
6. **Mermaid for every flow/sequence.** Each flow/endpoint/view gets the
   diagram(s) its template calls for.
7. **Callouts for gotchas.** Use `> [!NOTE]`, `> [!WARNING]`,
   `> [!IMPORTANT]`, `> [!CAUTION]` Markdown alert markers.
8. **READ-ONLY source.** Read the relevant source fresh; never modify it.
9. **Output only under `__docs/`.** Never write elsewhere.
10. **No placeholders.** Fill every section + table with real values: real
    field names in JSON skeletons, real `file:symbol` rows in impl maps.
11. **Naming (N1).** Section DIRS and item FILE names are BOTH PascalCase
    (e.g. `Features/LiveBoard.md`). The manifest link target and the actual
    filename must agree exactly.

---

## Feature (maintainer)

```markdown
# <Name>

## What It Does
(1-2 sentences, behavior-first)

## Why It Exists
(the problem it solves)

## How It Works

### User Perspective
(what the user sees/does)

### System Perspective
(what the code does end to end)

```mermaid
sequenceDiagram
    (the request/interaction sequence)
```

## Key Data Shapes
(DTO / request / response JSON skeletons in fenced ```json blocks — real field names)

## API Surface

| Method | Path | Purpose | -> Endpoint doc |
| --- | --- | --- | --- |

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |

## Configuration

| Key | Default | Effect |
| --- | --- | --- |

## Edge Cases
> [!WARNING]
> (one per edge case)

## Error Scenarios

| Trigger | Behavior | User sees |
| --- | --- | --- |

## Testing
(how it's tested / how to test)

## Related
(bidirectional links to flows/endpoints/views)
```

---

## Flow (maintainer)

```markdown
# <Name>

## What Happens
## Trigger
## Outcome

```mermaid
flowchart TD
    (the step graph)
```

## Step-by-Step

| # | What | Where (file:symbol) | Failure mode |
| --- | --- | --- | --- |

## Data Transformations
(input -> output at each hop)

## Performance Characteristics
(latency/throughput/N+1 notes, sync vs async)

## Failure Handling
(retries, timeouts, compensation)

## Key Log Messages

| Log line | Where | Means |
| --- | --- | --- |

## Common Issues

| Symptom | Likely cause | Fix |
| --- | --- | --- |

## Related
```

---

## Endpoint (maintainer only)

```markdown
# <METHOD> <path>

## Overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |

## Request

### Path/Query Params

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |

### Headers

| Header | Required | Notes |
| --- | --- | --- |

### Body
```json
(request skeleton)
```

### Validation Rules

| Field | Rule | Error |
| --- | --- | --- |

### Rate Limit

| Limit | Window | Scope |
| --- | --- | --- |

## Response

### Success
(status + fenced ```json response skeleton)

### Errors

| Status | Code | When |
| --- | --- | --- |

## Implementation Map

| Responsibility | File path | Symbol |
| --- | --- | --- |

```mermaid
sequenceDiagram
    (client -> handler -> store)
```

## Example
(a real `curl` invocation with headers + body)

## Related
```

---

## View (maintainer only)

```markdown
# <Name> (<route>)

## Overview

| Route | Auth | Purpose |
| --- | --- | --- |

## URL Params

| Param | Type | Required | Notes |
| --- | --- | --- | --- |

## What It Does
## User Actions

```mermaid
flowchart TD
    (page structure / component tree)
```

## Components

| Component | Responsibility | File |
| --- | --- | --- |

## State Management

| State | Source | Updated by |
| --- | --- | --- |

## Data Flow
```mermaid
sequenceDiagram
    (view <-> API)
```

## API Dependencies

| Endpoint | Used for | -> Endpoint doc |
| --- | --- | --- |

## States
(Loading / Empty / Error states described)

## Accessibility
(keyboard, ARIA, focus, contrast notes)

## Responsive Behavior
(breakpoint behavior)

## Related
```

---

## Concept (maintainer)

```markdown
# <Name>

## What Is It
## Why This Approach

## How It Works
(+ a concrete example)

## Where Used
(links to features/flows that rely on it)

## Conventions
> [!IMPORTANT]
> (the rules to follow)

## Anti-Patterns
> [!CAUTION]
> (what not to do)

## Related
```

---

## bdboard cheat-sheet (so doc beads survey the right places fast)

- **Tech stack:** Python ≥3.11, FastAPI, Jinja2 + HTMX (server-rendered
  partials), Server-Sent Events, `watchfiles`, Typer CLI, `uvicorn`,
  `markdown-it-py`. No JS framework, no client build step.
- **Source of truth:** the `bd` (beads) CLI over a Dolt DB. bdboard is a
  read-mostly OBSERVER — it shells out to `bd ... --json` and never writes
  `.beads/` except via `bd` mutation commands (remember/forget/update/pour).
- **Layering:** `cli.py` (entry/port/launch) -> `app.py` (FastAPI routes) ->
  `store.py` (snapshot cache + change detection) -> `bd.py` (subprocess
  client, semaphore-gated, cached) -> `derive/` (pure view shaping) ->
  `templates/` (Jinja + HTMX) + `static/styles.css`. `watcher.py` debounces
  filesystem events; `events.py` is the SSE pub/sub bus; `md.py` renders
  Markdown safely.
- **Endpoints:** all live in `src/bdboard/app.py` as `@app.get/post/delete`.
- **Views (pages):** `/` (dashboard.html), `/history` (history.html),
  `/memory` (memory.html) — each a cheap shell hydrated by HTMX partials.
- **BE<->FE linkage:** pages issue `hx-get`/`hx-post` to `/api/*`. The board
  shell loads `/api/counts` + `/api/lanes` (then `/api/lanes/closed`); the
  bead modal loads `/api/bead/{id}` then `/api/bead/{id}/audit`; field edits
  POST `/api/bead/{id}/field`; the History page hits `/api/history`; Memory
  hits `/api/memory` (+ POST/DELETE); formulas hit `/api/formulas*`; and
  every page subscribes once to `/api/events` (EventSource) which fires
  `refresh from:body` HTMX re-fetches.
