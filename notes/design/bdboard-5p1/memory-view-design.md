# Design: Memory View for browsing `bd remember` entries

- **Bead:** bdboard-5p1 (design)
- **Epic:** bdboard-12f — Memory View: browse, search, and curate bd memories from the dashboard
- **Status:** design / spec only — **no implementation in this bead**
- **Date:** 2026-05-28

> This document is the deliverable for bdboard-5p1. It defines scope, the
> data contract, the chosen design decisions, and a breakdown into child
> implementation beads for the epic. It deliberately ships **no** runtime
> code.

---

## 1. Problem & goal

`bd` accumulates persistent memories via `bd remember` / `bd memories`.
Today they are only reachable through the CLI and are injected at
`bd prime`. There is no way to browse, search, or curate them from the
bdboard dashboard.

**Goal:** a dashboard surface that lets a user *view* and *search* bd
memories without leaving bdboard, with the data contract and CRUD posture
decided and recorded so the epic's child beads can be implemented
deterministically.

---

## 2. Spike: the bd memory CLI surface (confirmed by hand)

All four commands exist on the installed `bd` and were exercised against
this workspace:

| Command | Purpose | Notes for the view |
| --- | --- | --- |
| `bd memories [--json]` | List all memories | Source of truth for the browse list. |
| `bd memories <term> [--json]` | Search memories | **Server-side** case-insensitive substring across key + body. |
| `bd recall <key> [--json]` | Fetch one memory | Useful for a detail/permalink fetch. |
| `bd remember "<body>" --key <key>` | Create **or update** (upsert by key) | Curate: create/edit. |
| `bd forget <key>` | Delete a memory by key | Curate: delete. |

### 2.1 `--json` data contract (CONFIRMED)

`bd memories --json` returns a **flat JSON object** mapping key → body,
plus a sentinel `schema_version`:

```json
{
  "agent-no-root-litter": "Verification and completion artifacts go in bead notes ...",
  "bd-edit-stalls": "Never run bd edit — it opens $EDITOR ...",
  "schema_version": 1
}
```

A scoped search returns the same shape, filtered:

```json
{
  "bd-edit-stalls": "Never run bd edit — ...",
  "schema_version": 1
}
```

**Contract rules the implementation MUST honor:**

1. **Strip the `schema_version` key** before rendering — it is metadata, not
   a memory. (Equally, branch on `schema_version` to stay forward-compatible
   if the shape ever changes.)
2. Each entry is `{key: str, body: str}`. There are **no nested fields**.
3. An empty / no-match search returns just `{"schema_version": 1}` (i.e. an
   "empty" result still carries the sentinel). The UI's empty-state logic must
   treat "only schema_version present" as zero results.

### 2.2 🚨 Gap finding — NO recency / timestamp data

The epic success criteria include **"sortable by recency."** The
`bd memories --json` output carries **no `created_at` / `updated_at` /
ordering metadata** — it is a bare key→body map. The CLI's human output is
alphabical by key, not chronological.

**Consequence:** "sort by recency" is **not satisfiable** from the current
bd JSON contract. This is recorded as a design constraint and split out as
its own child bead (see §6, bead D) so the epic's recency criterion is
explicitly tracked rather than silently dropped. The v1 view sorts
**alphabetically by key** (deterministic, matches CLI), and recency is
deferred pending an upstream bd capability or a local provenance source.

#### 2.2.1 Spike resolution (bead D: bdboard-12f.2)

**Investigation findings (2026-05-29):**

1. **Upstream bd capability:** `bd memories --json` (bd 1.0.4) returns a
   flat `{key: body, schema_version: 1}` object with NO timestamp fields.
   `bd recall <key> --json` likewise returns only `{found, key, value,
   schema_version}`. There is no bd CLI flag to request recency metadata.

2. **Local provenance source:** Memories are stored in the Dolt database's
   `config` table with `kv.memory.<key>` prefixes. Dolt's version control
   history (`dolt_diff_config` + `dolt_log`) **does** carry timestamp
   provenance — e.g.:
   ```sql
   SELECT d.to_key, l.date, d.diff_type
   FROM dolt_diff_config d
   JOIN dolt_log l ON d.to_commit = l.commit_hash
   WHERE d.to_key LIKE 'kv.memory.%'
   ORDER BY l.date DESC;
   ```
   This returns `(memory_key, created_at, diff_type)` tuples with
   millisecond precision.

3. **Architectural cost of using Dolt directly:**
   - Violates bdboard's design principle: "runtime source of truth is
     bd CLI JSON output" (see `stack-overview` memory).
   - Requires shelling out to `dolt sql` (embedded Dolt isn't reachable
     via the bd wrapper).
   - Creates undocumented coupling to bd's internal storage schema.
   - `dolt` binary may not be on PATH in all deployment contexts.

**Decision: recency is OUT OF SCOPE for v1.**

- The data exists but is not exposed through the bd CLI contract.
- Bypassing bd CLI to query Dolt directly is architecturally unsound for
  a P4 "nice-to-have" feature.
- v1 sorts alphabetically by key (deterministic, matches CLI).
- Proper fix: upstream bd should add `created_at` / `updated_at` fields
  to `bd memories --json` output. When/if that lands, bdboard can trivially
  consume it via the existing `BdClient.memories()` plumbing.
- This decision is recorded here and in the bead notes for traceability.

---

## 3. Design decisions (recorded per epic success criteria)

### D1 — Read-only in v1; curate is a later phase (DECIDED: read-only)

The epic asks for an explicit **read-only vs full CRUD** decision.

**Decision: v1 is read-only (browse + search).** Rationale:

- Memories are a *shared, cross-session* knowledge store injected at
  `bd prime`. Casual edit/delete from a dashboard is higher-blast-radius
  than editing a single bead; a stray "forget" silently degrades every
  future agent session.
- bdboard's current posture is a **read-mostly viewer** of bd state (it
  shells `bd list/show/history` and never mutates). Introducing write paths
  (`remember`/`forget`) is a meaningful architectural step (CSRF posture,
  optimistic UI, refresh invalidation, audit) that deserves its own bead,
  not a rider on the first view.
- The CLI already provides safe curate primitives; power users curate there
  today with zero data loss risk.

**Curate (create/edit/forget from UI) is explicitly scoped as a follow-up**
child bead (§6, bead E), gated behind this view landing first. The data
contract above already confirms the write primitives exist, so the follow-up
is "wire the buttons," not "discover the API."

### D2 — Markdown rendering via the shared renderer (DECIDED)

Per the `modal-ux` memory and to stay consistent with the bead modal,
memory **bodies render through the existing shared markdown filter**
(`md.render`, registered as the Jinja `md` filter in `app.py`). Keys render
as plain monospace text (they are slugs, not markdown). No new renderer.

### D3 — Navigation: dedicated route + masthead nav entry (DECIDED)

- New route **`GET /memory`** returns a full page (extends `base.html`),
  symmetric with the dashboard index at `/`.
- New partial route **`GET /api/memory`** returns just the list region
  (HTMX swap target), symmetric with `/api/lanes`.
- A **nav entry in the masthead** links `/` ⇄ `/memory`. The dashboard
  currently has no nav chrome, so a minimal masthead nav is part of bead C.

### D4 — Search: server-side via bd, debounced (DECIDED)

Search uses `bd memories <term> --json` (server-side filtering, matches CLI
semantics exactly) rather than re-implementing substring matching in the
browser. The search box posts to `/api/memory?q=<term>` with an HTMX
**`keyup changed delay:250ms`** debounce, swapping the list region. Empty
`q` lists all. This reuses bd's own match logic (no divergence) and keeps
the partial cacheable per-query.

### D5 — Live refresh: out of scope for v1 (DECIDED)

The existing SSE/watchfiles pipeline watches `.beads/` for bead changes.
Memory writes may or may not touch watched files in a way that maps cleanly
to a "memories changed" signal, and v1 is read-only anyway. v1 fetches
memories on page load / search; a **manual refresh affordance** (re-fetch
button) covers staleness. Wiring memories into SSE is deferred to the
curate bead (E), where writes make live invalidation actually useful.

---

## 4. Data flow & architecture fit

```
Browser ──GET /memory──────────────► app.py: page_memory()
                                         └─ renders memory.html (base)
Browser ──GET /api/memory?q=──────► app.py: api_memory()
                                         └─ Bd.memories(q) ──► subprocess:
                                              bd memories [q] --json
                                         └─ strip schema_version
                                         └─ sort by key
                                         └─ render partials/memory_list.html
```

- **New `Bd.memories(query: str | None)` method** in `bd.py`, built on the
  existing `_run_json` plumbing (subprocess gate + timeout + JSON parse +
  user-safe error messages). It strips `schema_version` and returns a sorted
  `list[dict]` of `{"key", "body"}`. This mirrors `list_all()` and inherits
  the semaphore/cache discipline already in the module.
- **Reuse** the `md` Jinja filter for bodies; no new template helpers beyond
  the new partial.
- **No new dependencies.** Pure FastAPI + HTMX + existing renderer.

---

## 5. UI / UX spec (v1, read-only)

- **Layout:** full page at `/memory`, masthead consistent with dashboard
  (kicker "bdboard", workspace title), plus a back/nav link to lanes.
- **Search strip:** single text input, `aria-label="Search memories"`,
  HTMX-debounced to `/api/memory`. Shows result count
  (`N memories` / `N matching "<q>"`).
- **List:** vertical list of memory cards. Each card:
  - **Key** — monospace, treated as the card heading (`<h3>`-level for a11y).
  - **Body** — rendered through the shared markdown filter.
  - Optional **copy-key** affordance (P-low).
- **Empty states:**
  - No memories at all → friendly "No memories yet — run `bd remember` to add one."
  - Search with no match → "No memories matching \"<q>\"." (mirrors CLI copy).
- **Sort:** alphabetical by key (deterministic; recency deferred — see §2.2).
- **Accessibility (WCAG 2.2 AA):**
  - Search input has a programmatic label; result count is in an
    `aria-live="polite"` region so screen readers hear filter updates.
  - Cards are list semantics (`role="list"` / `<li>`), keys as headings for
    navigation.
  - Color usage follows the existing token palette; no new contrast risks
    (text on card background reuses the dashboard's vetted pairs). Any new
    badge/state must clear 4.5:1 text / 3:1 UI, matching the existing
    filter-badge contrast tests.

---

## 6. Child bead breakdown (for the epic)

Implementation beads filed under bdboard-12f (this design is the canonical
plan; the bead IDs below are the filed instances, dependency-wired so that
`bd ready` surfaces A and D first).

| Bead | ID | Title | Scope | Depends on |
| --- | --- | --- | --- | --- |
| **A** | bdboard-12f.1 | `Bd.memories()` client + JSON contract handling | Add async `memories(query)` to `bd.py` on `_run_json`; strip `schema_version`; sort by key; unit-test the empty/sentinel/search shapes. | — |
| **B** | bdboard-12f.4 | `/api/memory` partial + `memory_list.html` | HTMX list partial rendering key + markdown body; debounced server-side search; empty states. | A |
| **C** | bdboard-12f.5 | `/memory` full page + masthead nav | `memory.html` extends `base.html`; add minimal masthead nav linking `/` ⇄ `/memory`. | B |
| **D** | bdboard-12f.2 | Recency metadata spike / decision | Resolve the §2.2 gap: either consume an upstream bd field if/when it exists, or decide recency is permanently out of scope. Tracks the epic's "sortable by recency" criterion. **→ RESOLVED: out of scope for v1; see §2.2.1.** | — |
| **E** | bdboard-12f.3 | Curate (create / edit / forget) from UI | Follow-up: wire `bd remember` / `bd forget` write paths, refresh invalidation, confirm-before-forget, SSE wiring. Gated behind A–C. | A, B, C |

Acceptance mapping to the epic's Success Criteria:

- "view all memories (key + body)" → A + B + C.
- "searchable/filterable by keyword" → B (D4 server-side search).
- "sortable by recency" → **D** (explicitly gated by the §2.2 gap; v1 sorts by key; **resolved as out of scope pending upstream bd support — see §2.2.1**).
- "read-only vs CRUD decision recorded" → **D1 (this doc)**; CRUD itself → E.
- "`bd memories --json` shape confirmed" → **§2.1 (confirmed here)**, hardened in A.
- "bodies render with shared markdown renderer" → D2 + B.
- "reachable via clear navigation (route + nav entry)" → C (D3).

---

## 7. Out of scope for this bead

- Any runtime/template/route code (this is a design bead).
- Curate write paths (deferred to bead E).
- SSE live-refresh of memories (deferred to bead E).
- Recency sorting (blocked on the §2.2 data gap, tracked by bead D).
