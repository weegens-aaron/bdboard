# The Memory Screen Reference

## Overview

The Memory screen lists your project's saved notes — short, named pieces of
context called **memories**. Each has a **key** (a short identifier) and a
**body** (markdown text). This page is a lookup for every control on the screen.

## Layout

| Region | What it shows |
|--------|---------------|
| Title | The screen name, "Memory". |
| Page navigation | Links to **Board**, **History**, and **Memory**. |
| Search box | Filters the list as you type. |
| + New Memory | Opens the dialog to create a memory. |
| Count | How many memories are shown (or how many match your search). |
| Memory list | One card per memory. |

## A memory card

| Element | Meaning |
|---------|---------|
| Key | The memory's short identifier. |
| Body | The note itself, rendered from markdown. |
| Edit button | Opens the dialog pre-filled to change the body. |
| Forget button | Opens a confirmation dialog to permanently remove the memory. |

## The new / edit dialog

| Control | What it does |
|---------|--------------|
| Key | The short identifier. Fixed when editing an existing memory. |
| Body | The note text (markdown supported). |
| Save Memory | Creates the memory, or updates the body if the key exists. |
| Cancel | Closes the dialog without saving. |

## The forget confirmation

| Control | What it does |
|---------|--------------|
| Warning | Explains that forgetting is permanent and can't be undone. |
| Yes, Forget It | Permanently removes the memory. |
| Cancel | Keeps the memory and closes the dialog. |

## Tips

> [!TIP]
> Saving with a key that already exists updates that memory rather than creating
> a duplicate — handy for editing, careful if you meant to add a new one.

> [!WARNING]
> Forgetting a memory is permanent. Memories give shared context to everyone
> working on the project, so removing one can quietly take away something others
> relied on.

> [!NOTE]
> The list updates live as memories change in any tab.

## See Also

- Guide: [Manage project memories](../Guides/ManagingMemories.md)
- Reference: [App navigation and status indicators](AppNavigation.md)
- Concept: [Live updates](../Concepts/LiveUpdates.md)
