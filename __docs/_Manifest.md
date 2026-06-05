# _Manifest — bdboard maintainer documentation

Tracks every item to document. Each doc bead fills its template from
`_FlowDocGuide.md`, then ticks its line `[x]` here and bumps the counters.

## Progress

- **Total:** 39
- **Done:** 33
- **Remaining:** 6

### By band

| Band | Total | Done |
| --- | --- | --- |
| Features | 7 | 1 |
| Flows | 5 | 5 |
| Endpoints | 15 | 15 |
| Views | 3 | 3 |
| Concepts | 9 | 9 |

---

## Features (001+)

- [ ] 001 | Feature: Live Board -> [Live Board](Features/LiveBoard.md)
- [ ] 002 | Feature: Bead Detail Modal -> [Bead Detail Modal](Features/BeadDetailModal.md)
- [ ] 003 | Feature: Manual Field Editing -> [Manual Field Editing](Features/ManualFieldEditing.md)
- [ ] 004 | Feature: Memory Curation -> [Memory Curation](Features/MemoryCuration.md)
- [ ] 005 | Feature: Formula Pour -> [Formula Pour](Features/FormulaPour.md)
- [ ] 006 | Feature: History & Analytics -> [History & Analytics](Features/HistoryAnalytics.md)
- [x] 007 | Feature: Live Updates -> [Live Updates](Features/LiveUpdates.md)

## Flows (010+)

- [x] 010 | Flow: Board First Paint -> [Board First Paint](Flows/BoardFirstPaint.md)
- [x] 011 | Flow: Watcher Refresh Cycle -> [Watcher Refresh Cycle](Flows/WatcherRefreshCycle.md)
- [x] 012 | Flow: SSE Live Update -> [SSE Live Update](Flows/SseLiveUpdate.md)
- [x] 013 | Flow: Field Edit Write Path -> [Field Edit Write Path](Flows/FieldEditWritePath.md)
- [x] 014 | Flow: Formula Pour Pipeline -> [Formula Pour Pipeline](Flows/FormulaPourPipeline.md)

## Endpoints (050+)

- [x] 050 | Endpoint: GET /api/events -> [GET /api/events](Endpoints/GetApiEvents.md)
- [x] 051 | Endpoint: GET /api/lanes -> [GET /api/lanes](Endpoints/GetApiLanes.md)
- [x] 052 | Endpoint: GET /api/lanes/closed -> [GET /api/lanes/closed](Endpoints/GetApiLanesClosed.md)
- [x] 053 | Endpoint: GET /api/counts -> [GET /api/counts](Endpoints/GetApiCounts.md)
- [x] 054 | Endpoint: GET /api/history -> [GET /api/history](Endpoints/GetApiHistory.md)
- [x] 055 | Endpoint: GET /api/memory -> [GET /api/memory](Endpoints/GetApiMemory.md)
- [x] 056 | Endpoint: POST /api/memory -> [POST /api/memory](Endpoints/PostApiMemory.md)
- [x] 057 | Endpoint: DELETE /api/memory/{key} -> [DELETE /api/memory/{key}](Endpoints/DeleteApiMemory.md)
- [x] 058 | Endpoint: GET /api/formulas -> [GET /api/formulas](Endpoints/GetApiFormulas.md)
- [x] 059 | Endpoint: GET /api/formulas/{name}/form -> [GET /api/formulas/{name}/form](Endpoints/GetApiFormulaForm.md)
- [x] 060 | Endpoint: POST /api/formulas/{name}/pour -> [POST /api/formulas/{name}/pour](Endpoints/PostApiFormulaPour.md)
- [x] 061 | Endpoint: GET /api/bead/{id} -> [GET /api/bead/{id}](Endpoints/GetApiBead.md)
- [x] 062 | Endpoint: GET /api/bead/{id}/audit -> [GET /api/bead/{id}/audit](Endpoints/GetApiBeadAudit.md)
- [x] 063 | Endpoint: GET /api/bead/{id}/raw -> [GET /api/bead/{id}/raw](Endpoints/GetApiBeadRaw.md)
- [x] 064 | Endpoint: POST /api/bead/{id}/field -> [POST /api/bead/{id}/field](Endpoints/PostApiBeadField.md)

## Views (070+)

- [x] 070 | View: Board -> [Board (/)](Views/BoardView.md)
- [x] 071 | View: History -> [History (/history)](Views/HistoryView.md)
- [x] 072 | View: Memory -> [Memory (/memory)](Views/MemoryView.md)

## Concepts (080+)

- [x] 080 | Concept: bd CLI as Source of Truth -> [bd CLI as Source of Truth](Concepts/BdCliSourceOfTruth.md)
- [x] 081 | Concept: Subprocess Serialization & Caching -> [Subprocess Serialization & Caching](Concepts/SubprocessSerializationAndCaching.md)
- [x] 082 | Concept: Filesystem Watcher -> [Filesystem Watcher](Concepts/FilesystemWatcher.md)
- [x] 083 | Concept: Store Snapshot & Change Detection -> [Store Snapshot & Change Detection](Concepts/StoreSnapshotChangeDetection.md)
- [x] 084 | Concept: Derive Layer -> [Derive Layer](Concepts/DeriveLayer.md)
- [x] 085 | Concept: SSE Event Bus -> [SSE Event Bus](Concepts/SseEventBus.md)
- [x] 086 | Concept: CSRF Protection -> [CSRF Protection](Concepts/CsrfProtection.md)
- [x] 087 | Concept: Field Editability Registry -> [Field Editability Registry](Concepts/FieldEditabilityRegistry.md)
- [x] 088 | Concept: Epic Lane Sequencing -> [Epic Lane Sequencing](Concepts/EpicLaneSequencing.md)
