# FlowDoc Authoring Guide (the doc-bead contract)

> **Audience for the generated docs: maintainers.** Every doc bead spawned from
> the FlowDoc maintainer epic MUST follow the template for its type, verbatim in
> shape, so output is consistent regardless of which agent writes it.

## Core rules (encode these in every doc)

1. **Features, not files.** Document what the system *does*, organized by
   capability — not a file-by-file inventory.
2. **Flows, not functions.** Describe end-to-end behavior and data movement,
   not a call-graph of every helper.
3. **Why over what.** Always explain *why* a thing exists / is shaped this way,
   not just the mechanics.
4. **Link every reference.** Every mentioned doc, ADR, source module, or related
   feature gets a relative markdown link.
5. **Mermaid for flows.** Use mermaid `sequenceDiagram` / `flowchart` /
   page-structure diagrams wherever a process or structure is described.
6. **Callouts for gotchas.** Use GitHub callouts: `> [!WARNING]` for edge cases,
   `> [!IMPORTANT]` for conventions, `> [!CAUTION]` for anti-patterns.
7. **Source is READ-ONLY.** Read the relevant source fresh; never modify code
   while writing docs.
8. **Output only under `__docs/`.** Write nothing outside the docs dir.
   Maintainer audience ⇒ `__docs/`. (User audience would be `_docs/`.)
9. **No placeholders.** Every template section must be filled with real content.
   No "TODO", no "TBD", no empty headings.
10. **Update the manifest.** After writing a doc, tick its `- [ ]` → `- [x]` in
    [`_Manifest.md`](./_Manifest.md) and bump the progress counters.

Acceptance for any doc bead: file exists at the manifest's stated path; all
template sections present and filled (no placeholders); links valid; manifest
checkbox + counters updated.

---

## Template — Feature

```markdown
# Feature: <Name>

## What it does
One-paragraph plain statement of the capability.

## Why it exists
The problem it solves / the user need behind it.

## How it works
### User perspective
What the user sees and does.
### System perspective
What happens server-side, step by step.

## Sequence
​```mermaid
sequenceDiagram
    actor User
    User->>bdboard: action
    bdboard->>bd: subprocess
​```

## Implementation Map
| Concern | Where | Notes |
| --- | --- | --- |
| Route | `src/bdboard/app.py:<fn>` | ... |
| Template | `templates/...` | ... |
| Logic | `src/bdboard/...` | ... |

## Config
Env vars / flags / constants that change behavior (with defaults).

## Edge Cases
> [!WARNING]
> Notable edge cases and how they're handled.

## Error Scenarios
What fails, what the user sees, how the system degrades.

## Testing
Which tests cover this (`tests/...`) and what they assert.

## Related
- [Other doc](../Section/Name.md)
- ADR / README links
```

---

## Template — Flow

```markdown
# Flow: <Name>

## What happens
One-paragraph summary of the end-to-end process.

## Trigger
What initiates the flow.

## Outcome
The end state once the flow completes.

## Diagram
​```mermaid
flowchart TD
    A[Trigger] --> B[Step] --> C[Outcome]
​```

## Step-by-step
| # | What | Where | Failure mode |
| --- | --- | --- | --- |
| 1 | ... | `src/bdboard/...` | ... |

## Data Transformations
How the data is shaped as it moves through the flow (raw → derived → rendered).

## Failure Handling
What happens when a step fails; retries, degradation, logging.

## Debugging
How to observe/trace this flow (logs, signals, endpoints, tests).

## Related
- [Other doc](../Section/Name.md)
```

---

## Template — Endpoint (maintainer only)

```markdown
# Endpoint: <Name>

## Overview
| METHOD | Path | Purpose |
| --- | --- | --- |
| GET | `/api/...` | ... |

## Request
### Headers
| Header | Required | Notes |
### Params / Query
| Name | Type | Required | Default | Validation |
### Body
| Field | Type | Required | Validation |

## Response
### Success
Status code + shape (HTML partial / JSON) + what it renders.
### Errors
| Status | When | Body |

## Implementation Map
| Concern | Where |
| --- | --- |
| Handler | `src/bdboard/app.py:<fn>` |

## Diagram
​```mermaid
sequenceDiagram
    Client->>app.py: METHOD path
    app.py->>Store: snapshot
​```

## curl example
​```sh
curl -s http://127.0.0.1:7332/api/...
​```

## Related
- [Other doc](../Section/Name.md)
```

---

## Template — View (maintainer only)

```markdown
# View: <Name>

## Route
| Path | Handler | Template |
| --- | --- | --- |
| `/` | `app.py:<fn>` | `templates/<file>.html` |

## What it does
What the page presents and why.

## User actions
What the user can do on this page.

## Page structure
​```mermaid
flowchart TD
    Page --> Header
    Page --> Body
​```

## Components / partials
| Partial | Purpose |
| --- | --- |
| `partials/...` | ... |

## State
Client/server state this view depends on (query params, theme, SSE).

## API dependencies
| Endpoint | Used for |
| --- | --- |

## Related
- [Other doc](../Section/Name.md)
```

---

## Template — Concept

```markdown
# Concept: <Name>

## What is it
Definition in one or two sentences.

## Why this approach
The rationale / alternatives rejected.

## How it works
Mechanics, with a concrete example.

​```python
# minimal illustrative example
​```

## Where used
| Consumer | How |
| --- | --- |

## Conventions
> [!IMPORTANT]
> The conventions to follow when touching this.

## Anti-patterns
> [!CAUTION]
> What NOT to do, and why.
```

---

## Template — User Guide (user edition only — not used by this maintainer epic)

```markdown
# How to: <Goal>

## Goal
What you'll accomplish.

## Prerequisites
What you need first.

## Steps
1. Do this — *expected result: ...*
2. Then this — *expected result: ...*

## Troubleshooting
| Symptom | Fix |

## Related
- [Other guide](Name.md)
```

> [!IMPORTANT]
> The User Guide template has NO code and NO file paths by design. It is listed
> here for completeness; the maintainer epic (this one) uses the Feature / Flow
> / Endpoint / View / Concept templates above.
