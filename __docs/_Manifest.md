# FlowDoc Manifest (maintainer)

> Single source of truth for what gets documented. Each item below has exactly
> one doc bead (parented to the discovery bead `bdboard-mol-bfs`). When a doc is
> written, tick its box `- [ ]` -> `- [x]` and bump the progress counters.
>
> IDs are **banded / type-segmented** (Features 001+, Flows 010+, Endpoints
> 050+, Views 060+, Concepts 080+) so the type is readable from the number and
> new items slot in without renumbering. Section dirs and file names are
> **PascalCase**; the link target must equal the filename exactly.

## Progress

- **Total items:** 25
- **Done:** 8
- **Remaining:** 17

By section: Features 0/6 | Flows 0/4 | Endpoints 0/7 | Views 3/3 | Concepts 5/5

## Features

- [ ] 001 | Feature: Swim-lane board -> [SwimLaneBoard](Features/SwimLaneBoard.md)
- [ ] 002 | Feature: Bead detail & inline editing -> [BeadDetailAndInlineEditing](Features/BeadDetailAndInlineEditing.md)
- [ ] 003 | Feature: History & trends -> [HistoryAndTrends](Features/HistoryAndTrends.md)
- [ ] 004 | Feature: Memory management -> [MemoryManagement](Features/MemoryManagement.md)
- [ ] 005 | Feature: Formula pour -> [FormulaPour](Features/FormulaPour.md)
- [ ] 006 | Feature: Live auto-refresh -> [LiveAutoRefresh](Features/LiveAutoRefresh.md)

## Flows

- [ ] 010 | Flow: Server startup & workspace resolution -> [ServerStartup](Flows/ServerStartup.md)
- [ ] 011 | Flow: Live-refresh pipeline -> [LiveRefreshPipeline](Flows/LiveRefreshPipeline.md)
- [ ] 012 | Flow: Inline field-edit write path -> [FieldEditWritePath](Flows/FieldEditWritePath.md)
- [ ] 013 | Flow: Formula pour fan-out -> [FormulaPourFanout](Flows/FormulaPourFanout.md)

## Endpoints

- [ ] 050 | Endpoint: SSE events (/api/events) -> [SseEvents](Endpoints/SseEvents.md)
- [ ] 051 | Endpoint: Lanes API (/api/lanes, /api/lanes/closed, /api/counts) -> [LanesApi](Endpoints/LanesApi.md)
- [ ] 052 | Endpoint: History API (/api/history) -> [HistoryApi](Endpoints/HistoryApi.md)
- [ ] 053 | Endpoint: Memory API (/api/memory GET/POST/DELETE) -> [MemoryApi](Endpoints/MemoryApi.md)
- [ ] 054 | Endpoint: Formulas API (/api/formulas, form, pour) -> [FormulasApi](Endpoints/FormulasApi.md)
- [ ] 055 | Endpoint: Bead detail API (/api/bead/{id}, /audit, /raw) -> [BeadDetailApi](Endpoints/BeadDetailApi.md)
- [ ] 056 | Endpoint: Bead field-edit API (POST /api/bead/{id}/field) -> [BeadFieldEditApi](Endpoints/BeadFieldEditApi.md)

## Views

- [x] 060 | View: Board page (/) -> [BoardPage](Views/BoardPage.md)
- [x] 061 | View: History page (/history) -> [HistoryPage](Views/HistoryPage.md)
- [x] 062 | View: Memory page (/memory) -> [MemoryPage](Views/MemoryPage.md)

## Concepts

- [x] 080 | Concept: bd CLI as runtime source of truth -> [BdCliSourceOfTruth](Concepts/BdCliSourceOfTruth.md)
- [x] 081 | Concept: Store snapshot cache & change detection -> [StoreSnapshotCache](Concepts/StoreSnapshotCache.md)
- [x] 082 | Concept: Derive layer (pure view shaping) -> [DeriveLayer](Concepts/DeriveLayer.md)
- [x] 083 | Concept: Watcher debounce/cooldown & self-feedback skip -> [WatcherScheduling](Concepts/WatcherScheduling.md)
- [x] 084 | Concept: HTMX + server-rendered partials -> [HtmxPartialsArchitecture](Concepts/HtmxPartialsArchitecture.md)
