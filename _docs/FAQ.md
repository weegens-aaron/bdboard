# Frequently Asked Questions

Quick answers to the things that most often surprise people while using
**bdboard**. Most of these aren't bugs — they're deliberate behaviours that make
more sense once you know the *why* behind them. Each answer links to the fuller
write-up if you want the whole story.

New here? Start with the [Overview](Overview.md) and
[Take your first look](Guides/take-your-first-look.md).

## The board & the lanes

**Why can't I drag a card from one lane to another?**
There's nothing to drag. Each card sits in a lane because of the bead's *real
state* — bdboard reads that state and groups the cards for you. Browsing the
board never changes anything; the board stays honest precisely because you can't
push cards around to fake progress. Change a bead's actual state and its lane
follows. See [Bead lifecycle & the lanes](Concepts/bead-lifecycle-and-lanes.md).

**Why didn't the time filter hide an old in-progress bead?**
The time window (12h / 1d / 3d) only narrows the **Closed** lane. The other
lanes — Ready, Blocked, In Progress, Deferred — show their current contents no
matter what window you pick, because they represent *live* state, not dated
events. See [The board](Features/the-board.md).

**The Closed lane is empty — does that mean nothing got done?**
Not necessarily. The board only looks back a few days. Work that finished
earlier hasn't vanished; it's simply older than the window shows. Head to
[History & trends](Features/history-and-trends.md) to see the longer story.

**Where did my older work go? I can't find it on the board.**
The board's windows stop at three days by design — it's meant for *recent*
activity. For anything older, use History instead of widening in circles. See
[Time ranges & recent work](Concepts/time-ranges-and-recent-work.md).

## Editing beads

**Why are the Edit controls missing on some beads?**
Only **open** beads can be edited. Once a bead is in progress or closed, its
fields go read-only and the Edit controls disappear. That's deliberate — it
stops an edit from quietly clobbering in-flight work or rewriting finished
history. See [Bead detail & editing](Features/bead-detail-and-editing.md).

**My save was rejected and asked me to refresh — what did I do wrong?**
Nothing. If someone else (or an agent) changed the same bead after you opened
its panel, bdboard refuses your save so their change isn't overwritten. It's a
safety net, not an error. Reload, reopen the bead, and re-apply your edit. See
[Edit a bead](Guides/edit-a-bead.md).

**A bead changed "on its own" while I was looking at it.**
Almost always that means the same bead was updated somewhere else — another tab,
another window, or an agent working alongside you. bdboard shows those changes
live, with no refresh. See [Live updates](Features/live-updates.md).

## Creating beads from formulas

**I poured a formula — why is the count off by one?**
Every pour quietly adds one behind-the-scenes wrapper that isn't part of your
visible count. That's expected. See [Create from formulas](Features/create-from-formulas.md).

**Something failed mid-pour. Did I end up with half a batch?**
No. A pour is all-or-nothing: if anything goes wrong while the batch is being
created, nothing is added, so your board is never left half-built with orphaned
beads. See [Create beads from a formula](Guides/create-beads-from-a-formula.md).

**Beads appeared out of nowhere.**
Check whether you — or an agent — just poured a formula in another tab or
window. Freshly poured beads show up everywhere bdboard is open. See
[Live updates](Features/live-updates.md).

## History & trends

**I set a custom date range, then it jumped back to the last 30 days.**
A live update (for example, a bead closing in the background) snaps History back
to its default last-30-days window. Just reopen **Custom** or click your preset
to re-apply your range. See
[Explore history & trends](Guides/explore-history-and-trends.md).

**Why don't the Total and Closed tallies change when I move the range?**
They're deliberately whole-workspace figures: **Total** and **Closed** count
your entire workspace as it stands right now, not just the selected window. If a
number doesn't budge when you change the range, that's one of these standing
counts sitting next to the figures that *do* respond. See
[History & trends](Features/history-and-trends.md).

**Can I tell the created and closed bars apart without colour?**
Yes. The "created" bar carries a diagonal hatch pattern as well as its colour,
so it stays distinguishable in greyscale or with colour-blind vision. Hovering
or reading with a screen reader gives the exact counts per day. See
[Explore history & trends](Guides/explore-history-and-trends.md).

## Agent memories

**I saved a memory and it replaced an existing one — why?**
Re-using a Key overwrites that memory's Body, with no "are you sure?" prompt.
That's how you keep a single note up to date. If you wanted a separate note,
give it a different Key. See [Memory manager](Features/memory-manager.md).

**I forgot a memory by mistake — can I undo it?**
There's no undo, and the cost is invisible: agents simply stop knowing whatever
that note taught them. When in doubt, **edit** a memory to trim or correct it
rather than forgetting it outright; if you've already forgotten one, re-create
it with the same Key and original text. See
[Manage agent memories](Guides/manage-agent-memories.md).

## Live updates & connection

**The connection indicator says "reconnecting…" — is something broken?**
Usually not. After your computer sleeps or the network blips, bdboard drops its
live link and then re-establishes it on its own; the indicator just tells you
it's catching back up. See [Live updates](Features/live-updates.md).

**Do I need to refresh to see new activity?**
No. The board, counts, and activity feed update themselves within a moment
whenever work changes — which is also why a card may appear, move, or vanish
while you watch. See [Take your first look](Guides/take-your-first-look.md).

## Your data & safety

**Is bdboard my backup?**
No. bdboard *reads* your local data; it doesn't copy it anywhere safe for you.
If the only copy lives on one machine, one mishap loses it — keep your own
backup or off-machine copy. See
[Your data is local & safe](Concepts/your-data-is-local-and-safe.md).

**Can I open the board from another device?**
Not by default. bdboard is set up to be reached from the same machine it runs
on. See [Your data is local & safe](Concepts/your-data-is-local-and-safe.md).

## Beads themselves

**Some of a bead's sections are empty — is it broken?**
No. Not every bead has every field filled in. A quickly-filed bead might carry
just a name and a kind; a well-groomed one has a full description, a "done"
check, links, and a thick log of notes. An empty section just means that detail
wasn't recorded. See [What is a bead?](Concepts/what-is-a-bead.md).

**Should I put several jobs into one bead to save time?**
Better not to. A bead that's really three tasks in a trench coat can never be
cleanly finished and quietly breaks the board's ability to show honest progress.
Split it into separate beads instead. And don't judge a bead by its title
alone — the headline is a label, not the whole story. See
[What is a bead?](Concepts/what-is-a-bead.md).

---

Still stuck? Browse the [Guides](Guides/index.md) for step-by-step how-tos, or
the [Concepts](Concepts/index.md) for the ideas behind how bdboard behaves.
