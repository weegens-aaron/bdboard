# Frequently Asked Questions

> Short answers to the questions that come up most. Each answer links on to the
> page that covers it in full.

## Getting Started

### What is bdboard?

bdboard is a small tool you run on your own computer. When you start it, it opens
a page in your browser that shows your project's work items as cards arranged into
lanes — what's ready, in progress, blocked, deferred, and recently closed. For
the full picture, read the [Overview](Overview.md).

### Do I need to be the person who set the project up?

No. If someone hands you the project folder, you can run bdboard against it. You
don't have to have created the project or configured anything. See the
[Overview](Overview.md).

### How do I install it?

You install it once, from inside the project folder you want to look at. The
[Installation](Getting-Started/Installation.md) page walks through every step.

### How do I open my first board?

From a terminal inside your project folder, start bdboard and a browser tab opens
on its own. The [Quick Start](Getting-Started/QuickStart.md) takes you from
launch to a live board in a couple of minutes.

### What do I need before I start?

A computer where you can run command-line tools, the project folder you want to
look at, and a modern web browser. The full list is on the
[Installation](Getting-Started/Installation.md) page.

## Common Tasks

### How do I see everything about one item?

Click any card and a panel opens with its full description, its history, and — if
the item is still open — controls to fix a field. See
[Inspect a bead in detail](Guides/InspectingABead.md).

### Can I change an item from the board?

Yes, but only one field at a time, and only on items that are still open. Open the
card and use the field controls in its detail panel. See
[Edit a bead's fields](Guides/EditingABead.md). bdboard never changes your work
items on its own.

### How do I look back at finished work?

Use the **History** screen. It shows a created-vs-closed chart and a searchable
list of work that finished over weeks or months. See
[Review history and trends](Guides/ReviewingHistory.md) and the
[History screen reference](Reference/HistoryScreen.md).

### How do I work with my project's saved notes?

The **Memory** screen lets you browse, search, add, and remove your project's
saved notes. See [Manage project memories](Guides/ManagingMemories.md) and the
[Memory screen reference](Reference/MemoryScreen.md).

### How do I create a batch of related work items at once?

Use **Formulas**. Pouring a formula creates a structured batch of related items
from a template in one go. See [Pour a formula](Guides/PouringAFormula.md).

### How do I find just the work I can pick up now?

Look at the **Ready** lane — it holds everything with nothing standing in its way.
For a full walkthrough of choosing and claiming work, see
[Triage and pick up work](Tutorials/TriageWalkthrough.md).

## Troubleshooting

### No browser tab opened when I ran bdboard. What now?

Open the address bdboard printed in your terminal. That's the same page the tab
would have shown. See the [Quick Start](Getting-Started/QuickStart.md).

### Every lane shows an error. Why?

bd (the beads tool bdboard reads through) isn't installed or isn't on your
system path. Install bd, then launch bdboard again. See
[Installation](Getting-Started/Installation.md).

### The board is completely empty. What happened?

The project's work history hasn't been pulled in yet. Run `bd bootstrap --yes`
once, then refresh. See [Installation](Getting-Started/Installation.md).

### `bdboard` is "not found" after I installed it.

The environment isn't active in this terminal. Activate it and try again — the
exact step is on the [Installation](Getting-Started/Installation.md) page.

### The page looks frozen and isn't updating.

A single manual refresh re-establishes the live connection, and updates resume on
their own. See [Live updates](Concepts/LiveUpdates.md).

### Something already runs on the usual address. Will bdboard clash?

No. bdboard quietly picks the next free address and prints it in the terminal.
You don't have to do anything. See the
[Quick Start](Getting-Started/QuickStart.md).

## Understanding the Board

### Why can't I drag cards between lanes?

A card's lane is decided automatically from its state and what it's waiting on,
so dragging would only fight the board. Change the underlying item instead and the
card moves itself. See [Lanes and how cards are sorted](Concepts/LanesExplained.md).

### What's the difference between Blocked and Ready?

**Ready** work has nothing standing in its way — you can start it now. **Blocked**
work is waiting on another item to finish first. When that item finishes, the
blocked card becomes ready on its own. See
[Blocked vs ready work](Concepts/BlockedVsReady.md).

### Do I ever need to reload the page?

Almost never. The board, History, and Memory screens keep themselves current on
their own, in every open tab. See [Live updates](Concepts/LiveUpdates.md).

### Is being "Blocked" a problem with the item?

No. An item can be valid and important and still be blocked — it just means
something else comes first. See [Blocked vs ready work](Concepts/BlockedVsReady.md).

## Still Stuck?

- Start from the top with the [Overview](Overview.md).
- Browse everyday tasks in the [Guides](Guides/index.md).
- Follow a full scenario in the [Tutorials](Tutorials/index.md).
- Look up a screen or control in the [Reference](Reference/index.md).
