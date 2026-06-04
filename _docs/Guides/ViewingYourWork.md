# How to view your work on the board

## What You'll Learn

How to read the board, tell the lanes apart, find the work that's yours to pick
up, and narrow down what you're looking at.

## Prerequisites

- bdboard running with your project open — see the
  [Quick Start](../Getting-Started/QuickStart.md).

## Overview

The board is the main screen. It shows every in-flight item as a card, grouped
into lanes by what you'd do with it. It's a *recent* view — finished work older
than a few days lives on the [History screen](../Reference/HistoryScreen.md)
instead.

## Step 1: Get your bearings

Look at the board top to bottom.

- The **Epics** strip across the top holds the big containers.
- Below it sit the lanes: **Deferred**, **Blocked**, **Ready**,
  **In Progress**, and **Closed**.
- An **Activity** feed shows the most recent changes.
- The bar at the top (the masthead) shows running counts and links to the other
  pages.

**Expected result:** you can name each lane and find the counts in the masthead.

## Step 2: Find what you can start now

Look at the **Ready** lane. Every card there is genuinely available — nothing in
it is secretly waiting on something else.

**Expected result:** the top card in Ready is the highest-priority, freshest
thing you could pick up.

> [!TIP]
> If a card you expected to be ready is sitting in **Blocked** instead, it's
> waiting on another item to finish. See
> [Blocked vs ready work](../Concepts/BlockedVsReady.md) for why.

## Step 3: Scan priority and freshness

Within each lane, cards are ordered highest-priority and newest first, so you can
read top-to-bottom.

**Expected result:** the most important, most recent work is always at the top of
its lane.

## Step 4: Narrow the recently-closed view

The **Closed** lane shows only the last few days by default. Use its filter to
switch between the last 12 hours, 1 day, or 3 days.

**Expected result:** the Closed lane shows only work finished within the window
you picked, and the masthead's closed count matches it.

> [!NOTE]
> Looking for something finished longer ago? The board deliberately keeps a short
> window. Use the [History screen](../Reference/HistoryScreen.md) for the long
> view.

## Step 5: Dig into a card

Click any card — on the board, an epic chip, or an activity row — to open its
full detail.

**Expected result:** a panel opens with everything about that item. See
[Inspect a bead in detail](InspectingABead.md).

## Step 6: Let it refresh itself

Keep the board open while you work. It updates live as things change.

**Expected result:** cards move and counts change without a manual reload. See
[Live updates](../Concepts/LiveUpdates.md).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| A lane shows an error instead of cards | bd isn't available where bdboard is running. See [Installation](../Getting-Started/Installation.md). |
| The Closed lane looks empty | Widen its filter, or check the [History screen](../Reference/HistoryScreen.md) for older work. |
| A card won't move out of Blocked | It's waiting on another item; open it to see what. See [Blocked vs ready work](../Concepts/BlockedVsReady.md). |
| The board seems frozen | Refresh once; live updates resume automatically. |

## Related Guides

- [Inspect a bead in detail](InspectingABead.md)
- [Filter recently closed work](FilteringClosedWork.md)
- [Review history & trends](ReviewingHistory.md)
- Reference: [The board screen](../Reference/BoardScreen.md)
- Concept: [Lanes & how cards are sorted](../Concepts/LanesExplained.md)
