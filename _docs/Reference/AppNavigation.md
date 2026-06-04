# App Navigation and Status Indicators Reference

## Overview

Every bdboard screen shares the same top bar (the masthead), the same navigation,
and the same visual language for status and priority. This page is a lookup for
those shared elements so you can read any screen at a glance.

## The top bar

| Element | What it does |
|---------|--------------|
| Title | Names the current screen or project. |
| Page navigation | Links to **Board**, **History**, and **Memory**; the current page is marked. |
| Theme toggle | Switches between light and dark; the label shows what you'll switch to. |
| + Pour Formula | (Board only) Opens the formula picker to pour a batch of work. |
| Counts strip | (Board) per-status totals; (History) range-scoped summary stats. |

## Navigating between screens

| Destination | What you'll find |
|-------------|------------------|
| Board | The live view of in-flight work. See [The board screen](BoardScreen.md). |
| History | The look back over time. See [The history screen](HistoryScreen.md). |
| Memory | Your project's saved notes. See [The memory screen](MemoryScreen.md). |

The link for the page you're on is highlighted so you always know where you are.

## Status indicators

bdboard uses a small set of statuses across cards, lanes, and detail panels.

| Status | Meaning |
|--------|---------|
| Open / Ready | Available to pick up. |
| In progress | Someone is actively working it. |
| Blocked | Waiting on another item to finish first. |
| Deferred | Intentionally parked for now. |
| Closed | Finished. |

See [Blocked vs ready work](../Concepts/BlockedVsReady.md) for why an item lands
in Blocked rather than Ready.

## Priority badges

| Badge | Meaning |
|-------|---------|
| P0 | Highest priority. |
| P1 | High priority. |
| P2 | Normal priority. |
| Higher numbers | Lower priority. |

Within a lane, higher-priority items sort above lower-priority ones, and newer
above older.

## Theme

| Mode | Notes |
|------|-------|
| Light | The default. |
| Dark | Toggle from the top bar; your choice is remembered between visits. |

## Tips

> [!TIP]
> Whatever screen you're on, the navigation and counts live in the same place —
> learn the top bar once and every screen reads the same way.

> [!NOTE]
> Counts and statuses update live as work changes. See
> [Live updates](../Concepts/LiveUpdates.md).

## See Also

- Reference: [The board screen](BoardScreen.md)
- Reference: [The history screen](HistoryScreen.md)
- Reference: [The memory screen](MemoryScreen.md)
- Concept: [Lanes and how cards are sorted](../Concepts/LanesExplained.md)
