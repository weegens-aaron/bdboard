# bdboard-mol-gpv — SOLID review: responsibility & coupling

Date: 2026-05-29
Scope: `src/bdboard/**` (Python only). Templates/CSS reviewed only where they
expose a coupling smell into Python.
Method: judgment-only (no mechanical CI gate exists for SRP/coupling). Read
every module, mapped responsibilities per file, counted function/route sizes,
traced the import + singleton graph. Findings are **refactor candidates ranked
by pain** — pain = (how much it hurts to change today) × (how often you must
change it) × (blast radius of getting it wrong).

> This is an assessment + recommendation deliverable. Per project rules it does
> NOT self-close the bead and does NOT auto-file the follow-up refactor beads;
> the "Recommended follow-up beads" section lists what to file if the team wants
> the work done.

---

## Module size census (the headline)

| Module | Lines | Over 600? | Responsibility count (observed) |
|---|---:|:---:|---|
| `app.py` | 1511 | **YES (2.5×)** | ~6 distinct jobs (see R1) |
| `bd.py` | 608 | **YES (just)** | 1 class, but ~5 concern clusters |
| `derive/history.py` | 503 | no | history math (cohesive) |
| `derive/lanes.py` | 400 | no | lane/topo math (cohesive) |
| `cli.py` | 147 | no | argparse + launch |
| `derive/__init__.py` | 117 | no | re-export facade |
| `store.py` | 107 | no | snapshot cache (exemplary SRP) |
| `derive/timeutil.py` | 97 | no | time helpers |
| `events.py` | 76 | no | SSE bus |
| `md.py` | 58 | no | markdown render |

Two modules breach the 600-line guideline. Only `app.py` is a genuine **god
module**; `bd.py` is a borderline-cohesive single class that's merely *large*.

---

## Refactor candidates, ranked by pain

### 🔴 R1 — `app.py` is a god module (1511 lines, ~6 responsibilities) — HIGHEST PAIN

`app.py`'s own docstring says it "composes routes over BdClient + Store +
derive." In reality it does *six* jobs, only one of which is "compose routes":

1. **Process bootstrap / config** — `_safe_cwd`, `_WORKSPACE`/`_BD_BIN`/`_ACTOR`
   env parsing, the `bd` / `store` / `bus` module-level singletons,
   `_validate_or_warn` (L29–147).
2. **Filesystem watcher + debounce/cooldown state machine** — `lifespan`,
   `_watch_beads`, `_settle_then_refresh`, `_settle_task`, plus the
   module-global mutable state `_last_refresh_at` / `_pending_settle`
   (L165–264, ~99 lines).
3. **SSE transport** — `sse_events` (L269–302), partner to `events.py`.
4. **HTTP route handlers** — ~15 endpoints (L303–1124).
5. **The field-editability domain model** — `FieldSpec`, `_FIELD_REGISTRY`,
   `_field_spec`, `_bead_is_editable`, `_classify_field`, `_field_row`,
   `_ordered_fields`, and the `_FIELD_ORDER` / `_KIND_*` / `_SHORT_META_FIELDS`
   tables (L1278–1505, **233 lines** of pure domain logic with zero web deps).
6. **Audit/diff view-shaping** — `_shape_audit`, `_diff_issue`, `_short`
   (L1447–1511).

**Why it's the worst pain:** every feature touches this file, so it's a
permanent merge-conflict magnet and the hardest file to reason about. Concern #5
(the field registry) is the most egregious: it's a self-contained domain model
(its docstrings explicitly call it "the single source of truth" and "the
extensibility seam") that imports nothing from FastAPI yet lives buried 1278
lines deep in the web module. Concern #2 keeps **module-global mutable refresh
state** (`_last_refresh_at`, `_pending_settle`) — an SRP *and* testability smell
that makes the debounce logic impossible to unit-test without importing the
whole app.

**Leaky abstraction inside R1:** route handlers reach directly for the
module-level `bd` / `store` / `bus` singletons (e.g. `_hydrate_epic_dependencies`
closes over the global `bd`). There is no dependency-injection seam, so handlers
can't be tested against a fake client without monkeypatching globals.

**Recommended split (highest-leverage first):**
- `fields.py` (or `fieldspec.py`) ← lift concern #5 wholesale (`FieldSpec`,
  `_FIELD_REGISTRY`, `_field_spec`, `_classify_field`, `_field_row`,
  `_ordered_fields`, `_bead_is_editable`, all the `_KIND_*`/`_FIELD_ORDER`/
  `_SHORT_META_FIELDS` tables). ~233 lines, pure, trivially unit-testable. This
  is the single biggest win and the lowest risk (no web deps to untangle).
- `watcher.py` ← lift concern #2 (`lifespan`, `_watch_beads`,
  `_settle_then_refresh`, `_settle_task`, watcher tunables). Convert the two
  module-globals into a small `Watcher` class holding its own state — kills the
  global-mutable-state smell and makes debounce/cooldown unit-testable.
- `audit.py` ← lift concern #6 (`_shape_audit`, `_diff_issue`, `_short`,
  `_dep_label`). Pure view-shaping, belongs next to `derive/`.
- Optionally split routes into an `api/` package by area (memory, formulas,
  bead-detail, history) once the above three leave `app.py` as a thin
  composition root.

Even just R1's first three bullets drop `app.py` from 1511 → ~900 lines and
remove all three of its non-web responsibilities.

---

### 🟠 R2 — `bd.py` BdClient mixes read/write/formula/cache concerns (608 lines) — MEDIUM PAIN

`BdClient` is one class doing five loosely-related jobs: workspace discovery,
**read** calls (`list_all`, `show_long`, `history`, `status_summary`,
`memories`), **write/mutation** calls (`remember`, `forget`, `rename_bead`,
`update_field`, `pour_formula`, `_run_mutate`), **formula introspection**
(`list_formulas`, `read_formula_variables`), and a **caching/dedup layer**
(`CacheEntry`, `_cached`, `_inflight`, `invalidate_caches`).

**Why medium (not high) pain:** unlike `app.py` it's genuinely *cohesive* —
everything is "talk to the bd CLI" and shares the `_subprocess_gate` semaphore,
so it reads cleanly today. The pain is latent: it's *just* over 600, every new
bd capability lands here, and the cache layer is interleaved with the read
methods (an ISP smell — a caller that only writes still depends on the whole
cache surface).

**Recommended (only if it keeps growing):**
- Extract the cache/dedup mechanics (`CacheEntry`, `_cached`, `_inflight`,
  TTL constants) into a small `_BdCache` collaborator the client *has*, rather
  than *is*. Keeps `BdClient` focused on "run bd, parse JSON."
- If formula support expands, peel `list_formulas` / `read_formula_variables` /
  `pour_formula` into a `FormulaClient`.
- Lower urgency than R1 — flag, don't rush. Splitting a cohesive class purely to
  duck under a line count would *hurt* cohesion (Zen: "flat is better than
  nested," but also don't fragment what reads well). Do it when the next formula
  feature forces a third reason to open this file.

---

### 🟡 R3 — `derive` facade re-exports private helpers for tests (leaky abstraction) — LOW PAIN

`derive/__init__.py` re-exports **18 underscore-prefixed private helpers**
(`_epic_lane_rank`, `_topo_component_order`, `_resolve_bounds`, `_percentile`,
…) in `__all__` "for tests / backward compat." That's the test suite reaching
*through* the package's public boundary into its internals — a classic leaky
abstraction. Renaming any internal helper now silently breaks the published
surface, and `__all__` advertising names starting with `_` is self-contradictory
(underscore *means* private).

**Recommended (cheap, do-when-touching-tests):**
- Have tests import the private helpers from their owning submodule
  (`from bdboard.derive.lanes import _topo_component_order`) instead of the
  package root, then drop the underscore names from `__init__`'s `__all__`.
- The package keeps a clean public surface; internals stay free to move.
- Low pain because it's contained to the test import lines and the facade — no
  production behavior changes.

---

### 🟡 R4 — handlers depend on module-global singletons (no DI seam) — LOW/MEDIUM PAIN

Covered as a sub-smell of R1 but worth its own line because it's the root cause
of bdboard's test friction: `bd`, `store`, and `bus` are module-level singletons
that handlers close over directly. There's no FastAPI dependency-injection
(`Depends(...)`) and no app-factory, so:
- you can't spin up the app against a fake `BdClient` without monkeypatching the
  module global, and
- the watcher's `store` / `bus` references are equally hard-wired.

**Recommended:** introduce an app-factory (`create_app(bd, store, bus)`) and/or
wire the singletons through `Depends`. Best tackled *as part of* R1's watcher and
route extraction so you only restructure once. Tagged separately so the team can
decide whether to bundle it or defer.

---

## Things that are GOOD (don't "fix" these)

A SOLID review that only lists sins is noise. These are the load-bearing
counter-examples that show the codebase isn't uniformly bad:

- **`store.py`** — textbook SRP. One job (cache the bead list + detect change),
  a single lock, crisp docstrings, ~107 lines. This is the standard the rest of
  the codebase should aspire to.
- **`events.py` / `md.py`** — small, single-purpose, no leakage.
- **`derive/` submodule split (bdboard-2ic)** — `history.py` and `lanes.py` are
  large but *cohesive* (one mathematical concern each) and pure (no I/O). They
  are correctly *under* 600 and should NOT be split further just for size — that
  would fragment cohesion.
- The **`_KIND_*` set + template-dispatch pattern** (R1 concern #5) is itself a
  nice open/closed design — it's just in the wrong *file*, not wrongly designed.

---

## Ranked summary (the deliverable)

| Rank | Candidate | Pain | Smell | Effort | Risk |
|---|---|:---:|---|:---:|:---:|
| 1 | **R1** `app.py` god module → extract `fields.py`, `watcher.py`, `audit.py` | 🔴 High | SRP, global mutable state, leaky singleton access | M–L | Low (fields.py) → Med |
| 2 | **R2** `bd.py` BdClient → extract `_BdCache` (and later `FormulaClient`) | 🟠 Med | SRP/ISP, latent (just over 600) | M | Low |
| 3 | **R3** `derive/__init__` stops re-exporting `_private` helpers | 🟡 Low | leaky abstraction | S | Low |
| 4 | **R4** introduce DI/app-factory seam for `bd`/`store`/`bus` | 🟡 Low–Med | tight coupling, untestable handlers | M | Med (bundle w/ R1) |

**If you do nothing else, do R1's `fields.py` extraction** — it removes 233
lines of pure domain logic from the god module, is near-zero risk (no web
dependencies to untangle), and makes the field-editability model independently
testable. Highest reward-to-risk ratio in the whole list.

---

## Recommended follow-up beads (file these if the team wants the work)

1. `task` — Extract field-editability model from `app.py` into `fields.py` (R1a).
2. `task` — Extract watcher + debounce state machine into a `Watcher` class /
   `watcher.py`, killing module-global mutable refresh state (R1b).
3. `task` — Extract audit/diff view-shaping into `audit.py` (R1c).
4. `task` — Extract `_BdCache` collaborator from `BdClient` (R2). Lower priority.
5. `chore` — Tests import `_private` derive helpers from their submodules; trim
   `derive.__init__.__all__` to the real public surface (R3).
6. `task` — Add `create_app()` factory / `Depends` seam for `bd`/`store`/`bus`,
   ideally bundled with bead #2 (R4).

> No code was changed by this review — it is assessment-only. The bead is left
> for the LLM judge pipeline to close per project rules.
