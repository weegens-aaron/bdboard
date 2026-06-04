# How to inspect a bead in detail

## What You'll Learn

How to open any item's full detail panel, read its timeline, follow its links to
related work, and find the answers to "what is this?", "who touched it?", and
"what is it waiting on?".

## Prerequisites

- bdboard running with your project open — see the
  [Quick Start](../Getting-Started/QuickStart.md).

## Overview

Every card on the board is a doorway. Clicking one opens a detail panel that
shows everything bdboard knows about that item — its description, all its
fields, a status timeline, and a complete change log. It's a read-and-review
view; if the item is still open you can also fix a field from here (see
[Edit a bead's fields](EditingABead.md)).

## Step 1: Open the detail panel

Click any card — on the board, an epic chip in the top strip, an Activity row,
or a card on the [History screen](../Reference/HistoryScreen.md).

**Expected result:** a panel opens over the board showing the item's ID,
priority, status, and full title at the top.

> [!TIP]
> To close the panel, click the close button in its top corner or click the
> dimmed area outside it. The board is still live behind it.

## Step 2: Read the header

The top of the panel gives you the at-a-glance facts: the item's ID, its
priority badge, and its current status.

**Expected result:** you can tell what the item is and what state it's in
without scrolling.

> [!NOTE]
> If the panel shows a small warning line, it means bdboard fell back to a
> cached or partial view of this item — the details are still shown, it's just
> flagging that they may be a moment behind.

## Step 3: Skim the lifecycle timeline

Just below the header, the **Lifecycle** section lists each status the item has
passed through, when it entered that status, how long it stayed there, and who
moved it.

**Expected result:** you can see the item's journey — for example *open to in
progress to closed* — and how long it spent in each stage.

## Step 4: Read the details

The **Bead details** section lists every field: description, labels, assignee,
priority, dependencies, comments, and more. Long text is shown formatted, and
linked items appear as their own rows.

**Expected result:** you can read the full description and every field value.

## Step 5: Follow a dependency

If the item depends on (or is depended on by) others, those appear as a list of
linked IDs in the details. Click any linked ID.

**Expected result:** the panel swaps to show that related item. To learn what
the relationship means, see
[Blocked vs ready work](../Concepts/BlockedVsReady.md).

## Step 6: Review the audit trail

At the bottom, the **Audit trail** lists every recorded change — when it
happened, who made it, and what changed.

**Expected result:** you can trace the item's history field by field. If there's
no history yet, you'll see a short "no recorded history" note.

> [!TIP]
> Need the data behind the panel? The header has a **raw JSON** link that opens
> the item's raw record in a new tab.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| The panel says audit history is unavailable | bd couldn't be reached for a moment. Close the panel and reopen it shortly. |
| A linked ID won't open | The related item may have been removed; check the [Board screen](../Reference/BoardScreen.md) or [History screen](../Reference/HistoryScreen.md). |
| There's no Edit control on a field | Only open items expose inline editing, and only some fields are editable. See [Edit a bead's fields](EditingABead.md). |
| The panel won't close | Click the close button, or click the dimmed area outside it. |

## Related Guides

- [Edit a bead's fields](EditingABead.md)
- [View your work on the board](ViewingYourWork.md)
- [Review history & trends](ReviewingHistory.md)
- Reference: [The board screen](../Reference/BoardScreen.md)
- Concept: [Blocked vs ready work](../Concepts/BlockedVsReady.md)
