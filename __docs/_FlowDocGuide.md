# FlowDoc Authoring Guide (maintainer edition)

> This is the **authoring contract** every maintainer doc bead follows. It is
> the SOLE carrier of template/section/naming fidelity (there is no external
> "flowdoc" skill). Reproduce the templates below **verbatim in shape** —
> section order, table column headers, mermaid scaffolds, callout markers, and
> PascalCase naming. Do not paraphrase the templates into a bare section list.

## Audience & Output Rules

- **Audience:** maintainers (developers). Include implementation detail, file
  paths, mermaid diagrams, API/View tables.
- **DOCS_DIR:** `__docs/` (this directory). Output **only** under `__docs/`.
- **Source is READ-ONLY.** Never modify source while documenting.

## Authoring Principles (encode these in every doc)

- **Features, not files** — document what the code *does*, not a file inventory.
- **Flows, not functions** — narrate end-to-end behavior.
- **Why over what** — explain the problem each thing solves.
- **Behavior-first framing** — lead with observable behavior.
- **Link every reference bidirectionally** — related docs link back.
- **Mermaid for every flow/sequence.**
- **Callouts for gotchas:** `> [!NOTE]`, `> [!WARNING]`, `> [!IMPORTANT]`,
  `> [!CAUTION]`.
- **Naming (N1):** section DIRS and item FILE names are BOTH PascalCase
  (e.g. `Features/SwimLaneBoard.md`); manifest link target == actual filename.

## Templates

### Feature (maintainer)

```markdown
# <Name>
## What It Does            (1-2 sentences, behavior-first)
## Why It Exists           (the problem it solves)
## How It Works
  ### User Perspective     (what the user sees/does)
  ### System Perspective   (what the code does end to end)
```mermaid
sequenceDiagram            (the request/interaction sequence)
```
## Key Data Shapes         (DTO / request / response JSON skeletons in
                            fenced ```json blocks — real field names)
## API Surface             (table | Method | Path | Purpose | -> Endpoint doc)
## Implementation Map      (table | Responsibility | File path | Symbol |)
## Configuration           (table | Key | Default | Effect |)
## Edge Cases              (> [!WARNING] one per edge case)
## Error Scenarios         (table | Trigger | Behavior | User sees |)
## Testing                 (how it's tested / how to test)
## Related                 (bidirectional links to flows/endpoints/views)
```

### Flow (maintainer)

```markdown
# <Name>
## What Happens / ## Trigger / ## Outcome
```mermaid
flowchart TD               (the step graph)
```
## Step-by-Step            (table | # | What | Where (file:symbol) | Failure mode |)
## Data Transformations    (input -> output at each hop)
## Performance Characteristics  (latency/throughput/N+1 notes, sync vs async)
## Failure Handling        (retries, timeouts, compensation)
## Key Log Messages        (table | Log line | Where | Means |)
## Common Issues           (table | Symptom | Likely cause | Fix |)  (debugging)
## Related
```

### Endpoint (maintainer only)

```markdown
# <METHOD> <path>
## Overview                (table | Method | Path | Auth | Purpose |)
## Request
  ### Path/Query Params    (table | Name | In | Type | Required | Notes |)
  ### Headers              (table | Header | Required | Notes |)
  ### Body                 (fenced ```json request skeleton)
  ### Validation Rules     (table | Field | Rule | Error |)
  ### Rate Limit           (one row: limit / window / scope)
## Response
  ### Success              (status + fenced ```json response skeleton)
  ### Errors               (table | Status | Code | When |)
## Implementation Map      (table | Responsibility | File path | Symbol |)
```mermaid
sequenceDiagram            (client -> handler -> store)
```
## Example                 (a real `curl` invocation with headers + body)
## Related
```

### View (maintainer only)

```markdown
# <Name> (<route>)
## Overview                (table | Route | Auth | Purpose |)
## URL Params              (table | Param | Type | Required | Notes |)
## What It Does / ## User Actions
```mermaid
flowchart TD               (page structure / component tree)
```
## Components              (table | Component | Responsibility | File |)
## State Management        (table | State | Source | Updated by |)
## Data Flow               (a mermaid sequenceDiagram: view <-> API)
## API Dependencies        (table | Endpoint | Used for | -> Endpoint doc |)
## States                  (Loading / Empty / Error states described)
## Accessibility           (keyboard, ARIA, focus, contrast notes)
## Responsive Behavior     (breakpoint behavior)
## Related
```

### Concept (maintainer)

```markdown
# <Name>
## What Is It / ## Why This Approach
## How It Works            (+ a concrete example)
## Where Used              (links to features/flows that rely on it)
## Conventions             (> [!IMPORTANT] the rules to follow)
## Anti-Patterns           (> [!CAUTION] what not to do)
## Related
```

## Acceptance for any doc bead

- File exists at the **PascalCase** path under the correct section dir.
- **Every** template section and table is filled — no placeholders, real column
  values, real JSON field names, real `file:symbol` impl-map rows.
- The mermaid diagram(s) the template calls for are present.
- Related links resolve and are bidirectional.
- The matching `_Manifest.md` item is ticked `- [x]` and counters bumped.
