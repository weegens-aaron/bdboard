# How to edit a bead's fields

## What You'll Learn

How to change a field on an open item right from its detail panel, how to add a
note without overwriting the history, and why some fields can't be edited.

## Prerequisites

- bdboard running with your project open — see the
  [Quick Start](../Getting-Started/QuickStart.md).
- The item you want to change is still **open** (editing is only offered on open
  items).

## Overview

bdboard lets you fix small things in place — a priority, an assignee, a
description — without leaving the board. You open the item, expand the field you
want to change, type the new value, and save. The card and counts update live.

## Step 1: Open the item

Click the card to open its detail panel. See
[Inspect a bead in detail](InspectingABead.md) for the full tour.

**Expected result:** the detail panel opens with the **Bead details** section
listing every field.

## Step 2: Find an editable field

Editable fields show an **Edit** control beneath their value. Not every field
has one — only fields bdboard knows are safe to change from the board.

**Expected result:** under an editable field you see a small "Edit" disclosure.

> [!NOTE]
> No Edit control? Either the item is closed, or that particular field isn't
> editable from the board. That's by design — it keeps risky changes off the
> quick-edit path.

## Step 3: Expand the editor and change the value

Click **Edit**. The field opens an inline editor sized to the field:

- A **dropdown** for fixed-choice fields like priority or status.
- A **number box** for numeric fields.
- A **text box** or a larger **text area** for free text and descriptions.

The current value is pre-filled. Change it.

**Expected result:** the editor opens with focus already in the input, showing
the current value ready to edit.

## Step 4: Save

Click **Save** (or **Cancel** to back out without changing anything).

**Expected result:** the field's row updates in place to show the new value, and
the board's cards and counts reflect the change. A short confirmation appears by
the field.

> [!WARNING]
> If someone else changed the same item while you had it open, your save is
> rejected so you can't silently overwrite their change. Close the panel,
> reopen the item to see the latest, and redo your edit.

## Step 5: Add a note (without erasing history)

Notes are special: they're append-only. Instead of replacing the existing notes,
you add to them. Expand **Add a note**, type your note, and submit.

**Expected result:** your note is added below the existing notes — nothing above
it is overwritten — and the form collapses again.

> [!TIP]
> Notes support markdown, so you can use lists, emphasis, and links to keep
> them readable.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No Edit control anywhere | The item is closed. Editing is only offered on open items. |
| A specific field has no Edit control | That field isn't editable from the board by design. |
| My save was rejected | The item changed underneath you. Reopen it to get the latest, then redo the edit. |
| The save seemed to do nothing | Watch for the confirmation by the field; if an error shows there, read it and try again. |

## Related Guides

- [Inspect a bead in detail](InspectingABead.md)
- [View your work on the board](ViewingYourWork.md)
- [Manage project memories](ManagingMemories.md)
- Reference: [The board screen](../Reference/BoardScreen.md)
