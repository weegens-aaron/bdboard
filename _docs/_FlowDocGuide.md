# FlowDoc Authoring Guide (the doc-bead contract)

> **Audience for the generated docs: users.** Every doc bead spawned from the
> FlowDoc **user** epic MUST follow the template for its type, verbatim in
> shape, so output is consistent regardless of which agent writes it.

## Core rules (encode these in every doc)

1. **Features, not files.** Document what bdboard *does*, organized by
   capability — not a file-by-file inventory.
2. **Flows, not functions.** Describe end-to-end behaviour the user experiences,
   not a call-graph of helpers.
3. **Why over what.** Always explain *why* a thing exists / behaves this way,
   not just the mechanics.
4. **Link every reference.** Every mentioned doc or related topic gets a
   relative markdown link.
5. **Mermaid for flows.** Use mermaid `flowchart` / `sequenceDiagram` wherever a
   process or structure is described. (User edition: keep diagram labels in
   plain language — screens and actions, not function names.)
6. **Callouts for gotchas.** Use GitHub callouts: `> [!WARNING]` for edge cases,
   `> [!IMPORTANT]` for conventions, `> [!CAUTION]` for anti-patterns.
7. **Source is READ-ONLY.** Read the relevant source fresh to get the facts
   right; never modify code while writing docs.
8. **Output only under `_docs/`.** Write nothing outside the docs dir.
   User audience ⇒ `_docs/`. (Maintainer audience would be `__docs/`.)
9. **No placeholders.** Every template section must be filled with real content.
   No "TODO", no "TBD", no empty headings.
10. **Update the manifest.** After writing a doc, tick its `- [ ]` → `- [x]` in
    [`_Manifest.md`](./_Manifest.md) and bump the progress counters.

Acceptance for any doc bead: file exists at the manifest's stated path; all
template sections present and filled (no placeholders); links valid; manifest
checkbox + counters updated.

---

> [!IMPORTANT]
> ## USER-EDITION OVERRIDES — read before you write
>
> This is the **user** edition. The doc beads in this epic use only three of the
> templates below: **Feature**, **Concept**, and **User Guide**. The
> **Endpoint** and **View** templates are *maintainer-only* and are reproduced
> here solely so the contract is complete — do not author them in this epit.
>
> For the **user** edition, apply these overrides to the verbatim templates:
>
> - **No file paths. No code. No internal symbol names.** Never write
>   `src/...`, a function name, a class name, an env-var, a `curl` command, or a
>   `localhost`/staging URL. Talk about *screens*, *buttons*, and *what the user
>   sees*.
> - In the **Feature** template, **replace the "Implementation Map" table and
>   the "Sequence" code with plain language**: use a *"Where you'll find it"*
>   note (which page / which part of the screen) instead. The mermaid diagram, if
>   used, shows the *user's* steps, not server internals.
> - In the **Feature** template, fold "Testing" into a plain *"Good to know"*
>   note (or omit) — users don't run the test suite.
> - In the **Concept** template, **drop the code example**; explain with a
>   real-world analogy or a plain worked example instead.
> - The **User Guide** template is the workhorse for task how-tos: numbered
>   steps, each with an *expected result*, plus a Troubleshooting table.
> - Default port and addresses, when you must mention them, come from what the
>   app prints on screen — describe "the address shown in your terminal / the tab
>   that opens", not a hard-coded number.

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
What happens behind the scenes, in plain language (no file paths / code).

## Sequence
​```mermaid
sequenceDiagram
    actor User
    User->>bdboard: action
    bdboard-->>User: result
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

> [!IMPORTANT]
> **User-edition Feature:** replace **Implementation Map** with a plain
> *"Where you'll find it"* note (page + part of the screen), keep **Sequence**
> in plain-language user steps, drop **Config** unless it's a user-facing option
> (like a command-line flag described in words), and rename **Testing** to a
> short *"Good to know"* note or omit it. No file paths, no code.

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

> [!IMPORTANT]
> **Flow is not authored in the user edition.** User-facing processes are
> documented as actionable **User Guides** instead (see below). This template is
> here for contract completeness only.

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

> [!CAUTION]
> **Maintainer-only.** Do NOT author Endpoint docs in the user edition — they
> expose paths, headers, and `curl` commands that violate the no-developer-leakage
> rule. Reproduced here for contract completeness only.

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

> [!CAUTION]
> **Maintainer-only.** Do NOT author View docs in the user edition — they expose
> routes, template paths, and partial names. The *user-visible* aspects of each
> page are covered by the relevant **Feature** and **User Guide** docs instead.

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

> [!IMPORTANT]
> **User-edition Concept:** **drop the code example** — explain with a
> real-world analogy or a plain worked example. Replace "Where used" with a
> plain *"Where it shows up"* note (which screens it affects). Keep
> **Conventions** as plain *"Good habits"* and **Anti-patterns** as *"Things to
> avoid"* — phrased for someone *using* bdboard, not editing its code.

---

## Template — User Guide (user edition — the primary template here)

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
> The User Guide template has NO code and NO file paths by design. It is the
> workhorse of this **user** epic alongside **Feature** and **Concept**.
