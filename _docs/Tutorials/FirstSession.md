# Tutorial: Your first bdboard session

## What You'll Achieve

By the end of this walkthrough you'll have bdboard running against a project, a
live board open in your browser, and you'll have read the lanes, opened an item,
made a small edit, and watched the board update itself — a complete first
session, start to finish.

## Before You Begin

- bdboard installed — see [Installation](../Getting-Started/Installation.md).
- A project folder your team tracks work in.
- A few minutes and a modern browser.

## The Scenario

You've just been handed a project and asked to "take a look at where things
stand." You'll open it in bdboard, get oriented, and make one small update.

## Step 1: Start bdboard

Open a terminal inside the project folder and launch bdboard, exactly as in the
[Quick Start](../Getting-Started/QuickStart.md).

**What you'll see:** a browser tab opens with the project's board, and the
terminal prints the address it's serving. If no tab opens, open that address
yourself.

> [!TIP]
> If something else is already using the usual address, bdboard quietly picks
> the next free one and prints it — nothing for you to do.

## Step 2: Get the lay of the land

Look across the board. Along the top is the **Epics** strip. Below it are the
lanes: **Deferred**, **Blocked**, **Ready**, **In Progress**, and **Closed**,
plus an **Activity** feed of recent changes. The top bar shows running counts and
links to the other screens.

**What you'll see:** every in-flight item as a card, sorted into exactly one
lane, highest-priority and newest first.

## Step 3: Find something you could start

Look at the **Ready** lane. Everything there is genuinely available to pick up
right now.

**What you'll see:** the top card in Ready is the highest-priority, freshest
thing you could start. If a card you expected is in **Blocked** instead, it's
waiting on something — see [Blocked vs ready work](../Concepts/BlockedVsReady.md).

## Step 4: Open an item

Click any card.

**What you'll see:** a detail panel opens with the full description, a lifecycle
timeline, every field, and an audit trail. Read it, then keep the panel open for
the next step. For the full tour see
[Inspect a bead in detail](../Guides/InspectingABead.md).

## Step 5: Make one small edit

If the item is open, find an editable field — say its priority — and click
**Edit**. Change the value and click **Save**.

**What you'll see:** the field updates in place, and behind the panel the card
and the top-bar counts change to match. If your save is rejected, someone edited
the item while you had it open — reopen it and try again. Full details:
[Edit a bead's fields](../Guides/EditingABead.md).

## Step 6: Watch it stay current

Close the panel and leave the board open for a moment.

**What you'll see:** as work changes — yours or a teammate's — cards move, appear,
and disappear with no reload. That's the board's
[live updates](../Concepts/LiveUpdates.md) at work.

## Final Result

You have a live board open, you understand the lanes, you've inspected an item,
made an edit, and seen the board refresh itself — a full first session.

## What You Learned

- How to start bdboard against a project.
- How to read the lanes and find ready work.
- How to open and edit an item.
- That the board keeps itself current automatically.

## Next Steps

- Put it into practice: [Triage and pick up work](TriageWalkthrough.md).
- Learn the board in depth: [View your work on the board](../Guides/ViewingYourWork.md).
- Look back over time: [Review history and trends](../Guides/ReviewingHistory.md).
