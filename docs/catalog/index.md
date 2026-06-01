# Feature Catalog Index

A structured reference covering every user-visible feature and supporting
infrastructure in bdboard. Each feature has its own markdown doc following the
canonical section order defined in [`_TEMPLATE.md`](./_TEMPLATE.md):
**What it shows / Where the data comes from / What changes its state /
Edge cases & notes / Source files**.

Features are grouped by the page (or layer) they belong to. Links are relative
and point at the target filename for each feature's catalog doc. Some docs may
not exist yet — they are the deliverables of the per-feature beads under epic
`bdboard-1h9`.

## Board

The primary dashboard view: lanes, counts, navigation, and the bead modal.

| Feature | Doc | Bead |
| --- | --- | --- |
| Primary navigation | [nav.md](./nav.md) | bdboard-df2 |
| Open lanes | [board-lanes.md](./board-lanes.md) | bdboard-bkz |
| Closed lane | [board-closed-lane.md](./board-closed-lane.md) | bdboard-bpu |
| Counts strip (upper-right stats) | [board-counts.md](./board-counts.md) | bdboard-9c2 |
| Time-window filter (12h/1d/3d) | [board-time-filter.md](./board-time-filter.md) | bdboard-u7t |
| Theme toggle (light/dark) | [theme-toggle.md](./theme-toggle.md) | bdboard-krb |
| Bead detail modal | [bead-modal.md](./bead-modal.md) | bdboard-glo |
| Inline field editing | [bead-inline-edit.md](./bead-inline-edit.md) | bdboard-62f6 |
| Bead audit/history view | [bead-audit.md](./bead-audit.md) | bdboard-95a5 |
| Bead raw JSON view | [bead-raw.md](./bead-raw.md) | bdboard-tp73 |
| Pour Formula dialog | [pour-formula.md](./pour-formula.md) | bdboard-obv |

## History

The history page: trends over time plus a paginated record list.

| Feature | Doc | Bead |
| --- | --- | --- |
| Created-vs-closed chart | [history-chart.md](./history-chart.md) | bdboard-l1th |
| Stats summary | [history-stats.md](./history-stats.md) | bdboard-tzkm |
| Paginated list | [history-list.md](./history-list.md) | bdboard-mwqf |

## Memory

The memory page: list, search, create, and delete persistent insights.

| Feature | Doc | Bead |
| --- | --- | --- |
| List & search | [memory-list.md](./memory-list.md) | bdboard-jbbb |
| Create | [memory-create.md](./memory-create.md) | bdboard-qds3 |
| Delete | [memory-delete.md](./memory-delete.md) | bdboard-0221 |

## Infra

Cross-cutting infrastructure that supports the user-visible pages.

| Feature | Doc | Bead |
| --- | --- | --- |
| SSE live-refresh pipeline | [sse-live-refresh.md](./sse-live-refresh.md) | bdboard-d1o0 |
| Store cache / data source of truth | [store-cache.md](./store-cache.md) | bdboard-ex4w |
