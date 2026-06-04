# Quick Start: Open your first board

## What You'll Achieve

A live board open in your browser, showing your project's work, so you can tell
at a glance what's ready to pick up.

## Prerequisites

- bdboard installed — see [Installation](Installation.md).
- A terminal open inside the project folder you want to look at.

## Step 1: Start bdboard

In your terminal, from inside the project folder, run:

```sh
bdboard
```

**Expected result:** a browser tab opens with your project's board, and your
terminal prints the address it's serving. If a tab doesn't open on its own, open
the address the terminal prints.

> [!TIP]
> Already have something running on the usual address? bdboard quietly picks the
> next free one and prints it — you don't have to do anything.

## Step 2: Read the lanes

Look across the board. Your work is grouped into columns called **lanes**:

- **Epics** — the big containers, shown in a strip across the top.
- **Deferred** — work intentionally put off for now.
- **Blocked** — work that's waiting on something else to finish first.
- **Ready** — work you can pick up right now.
- **In Progress** — work someone is actively doing.
- **Closed** — work finished recently.

**Expected result:** every item your project tracks appears as a card in exactly
one lane, highest-priority and newest first.

> [!NOTE]
> You can't drag cards between lanes. A card's lane is decided automatically from
> its state and what it's waiting on. To learn why, see
> [Lanes & how cards are sorted](../Concepts/LanesExplained.md).

## Step 3: Open a card

Click any card.

**Expected result:** a panel opens showing everything about that item — its full
description, its history, and (if it's still open) controls to fix a field. Close
the panel to return to the board.

> [!TIP]
> Want the details on editing? See
> [Inspect a bead in detail](../Guides/InspectingABead.md) and
> [Edit a bead's fields](../Guides/EditingABead.md).

## Step 4: Watch it stay current

Leave the board open. As work changes in your project — yours or a teammate's —
the board updates on its own.

**Expected result:** cards move, appear, and disappear without you reloading the
page.

## Step 5 (optional): Adjust how it launches

You can change a couple of things about how bdboard starts:

- **Point it at a different project** without changing folders first, by passing
  the folder you want.
- **Stop the browser tab from opening automatically**, if you'd rather open it
  yourself.

**Expected result:** bdboard launches the way you prefer. Run `bdboard --help`
to see the available options.

## Common Issues

| Symptom | What to do |
|---------|------------|
| No browser tab opened | Open the address bdboard printed in the terminal. |
| Lanes show errors | bd isn't available. See [Installation](Installation.md). |
| The board is empty | Pull in the project history once with `bd bootstrap --yes`, then refresh. |
| Stale-looking board | Refresh once; if it persists, the project may simply have no recent activity — check the [History screen](../Reference/HistoryScreen.md). |

## What You Learned

You started bdboard, read the lanes, opened a card, and saw the board keep itself
up to date.

## Next Steps

- Learn the board in depth: [View your work on the board](../Guides/ViewingYourWork.md).
- Walk through a full first session: [Your first bdboard session](../Tutorials/FirstSession.md).
- Look up any screen or control in the [Reference](../Reference/index.md).
