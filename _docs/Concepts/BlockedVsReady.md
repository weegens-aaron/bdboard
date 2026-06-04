# Blocked vs ready work

## What Is It

**Ready** work is anything you can start right now — nothing is standing in its
way. **Blocked** work is the opposite: it can't start yet because it's waiting on
another item to finish first. bdboard separates the two into different lanes so
you never pick up something that's secretly stuck.

## Why It Matters

The most frustrating way to lose time is to start something, only to discover
halfway in that it was waiting on a piece that isn't done. By splitting Ready from
Blocked, the board answers the only question that matters when you're choosing
work — "can I actually do this now?" — before you click anything.

## How It Works

Items can depend on each other. "Paint the wall" depends on "plaster the wall";
you can't paint until the plaster is up. bdboard understands these links and uses
them to decide a lane:

- If an item has unfinished work it depends on, it goes to **Blocked**. It's
  waiting, by definition.
- If an item has nothing unfinished standing in its way, it goes to **Ready**.
  Go for it.
- As soon as the thing it was waiting on finishes, the blocked item becomes ready
  on its own and moves to the Ready lane — you don't have to move it.

When you open a blocked item, its detail panel lists what it depends on, so you
can see exactly what needs to finish first — and click straight through to that
item. See [Inspect a bead in detail](../Guides/InspectingABead.md).

> [!NOTE]
> An item can be perfectly valid and important and still be Blocked — being
> blocked isn't a problem with the item, just a statement that something else
> comes first.

## Related

- Concept: [Lanes and how cards are sorted](LanesExplained.md)
- Concept: [Live updates](LiveUpdates.md)
- Guide: [Inspect a bead in detail](../Guides/InspectingABead.md)
- Guide: [View your work on the board](../Guides/ViewingYourWork.md)
