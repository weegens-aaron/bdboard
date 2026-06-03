# Feature: Live updates

## What it does

bdboard keeps itself current. When the beads in your project change — because
you (or one of your tools) filed, claimed, edited, closed, or poured beads —
the board notices and refreshes the affected parts of the page on its own,
usually within a second or two. You don't reload, you don't press a refresh
button, and you don't poll: the screen simply catches up to reality while you
watch. A small **live** indicator at the bottom of the window tells you the
push connection is healthy.

## Why it exists

A board that goes stale the moment you stop touching it is worse than no board
at all — it quietly lies to you. Beads change constantly: agents and teammates
file and close them in the background, and you yourself edit beads and pour new
ones from formulas. If the page only updated when you manually reloaded, you'd
never be sure whether what's on screen is *now* or *five minutes ago*, and you'd
develop the bad habit of mashing reload "just in case."

Live updates exist so the board is **trustworthy at a glance**. Because it
refreshes itself whenever the underlying work changes, you can leave it open on
a second monitor and treat it as a true, current picture of your project. It
also means a change you make in one place shows up everywhere — including in
other browser tabs you have open — without any extra steps.

## How it works

### User perspective

You don't do anything to turn this on — it's always working. Open the board and
glance at the bottom of the window:

- **"connecting…"** — the page has just loaded and is opening its live
  connection.
- **"live · push"** with a steady dot — connected and listening; changes will
  appear on their own.
- **"reconnecting…"** — the connection dropped (a sleep, a network blip, the app
  briefly restarting) and the page is automatically trying again. It heals
  itself within a few seconds; you don't need to do anything.

While the connection is healthy, anything that changes your beads — a teammate or
agent closing a bead, you editing a field, you pouring new beads from a formula —
makes the relevant part of the screen update in place. On the **Board**, the
counts strip and the swim lanes re-draw. On **History**, the charts and stats
re-draw for the time window you're currently viewing. On the **Memory** page,
the saved-notes list refreshes. The rest of the page — your scroll position, an
open bead, your dark-mode and time-window choices — stays put. Only the data
panels refresh, so it feels like the numbers and cards quietly correct
themselves rather than the whole page flashing.

### System perspective

In plain language, and without any file paths or code: bdboard runs a small
watcher that keeps an eye on your project's bead data on your own machine. When
that data changes on disk, the watcher takes a fresh reading of your beads and
compares it to what it last showed. If something genuinely changed, the server
sends a short "beads changed" nudge down a long-lived connection that every open
page holds. Each page, on receiving the nudge, re-fetches just the panels that
display live data and swaps in the new content.

Two pieces of timing keep this smooth rather than frantic:

- A brief **settle window** (about a quarter of a second) groups the flurry of
  tiny writes a single change produces into *one* refresh, instead of a dozen.
- A short **cool-down** after each refresh stops a burst of background activity
  from triggering refreshes back-to-back at full speed.

The connection also sends a quiet heartbeat every few seconds so that proxies or
network equipment don't hang up on it for being idle. The whole thing is
**push, not polling** — your browser isn't pestering the server on a timer; it
just waits and is told when there's news, which is why updates feel immediate
without wasting effort when nothing is happening. And because this all reads from
data already on your machine, nothing is fetched from the internet to keep the
board current (see [Your data is local & safe](../Concepts/your-data-is-local-and-safe.md)).

## Sequence

```mermaid
sequenceDiagram
    actor You
    participant Page as bdboard page (your browser tab)
    participant App as bdboard (on your machine)
    participant Data as Your bead data

    Page->>App: Open a live connection on page load
    App-->>Page: "live · push" — connection healthy
    Note over Data: A bead is filed / edited / closed / poured
    Data-->>App: The data on disk changes
    App->>App: Take a fresh reading; did anything really change?
    App-->>Page: Nudge: "beads changed"
    Page->>App: Re-fetch just the data panels
    App-->>Page: Updated counts / lanes / history / notes
    Note over You: The screen catches up on its own — no reload
```

## Where you'll find it

Live updates aren't a button — they're a behaviour of the whole app, so you see
them everywhere data is shown:

- **The status indicator** lives at the **bottom-centre of every page** (in the
  footer): a small dot plus the words *connecting… / live · push /
  reconnecting…*. That's your at-a-glance "is the board current?" cue.
- **The Board page** — the counts strip across the top and the swim lanes update
  themselves in place as beads change.
- **The History page** — the charts and summary stats re-draw for whichever time
  window you're viewing.
- **The Memory page** — the saved-notes list refreshes as notes change.

You won't find a settings screen or a toggle for this; it's on by default and
needs no configuration.

## Edge Cases

> [!WARNING]
> - **A change in one tab shows up in all your tabs.** Every open bdboard page
>   holds its own live connection, so editing a bead or pouring a formula in one
>   tab updates the board in your other tabs too — they all hear the same nudge.
> - **After sleep or a network blip, the indicator shows "reconnecting…".** This
>   is normal and self-healing: the page retries automatically and, the moment it
>   reconnects, pulls a fresh picture so you're never left looking at stale data
>   without warning.
> - **On the History page, a live update re-draws the window you're viewing.** If
>   you've narrowed to a custom range, an automatic refresh keeps showing your
>   current selection rather than snapping you back to a default — your view is
>   preserved while the numbers update underneath it.
> - **Browsing never triggers a "change."** Simply opening beads, switching
>   pages, or flipping dark mode doesn't alter your data, so it won't cause the
>   board to think something changed. Only real edits and pours do.

## Error Scenarios

- **The live connection drops** (you closed the laptop, the Wi-Fi hiccuped, or
  the app briefly restarted): the indicator switches to *reconnecting…* and the
  page keeps trying on its own with growing pauses between attempts. When it
  succeeds, it re-reads your beads so the board is current again. You see a
  short delay, not an error you have to act on.
- **A reading of your beads momentarily fails in the background**: the board
  keeps showing the last good picture rather than blanking out, and it simply
  tries again on the next change. A transient hiccup can't wedge live updates
  permanently — it retries promptly instead of giving up.
- **A page falls badly behind** (for example, a tab left buried for a long
  time): rather than queue up an endless backlog, bdboard may skip ahead to the
  latest state. You might miss the *blow-by-blow*, but the next refresh shows the
  correct, current picture — freshness, not accuracy, is what briefly lapses.
- **Live updates can't connect at all** (rare): the page still works as a normal
  view of your beads. You can reload it by hand at any time to pull the current
  state, since the board always reads fresh data when it first loads.

## Good to know

The behaviour you'd most want to rely on is exercised by the project's automated
checks — that a single change produces exactly one refresh (not a storm), that a
trailing or isolated change is never silently dropped, and that a momentary
reading failure doesn't permanently freeze live syncing. In everyday use that
translates to a simple promise: if your beads change, the board will catch up on
its own, and the *live* indicator tells you when that promise is in force.

## Related

- [Your data is local & safe](../Concepts/your-data-is-local-and-safe.md) — why
  keeping the board current never involves the internet.
- [Bead lifecycle & the lanes](../Concepts/bead-lifecycle-and-lanes.md) — what's
  actually moving when the lanes re-draw themselves.
- [Time ranges & recent work](../Concepts/time-ranges-and-recent-work.md) — how
  the window you've chosen is preserved across an automatic refresh.
- [Take your first look](../Guides/take-your-first-look.md) — the orientation
  tour, including the live, read-only nature of the board.
- [Edit a bead](../Guides/edit-a-bead.md) — a deliberate change that the rest of
  the board (and your other tabs) will pick up live.
- [Create beads from a formula](../Guides/create-beads-from-a-formula.md) — pour
  new beads and watch them arrive on the board without a reload.
- [Explore history & trends](../Guides/explore-history-and-trends.md) — the
  History page that also stays current via live updates.
- [Features](index.md) — the rest of what bdboard does.
- [Overview](../Overview.md) — the big picture of the app.
