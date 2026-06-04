# The Board Screen Reference

## Overview

The board is bdboard's main screen. It shows your project's in-flight work as
cards arranged into lanes, with a header of running counts, a time filter, and an
activity feed. This page is a lookup for every region and control on it.

## Layout

| Region | What it shows |
|--------|---------------|
| Title | The name of the project (workspace) you're viewing. |
| Counts strip | Running totals per status, top-right in the header. |
| Page navigation | Links to **Board**, **History**, and **Memory**. |
| Actions | The theme toggle and the **+ Pour Formula** button. |
| Time filter | Range buttons above the lanes that bound the Closed lane. |
| Epics strip | The big container items, in a row across the top. |
| Lanes | The columns of cards: Deferred, Blocked, Ready, In Progress, Closed. |
| Activity feed | The most recent changes, newest first. |

## Lanes

| Lane | What's in it |
|------|--------------|
| Epics | Large container items; shown as chips in the top strip. |
| Deferred | Work intentionally put off for now. |
| Blocked | Work waiting on something else to finish first. |
| Ready | Work you can pick up right now, with nothing in its way. |
| In Progress | Work someone is actively doing. |
| Closed | Work finished within the active time window. |

Within every lane, cards are ordered highest-priority and newest first. See
[Lanes and how cards are sorted](../Concepts/LanesExplained.md).

## The time filter

| Button | Window |
|--------|--------|
| 12h | Work finished in the last 12 hours. |
| 1d | Work finished in the last 24 hours (the default). |
| 3d | Work finished in the last 3 days (the longest the board reaches). |

For longer windows, use the [History screen](HistoryScreen.md).

## A card

| Element | Meaning |
|---------|---------|
| ID | The item's identifier. |
| Priority badge | The item's priority (for example P1, P2). |
| Title | What the item is. |
| Assignee | Who it belongs to, if anyone. |
| Type | The kind of item (for example task, bug, epic). |
| Dependency marker | A count shown when the item is linked to others. |

Clicking a card opens its detail panel — see
[Inspect a bead in detail](../Guides/InspectingABead.md).

## The activity feed

| Element | Meaning |
|---------|---------|
| When | How long ago the change happened. |
| Verb | What changed (for example created, closed). |
| Actor | Who made the change. |
| Title | Which item it was. |

Clicking an activity row opens that item's detail panel.

## Tips

> [!TIP]
> The board updates itself live — keep it open and it stays current. See
> [Live updates](../Concepts/LiveUpdates.md).

> [!NOTE]
> You can't drag cards between lanes. A card's lane is decided automatically from
> its state and what it's waiting on.

## See Also

- Guide: [View your work on the board](../Guides/ViewingYourWork.md)
- Guide: [Filter recently closed work](../Guides/FilteringClosedWork.md)
- Reference: [App navigation and status indicators](AppNavigation.md)
- Concept: [Lanes and how cards are sorted](../Concepts/LanesExplained.md)
