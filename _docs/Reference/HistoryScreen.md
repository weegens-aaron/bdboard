# The History Screen Reference

## Overview

The History screen is bdboard's look back over time. It shows a created-vs-closed
chart, a strip of summary stats, and a paginated list of finished work — all
scoped to a time range you choose. This page is a lookup for every control on it.

## The range control

| Control | What it does |
|---------|--------------|
| 7d | Scope everything to the last 7 days. |
| 30d | Scope to the last 30 days (the default). |
| 90d | Scope to the last 90 days. |
| All | Show all time. |
| Custom | Open a date picker to choose an exact From/To window. |
| Apply | Apply the chosen custom dates. |
| Clear | Discard the custom window and return to the preset range. |

The active range stays highlighted, and every region below reacts to it.

## The created-vs-closed chart

| Element | Meaning |
|---------|---------|
| Created bars | How many items were created each day (hatched, so they read in greyscale). |
| Closed bars | How many items were closed each day. |
| Legend | Names each series with its total over the window. |
| Day labels | The date each pair of bars represents. |

Both series share one scale so they're directly comparable.

## The stats strip

| Stat | Meaning |
|------|---------|
| Total | Workspace-wide total across all items (not range-scoped). |
| Closed (all time) | Every item ever closed in the workspace (not range-scoped). |
| Avg lead | Average claim-to-close time over the active range. |
| Closed (range) | Items closed within the active range. |
| Median lead | Median filed-to-closed time over the active range. |
| Throughput | Average items closed per day over the active range. |

Each stat has a small **i** you can hover or focus for its precise definition.

## The closed list and pager

| Control | What it does |
|---------|--------------|
| Closed beads list | Finished items, newest-closed first; click one to open its detail panel. |
| Newer | Page toward more recent items. |
| Older | Page toward older items. |
| Page indicator | The page you're currently on. |
| Per page | How many items to show per page (remembered as you navigate). |

## Tips

> [!TIP]
> The board only reaches back 3 days; the History screen is where you go for
> weeks or months. See [Filter recently closed work](../Guides/FilteringClosedWork.md).

> [!NOTE]
> The workspace totals (Total, Closed all time) don't move with the range — only
> the range-scoped stats do.

## See Also

- Guide: [Review history and trends](../Guides/ReviewingHistory.md)
- Guide: [Filter recently closed work](../Guides/FilteringClosedWork.md)
- Reference: [The board screen](BoardScreen.md)
- Concept: [Live updates](../Concepts/LiveUpdates.md)
