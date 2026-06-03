# FlowDoc Manifest (user)

> Single source of truth for what gets documented in the **user** edition. Each
> item below has exactly one doc bead (parented to the discovery bead
> `bdboard-mol-gyl`). When a doc is written, tick its box `- [ ]` → `- [x]` and
> bump the progress counters.

## Progress

- **Total items:** 15
- **Done:** 1
- **Remaining:** 14

By section: Features 0/6 | Concepts 0/4 | Guides 1/5

> [!IMPORTANT]
> **Section choice for the user edition.** Per the FlowDoc contract, **Endpoint**
> and **View** docs are *maintainer-only* (they expose HTTP paths, headers,
> `curl` commands, routes, and template names — exactly the developer leakage the
> user edition forbids), so they are intentionally **not** documented here. The
> end-to-end **Flow** material is delivered as actionable **User Guides** instead
> of internal flow write-ups, because a user wants "how do I do X?" not "how does
> the refresh pipeline schedule itself". The user-visible surface is therefore
> covered by **Features** (what each part does), **Concepts** (the mental models
> behind them), and **Guides** (step-by-step how-tos). See
> [`_FlowDocGuide.md`](./_FlowDocGuide.md) for the per-template overrides.

## Features

- [ ] 001 | Feature: The board (swim lanes & activity) -> [the-board](Features/the-board.md)
- [ ] 002 | Feature: Bead detail & editing -> [bead-detail-and-editing](Features/bead-detail-and-editing.md)
- [ ] 003 | Feature: History & trends -> [history-and-trends](Features/history-and-trends.md)
- [ ] 004 | Feature: Memory manager -> [memory-manager](Features/memory-manager.md)
- [ ] 005 | Feature: Create from formulas -> [create-from-formulas](Features/create-from-formulas.md)
- [ ] 006 | Feature: Live updates -> [live-updates](Features/live-updates.md)

## Concepts

- [ ] 007 | Concept: What is a bead? -> [what-is-a-bead](Concepts/what-is-a-bead.md)
- [ ] 008 | Concept: Bead lifecycle & the lanes -> [bead-lifecycle-and-lanes](Concepts/bead-lifecycle-and-lanes.md)
- [ ] 009 | Concept: Time ranges & recent work -> [time-ranges-and-recent-work](Concepts/time-ranges-and-recent-work.md)
- [ ] 010 | Concept: Your data is local & safe -> [your-data-is-local-and-safe](Concepts/your-data-is-local-and-safe.md)

## Guides

- [ ] 011 | User Guide: Take your first look -> [take-your-first-look](Guides/take-your-first-look.md)
- [ ] 012 | User Guide: Edit a bead -> [edit-a-bead](Guides/edit-a-bead.md)
- [ ] 013 | User Guide: Create beads from a formula -> [create-beads-from-a-formula](Guides/create-beads-from-a-formula.md)
- [ ] 014 | User Guide: Explore history & trends -> [explore-history-and-trends](Guides/explore-history-and-trends.md)
- [x] 015 | User Guide: Manage agent memories -> [manage-agent-memories](Guides/manage-agent-memories.md)
