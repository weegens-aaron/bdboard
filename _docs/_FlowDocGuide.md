# FlowDoc Authoring Guide (user edition)

> This is the authoring contract every user-doc page in `_docs/` follows. It
> exists so a generic agent (or a human) reproduces output identical in **shape**
> to the FlowDoc user agent: same Diataxis grouping, same section order, same
> callout markers, same naming. Author pages from the templates below; do not
> paraphrase a template into a bare list of section names.

## Audience & scope

These docs are for **people who use bdboard**, not people who build it. bdboard
is a small developer tool you run locally; it opens a board in your browser that
shows your project's work items (called *beads*) and keeps itself up to date.

`_docs/` is the **user edition**. The developer edition lives in `__docs/` and is
not for end users.

## The leakage rule (applies to EVERY page, always)

Describe the product the way a user experiences it. On every page:

- **No** source file paths, module names, class names, or function names.
- **No** code, shell, or implementation snippets — *except* the commands a user
  genuinely types to install and launch the tool, which belong only on the
  Getting-Started / Installation page (this product is installed locally).
- **No** internal issue IDs, no dev/staging URLs.
- Describe the **UI the user sees** ("the Ready lane", "click a card", "the
  range buttons"), never the implementation behind it.

## The 7 writing rules

1. **Second person.** "You click", "you'll see" — never "the user".
2. **Active voice; imperative steps.** "Click Submit", not "Submit can be clicked".
3. **Show, don't tell.** Describe exactly what appears on screen.
4. **One idea per paragraph.** Keep paragraphs short.
5. **Use callouts** for tips and gotchas: `> [!TIP]`, `> [!NOTE]`, `> [!WARNING]`.
6. **State the expected result after every step** — what the user should see next.
7. **Link generously and bidirectionally** between related pages.

## Diataxis grouping

User docs are classified by the [Diataxis](https://diataxis.fr) framework. Each
group lives in its own PascalCase directory; each page file is PascalCase too,
and the manifest link target must equal the filename exactly.

| Group | Directory | Answers |
|-------|-----------|---------|
| Getting-Started | `Getting-Started/` | "How do I begin?" |
| Guides (how-to) | `Guides/` | "How do I do task X?" |
| Tutorials | `Tutorials/` | "Walk me through a real scenario." |
| Reference | `Reference/` | "What does this screen/control do?" |
| Concepts | `Concepts/` | "Why does it work this way?" |
| FAQ | `FAQ.md` (root) | "Quick answers." |

## Templates

### Getting-Started page

```
# Quick Start: <achieve a first concrete outcome>
## What You'll Achieve   (the end result in one line)
## Prerequisites         (account / access / device — user-facing only)
## Step 1..N: <action>   (numbered; each step = ONE user action plus the
                          expected result; use Option A / Option B for branches)
## Common Issues         (table | Symptom | What to do |)
## What You Learned / ## Next Steps   (links onward to Guides/Tutorials)
```

> An Installation page exists in this group **only because bdboard is installed
> locally**. A URL-accessed product would lead with an "Accessing <Product>"
> page instead.

### Guide / How-To page

```
# How to <task>
## What You'll Learn / ## Prerequisites
## Overview              (1-2 sentences of context)
## Step 1..N: <sub-task> (numbered actions, each with its expected result;
                          nest bullet sub-actions per step)
## Troubleshooting       (table | Problem | Fix |)
## Related Guides        (bidirectional links)
```

### Tutorial page

```
# Tutorial: <end-to-end scenario>
## What You'll Achieve / ## Before You Begin / ## The Scenario
## Step 1..N: <action>   (narrative walkthrough showing expected screens; cover
                          success + the error branches a user may hit)
## Final Result / ## What You Learned / ## Next Steps
```

### Reference page

```
# <Subject> Reference
## Overview
## <grouped reference sections>  (screens, controls, buttons, fields as
                                  tables | Item | What it does |)
## Tips / ## See Also
```

### Concept page

```
# <Concept in plain language>
## What Is It / ## Why It Matters
## How It Works          (plain language, analogy-friendly, no code)
## Related
```

### FAQ (the finalize step writes/refreshes this)

```
# Frequently Asked Questions
grouped by theme (Getting Started / Troubleshooting / Common Tasks),
each entry a "### <question>" heading + a short answer.
```

## Naming

Section directories and page files are **both PascalCase**
(e.g. `Guides/ViewingYourWork.md`). The manifest link target and the actual
filename must agree exactly.
