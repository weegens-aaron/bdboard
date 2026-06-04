# Lanes and how cards are sorted

## What Is It

A **lane** is a column on the board that groups work by what you'd do with it —
Deferred, Blocked, Ready, In Progress, and Closed, plus an Epics strip across the
top. Every item sits in exactly one lane, and within a lane the cards are always
ordered the same way.

## Why It Matters

Lanes turn a flat list of work into a board you can read in seconds. Instead of
scanning everything and asking "can I start this?" item by item, you look at one
lane — **Ready** — and the answer is already sorted for you. The ordering means
the single best thing to do next is always near the top.

## How It Works

Think of the board like a kitchen pass. Orders that can't be cooked yet (waiting
on an ingredient) sit to one side; orders ready to cook are lined up in the order
you should make them; orders being cooked are on the stove; finished plates go
out.

bdboard does the same thing automatically:

- **Each item goes to one lane** based on its state and what it's waiting on. You
  don't drag cards around — the lane is decided for you, so it's always honest.
- **Epics** (the big containers) get their own strip at the top, separate from
  the everyday lanes.
- **Within every lane, cards sort the same way:** highest priority first, and
  among equal priorities, the newest first. So reading a lane top-to-bottom is
  reading it in "do this next" order.
- **The Closed lane is a recent view.** It only reaches back a short window so
  the board stays focused on the present; older finished work lives on the
  History screen.

Because an item's lane comes straight from its real state, the board can never
drift out of sync with what's actually true — if something becomes ready, it
shows up in Ready on its own.

## Related

- Concept: [Blocked vs ready work](BlockedVsReady.md)
- Concept: [Live updates](LiveUpdates.md)
- Guide: [View your work on the board](../Guides/ViewingYourWork.md)
- Reference: [The board screen](../Reference/BoardScreen.md)
