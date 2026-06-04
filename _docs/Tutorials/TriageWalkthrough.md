# Tutorial: Triage and pick up work

## What You'll Achieve

You'll work a realistic triage flow: scan the board, decide what's most worth
doing, confirm it's truly ready, open it, and claim it by updating a field — then
watch it move lanes live.

## Before You Begin

- bdboard running with your project open — see the
  [Quick Start](../Getting-Started/QuickStart.md).
- A first session under your belt helps: [Your first bdboard session](FirstSession.md).

## The Scenario

It's the start of your day. Several items are in flight and you need to pick the
right next thing, confirm nothing is secretly blocking it, and start it.

## Step 1: Take in the whole board

Read top to bottom: the **Epics** strip, then **Deferred**, **Blocked**,
**Ready**, **In Progress**, **Closed**, and the **Activity** feed.

**What you'll see:** the shape of the work at a glance — what's parked, what's
stuck, what's available, what's moving, and what just finished.

## Step 2: Rule out what you can't start

Glance at **Blocked**. Everything there is waiting on something else, so it's not
a candidate yet.

**What you'll see:** the blocked items, each waiting on another. To understand
why, see [Blocked vs ready work](../Concepts/BlockedVsReady.md).

## Step 3: Pick the best ready item

Look at the top of the **Ready** lane. Because lanes sort highest-priority and
newest first, the strongest candidate is already at the top.

**What you'll see:** a clear "do this next" candidate without hunting. For how
the ordering works, see
[Lanes and how cards are sorted](../Concepts/LanesExplained.md).

## Step 4: Confirm the details

Click the card to open it. Read the description and skim the lifecycle and
dependencies to confirm it's genuinely ready and you understand the goal.

**What you'll see:** the full detail panel. If a dependency you didn't expect
shows up, follow it to check its status — see
[Inspect a bead in detail](../Guides/InspectingABead.md).

## Step 5: Claim it

With the item still open, edit the field your team uses to take ownership — for
example set the **assignee** to you, or move the **status** to in progress — then
**Save**.

**What you'll see:** the field updates in place. If your save is rejected,
someone just changed the item; reopen it and redo the edit. Full details:
[Edit a bead's fields](../Guides/EditingABead.md).

## Step 6: Watch it move

Close the panel.

**What you'll see:** the item leaves **Ready** and appears in **In Progress**,
and the top-bar counts update — all without a reload, thanks to
[live updates](../Concepts/LiveUpdates.md).

## Final Result

You triaged the board, chose the best available work, confirmed it was ready,
and claimed it — and saw it move lanes live.

## What You Learned

- How to read the board to triage quickly.
- How to rule out blocked work and pick the top ready item.
- How to confirm details before committing.
- How to claim work and watch the board reflect it instantly.

## Next Steps

- Go deeper on the board: [View your work on the board](../Guides/ViewingYourWork.md).
- Spin up a batch of related work: [Pour a formula](../Guides/PouringAFormula.md).
- Review throughput over time: [Review history and trends](../Guides/ReviewingHistory.md).
