# How to review history and trends

## What You'll Learn

How to open the History screen, change the time range, read the created-vs-closed
chart and the headline stats, page through finished work, and open any closed
item.

## Prerequisites

- bdboard running with your project open — see the
  [Quick Start](../Getting-Started/QuickStart.md).

## Overview

The board shows the present; the **History** screen shows the past. It answers
"what got finished, when, and how fast?" with a throughput chart, a row of
summary stats, and a searchable list of closed work — over any window you pick.

## Step 1: Open History

In the top bar, click **History**.

**Expected result:** the History screen opens with a chart, a stats strip in the
header, and a list of recently closed items.

## Step 2: Pick a time range

Use the range buttons — **7d**, **30d**, **90d**, and **All**. The default is
30 days.

**Expected result:** the chart, the stats, and the closed list all update to the
window you chose. The active range button stays highlighted.

> [!TIP]
> Need an exact window? Click **Custom** to pick a **From** and **To** date,
> then **Apply**. Click **Clear** to return to the preset range.

## Step 3: Read the created-vs-closed chart

The **Created vs closed** chart shows two bars per day: how many items were
created and how many were closed. A legend names each series, and the created
bars carry a diagonal hatch so you can tell them apart even in greyscale.

**Expected result:** you can see, day by day, whether you're closing work faster
than it arrives.

## Step 4: Read the headline stats

The stats strip in the header summarises the window:

- **Total** and **Closed (all time)** — workspace-wide totals (these don't
  change with the range).
- **Avg lead** — average claim-to-close time over the range.
- **Closed (range)** — how many items closed inside the window.
- **Median lead** — median filed-to-closed time over the range.
- **Throughput** — average items closed per day over the range.

**Expected result:** the range-scoped numbers move when you change the range; the
workspace totals stay put.

> [!NOTE]
> Each stat has a small **i** you can hover or focus for the precise definition.

## Step 5: Page through closed work

Below the chart, the **Closed beads** list shows finished items newest-first.
Use **Newer** / **Older** to page, and **Per page** to change how many show at
once.

**Expected result:** the list pages within your chosen window and remembers your
per-page choice as you go.

## Step 6: Open a closed item

Click any card in the list.

**Expected result:** the same detail panel you get on the board opens, showing
that item's full history. See [Inspect a bead in detail](InspectingABead.md).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Nothing closed in this range" | Widen the range, or pick a Custom window that covers when the work finished. |
| The chart is empty but items closed | Make sure your range covers the dates they closed; try **All**. |
| A page looks empty | Use the link to jump back to page 1, or widen the range. |
| The stats look stale | The screen updates live; if needed, switch ranges once to force a refresh. |

## Related Guides

- [Filter recently closed work](FilteringClosedWork.md)
- [View your work on the board](ViewingYourWork.md)
- [Inspect a bead in detail](InspectingABead.md)
- Reference: [The history screen](../Reference/HistoryScreen.md)
- Concept: [Live updates](../Concepts/LiveUpdates.md)
