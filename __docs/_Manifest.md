# FlowDoc Manifest (maintainer)

> Single source of truth for what gets documented. Each item below has exactly
> one doc bead (parented to the discovery bead `bdboard-mol-gh2`). When a doc is
> written, tick its box `- [ ]` -> `- [x]` and bump the progress counters.

## Progress

- **Total items:** 25
- **Done:** 14
- **Remaining:** 11

By section: Features 0/6 | Flows 0/4 | Endpoints 6/7 | Views 3/3 | Concepts 5/5

## Features

- [ ] 001 | Feature: Swim-lane board -> [swim-lane-board](Features/swim-lane-board.md)
- [ ] 002 | Feature: Bead detail & inline editing -> [bead-detail-and-inline-editing](Features/bead-detail-and-inline-editing.md)
- [ ] 003 | Feature: History & trends -> [history-and-trends](Features/history-and-trends.md)
- [ ] 004 | Feature: Memory management -> [memory-management](Features/memory-management.md)
- [ ] 005 | Feature: Formula pour -> [formula-pour](Features/formula-pour.md)
- [ ] 006 | Feature: Live auto-refresh -> [live-auto-refresh](Features/live-auto-refresh.md)

## Flows

- [ ] 007 | Flow: Server startup & workspace resolution -> [server-startup](Flows/server-startup.md)
- [ ] 008 | Flow: Live-refresh pipeline -> [live-refresh-pipeline](Flows/live-refresh-pipeline.md)
- [ ] 009 | Flow: Inline field-edit write path -> [field-edit-write-path](Flows/field-edit-write-path.md)
- [ ] 010 | Flow: Formula pour fan-out -> [formula-pour-fanout](Flows/formula-pour-fanout.md)

## Endpoints

- [ ] 011 | Endpoint: SSE events (/api/events) -> [sse-events](Endpoints/sse-events.md)
- [x] 012 | Endpoint: Lanes API (/api/lanes, /api/lanes/closed, /api/counts) -> [lanes-api](Endpoints/lanes-api.md)
- [x] 013 | Endpoint: History API (/api/history) -> [history-api](Endpoints/history-api.md)
- [x] 014 | Endpoint: Memory API (/api/memory GET/POST/DELETE) -> [memory-api](Endpoints/memory-api.md)
- [x] 015 | Endpoint: Formulas API (/api/formulas, form, pour) -> [formulas-api](Endpoints/formulas-api.md)
- [x] 016 | Endpoint: Bead detail API (/api/bead/{id}, /audit, /raw) -> [bead-detail-api](Endpoints/bead-detail-api.md)
- [x] 017 | Endpoint: Bead field-edit API (POST /api/bead/{id}/field) -> [bead-field-edit-api](Endpoints/bead-field-edit-api.md)

## Views

- [x] 018 | View: Board page (/) -> [board-page](Views/board-page.md)
- [x] 019 | View: History page (/history) -> [history-page](Views/history-page.md)
- [x] 020 | View: Memory page (/memory) -> [memory-page](Views/memory-page.md)

## Concepts

- [x] 021 | Concept: bd CLI as runtime source of truth -> [bd-cli-source-of-truth](Concepts/bd-cli-source-of-truth.md)
- [x] 022 | Concept: Store snapshot cache & change detection -> [store-snapshot-cache](Concepts/store-snapshot-cache.md)
- [x] 023 | Concept: Derive layer (pure view shaping) -> [derive-layer](Concepts/derive-layer.md)
- [x] 024 | Concept: Watcher debounce/cooldown & self-feedback skip -> [watcher-scheduling](Concepts/watcher-scheduling.md)
- [x] 025 | Concept: HTMX + server-rendered partials -> [htmx-partials-architecture](Concepts/htmx-partials-architecture.md)