# How to manage project memories

## What You'll Learn

How to open the Memory screen, search your project's saved notes, add a new one,
edit an existing one, and safely remove one.

## Prerequisites

- bdboard running with your project open — see the
  [Quick Start](../Getting-Started/QuickStart.md).

## Overview

**Memories** are short, named notes your project keeps — conventions, gotchas,
decisions worth remembering. The Memory screen lets you browse, search, and
maintain them. Each memory has a **key** (a short identifier) and a **body** (the
note itself, in markdown).

## Step 1: Open Memory

In the top bar, click **Memory**.

**Expected result:** the Memory screen opens listing every saved memory, with a
count and a search box at the top.

## Step 2: Search

Type in the **Search memories** box. The list filters as you type.

**Expected result:** the list narrows to memories matching your text, and the
count updates to "N matching ...". Clear the box to see everything again.

## Step 3: Add a memory

Click **+ New Memory**. In the dialog, enter a short **Key** and the **Body**,
then click **Save Memory**.

**Expected result:** the dialog closes and your new memory appears in the list.

> [!TIP]
> Keep keys short and slug-like (for example `dev-workflow`). If you save with a
> key that already exists, the body is updated instead of creating a duplicate.

## Step 4: Edit a memory

On a memory card, click the edit button. The dialog opens pre-filled. Change the
body and click **Save Memory**.

**Expected result:** the card updates with your new body. The key stays fixed —
you can't rename a key by editing; save under a new key instead.

## Step 5: Remove a memory

On a memory card, click the forget button. A confirmation dialog appears. Read
the warning, then click **Yes, Forget It** to confirm (or **Cancel** to keep
it).

**Expected result:** the memory is permanently removed from the list.

> [!WARNING]
> Forgetting a memory is permanent and can't be undone. Memories are surfaced to
> the people and tools working on your project, so removing one can quietly take
> away context others relied on. Confirm only when you're sure.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Search shows nothing | Clear the box to confirm memories exist; if the list is empty, add one with **+ New Memory**. |
| My new memory replaced an old one | The key already existed — saving an existing key updates its body. Use a different key to keep both. |
| I can't change the key when editing | Keys are fixed on edit. Create a new memory under the desired key instead. |
| The list looks out of date | The screen updates live as memories change in any tab; reopen Memory if needed. |

## Related Guides

- [Pour a formula](PouringAFormula.md)
- [View your work on the board](ViewingYourWork.md)
- Reference: [The memory screen](../Reference/MemoryScreen.md)
- Concept: [Live updates](../Concepts/LiveUpdates.md)
