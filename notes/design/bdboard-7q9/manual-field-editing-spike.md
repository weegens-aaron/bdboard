# Spike: manual editing of bead field values in bdboard

- **Bead:** bdboard-7q9 (spike)
- **Parent epic:** bdboard-o9v — Enable manual editing of bead field values
- **Status:** spike / notes + recommendation only — **no shipped editing code**
- **Date:** 2026-05-29
- **Scope guardrail:** edit the **VALUES of fields that already exist** on a
  bead (primarily agent-authored beads). **NOT** in scope: adding, removing,
  or otherwise changing the *set/shape* of fields.

> Deliverable for bdboard-7q9. Verified empirically against the installed `bd`
> (`bd update --help`, live `bd show … --json`) and against the current
> bdboard source, not docs alone. Outputs: an editability matrix, an
> architecture recommendation, and proposed follow-up beads. **Nothing here
> ships an edit path** — that is the next epic phase's work.

---

## 1. How bdboard talks to bd today (the substrate we build on)

bdboard is a FastAPI + HTMX dashboard whose **runtime source of truth is bd
CLI JSON output**, not `.beads/issues.jsonl` (memory `stack-overview`). The
relevant existing machinery:

- **Reads:** `src/bdboard/bd.py` `BdClient` wraps `bd` subprocess calls
  (`list_all`, `show_long`, `history`, `memories`, `status_summary`), all
  serialized through one `asyncio.Semaphore(1)` (`_subprocess_gate`) because
  bd's embedded dolt server is single-writer and lock-prone under concurrency.
- **There is already a write path.** Memory mutations (`remember` / `forget`)
  go through `BdClient._run_mutate` → `bd remember …` / `bd forget …`, then
  `self._memories_cache.clear()`, then the route broadcasts `beads_changed`
  over SSE. **This is the exact template a field-edit path should copy.**
- **CSRF is already solved.** `app.py` mints `_CSRF_TOKEN = secrets.token_urlsafe(32)`
  at startup, exposes it as a Jinja global, validates via `_check_csrf` (header
  `X-CSRF-Token` or form field `csrf_token`). The memory form
  (`templates/memory.html`) shows the HTMX pattern: `hx-headers` for JS posts +
  a hidden form field fallback.
- **Live refresh closes the loop.** `watchfiles` watches `.beads/`, `Store.refresh`
  re-runs `bd list`, SSE broadcasts `beads_changed` only on structural change
  (memory `refresh-architecture`). After a mutation we also `invalidate_caches()`
  so the next `show_long` returns post-edit state instead of up-to-10s-stale cache.

**Implication:** bdboard already has *every architectural primitive* an edit
feature needs (serialized mutate path, CSRF, optimistic re-render, SSE
broadcast, cache invalidation). The edit epic is mostly **wiring + UI + a
careful per-field whitelist**, not new infrastructure.

---

## 2. The display layer (where edit affordances must attach)

The bead modal (`templates/partials/bead_modal.html`) renders a `field-grid`
built by `app.py::_ordered_fields(bead)`. Each row is a dict:
`{key, val, kind, short_meta}`.

- `_FIELD_ORDER` defines deterministic display order; unknown keys append
  alphabetically (so new bd fields never silently vanish).
- `_classify_field` picks a render **kind**: `empty | chips | deps | comments |
  markdown | para | json | scalar`.
- `_is_short_meta_field` flags the compact half-width metadata fields.

This per-field `kind` is the **natural hook for editability**: the editor type
maps cleanly off the same classification. The template stays "stupid" — it just
dispatches on kind — and an `editable` flag + `editor` hint can ride alongside
in the same row dict with zero logic creep across files (the established pattern).

---

## 3. The editability matrix (verified against `bd update --help`)

`bd update [id...]` is the only value-editing CLI surface. Mapping the JSON
field keys bd emits (`bd show … --json`) to whether/how `bd update` can edit
that value **in place**:

| Field (JSON key) | `bd update` flag | Editable in scope? | Editor kind | Notes |
|---|---|---|---|---|
| `title` | `--title` | ✅ yes | text | Plain scalar. Safest first target. |
| `description` | `-d` / `--body-file -` | ✅ yes | markdown textarea | Long markdown; prefer stdin/body-file to dodge shell-arg limits & quoting. |
| `acceptance_criteria` | `--acceptance` | ✅ yes | markdown textarea | Not present on this bead but valid field. |
| `design` | `--design` / `--design-file -` | ✅ yes | markdown textarea | Same stdin caution as description. |
| `notes` | `--notes` (replace) / `--append-notes` | ✅ yes (careful) | markdown textarea | `--notes` **replaces**; agents rely on append. UI must default to append or clearly warn on replace. |
| `priority` | `-p` / `--priority` | ✅ yes | select (P0–P4) | Constrained enum → dropdown, not free text. |
| `assignee` | `-a` / `--assignee` | ✅ yes | text | Free string. |
| `issue_type` | `-t` / `--type` | ✅ yes | select | Enum bug/feature/task/epic/chore/decision (+custom-config). |
| `labels` | `--add/remove/set-labels` | ⚠️ borderline | chips editor | Editing the *values* of the set arguably edits shape. **Recommend DEFER** to stay strictly in scope (see §5). |
| `parent` | `--parent` | ⚠️ borderline | text | Reparenting is a graph edit, not a flat value edit. **Recommend DEFER.** |
| `external_ref` | `--external-ref` | ✅ yes | text | Simple scalar. |
| `estimate` | `-e` / `--estimate` | ✅ yes | number (minutes) | Int minutes. |
| `metadata` | `--metadata` / `--set/unset-metadata` | ⚠️ borderline | json/kv editor | Editing existing values ✅; add/remove keys = shape. **DEFER** the kv-shape parts. |
| `status` | `-s` / `--status` (+`--claim`) | 🚫 out of scope | — | Status transitions are lifecycle, not "field value." bdboard already handles claim/close semantics conceptually; mixing into a generic editor invites bad transitions (e.g. closing without `--session`/`close_reason`). Keep lifecycle a **separate, explicit** affordance. |
| `story_points` | *(none)* | 🚫 not supported | — | **No `bd update` flag exists.** Cannot be edited via the CLI surface. |
| `created_at`, `started_at`, `updated_at`, `closed_at` | *(none)* | 🚫 system-managed | — | Timestamps; no edit flags. `updated_at` changes as a side effect of any edit. |
| `created_by` | *(none)* | 🚫 immutable | — | No flag. |
| `close_reason` | *(only via `bd close`)* | 🚫 lifecycle | — | Set at close time, not via update. |
| `id` | *(none)* | 🚫 immutable identity | — | Never editable. |
| `dependency_count`, `dependent_count`, `comment_count` | *(derived)* | 🚫 computed | — | Read-only aggregates. |
| `comments` | *(via `bd comment`)* | 🚫 different surface | — | Append-only conversation; out of a value-editor's scope. |
| `dependencies` / `dependents` / `deps` | `bd dep …` | 🚫 graph surface | — | Edges, not values. Separate epic if ever wanted. |

**Key empirical findings:**

1. **`story_points` has no update flag.** Any "edit every scalar" assumption is
   wrong on day one. The editor MUST be an explicit per-field whitelist, never
   "edit anything that looks scalar."
2. **`--notes` replaces, `--append-notes` appends.** Agents depend on
   append-only notes (the whole bug-discovery/verification protocol writes via
   `--append-notes`). A naive "edit notes" textarea that calls `--notes` would
   **silently destroy agent verification history**. This is the single sharpest
   foot-gun in the whole feature.
3. **`status` and `parent` look like fields but are lifecycle/graph edits.**
   Treating them as plain values invites invalid transitions and confusing UX.

---

## 4. Risks & sharp edges (call them out before any code)

- **Notes destruction (HIGH):** see §3.2. Mitigation: the editor for `notes`
  must default to *append* semantics, or render the replace path behind an
  explicit, scary confirm ("This replaces ALL notes, including agent
  verification history"). Strongly prefer never exposing raw `--notes` replace.
- **Multi-writer races (MED):** multiple browser tabs / a human + an agent can
  edit the same bead. The single `_subprocess_gate` serializes the *writes*,
  but a stale form can clobber a concurrent change (last-write-wins). Mitigation
  for v1: optimistic + SSE-driven refresh (acceptable for a local single-user
  tool); note a future `updated_at` precondition check as a follow-up.
- **Shell quoting / arg-length (MED):** long markdown via positional args is
  fragile. Mitigation: use `--body-file -` / `--design-file -` and feed content
  on stdin (bd supports `--stdin`). Avoid string-building shell commands.
- **Enum drift (LOW):** priority/type enums are constrained; build the dropdown
  options server-side from a single source so they can't desync from bd.
- **Scope creep into shape edits (PROCESS):** labels/metadata/parent are
  tempting but cross the "don't change field shape" line. Keep them OUT of the
  first deliverable; the epic explicitly wants a forward-thinking architecture,
  not a kitchen sink.
- **Auditability:** every edit should pass `--actor` (or rely on
  `$BEADS_ACTOR`/git user) so the existing audit-trail panel attributes the
  human edit correctly rather than to the agent identity.

---

## 5. Recommendation

**Ship a narrow, whitelist-driven, single-field inline editor — and build the
architecture so widening it later is additive, not a rewrite.**

### Recommended v1 field set (strictly "edit existing value", low-risk)
`title`, `description`, `acceptance_criteria`, `design`, `priority`,
`assignee`, `issue_type`, `external_ref`, `estimate`.
Plus `notes` **append-only** (the safe half of notes), rendered as "Add a note"
rather than "edit notes."

### Explicitly DEFERRED (out of scope or higher-risk, file as follow-ups)
- `labels`, `metadata` (kv), `parent` — these edit *shape/graph*, not a flat
  value. Out of the epic's stated scope.
- `status` lifecycle transitions — keep as a separate, explicit affordance with
  transition guards (don't fold into the generic value editor).
- `notes` *replace* — only behind a hard confirm, if ever.
- Concurrency precondition (`updated_at` optimistic-lock) — v2 hardening.

### Recommended architecture (forward-thinking, matches existing patterns)

1. **A field registry** (one Python dict/dataclass list) is the single source
   of truth: `key → {editable: bool, flag: str, editor: "text|textarea|md|
   select|number", enum_options?, append_only?}`. `_ordered_fields` consults it
   to add `editable` + `editor` hints to each row. **Adding a field later = one
   registry entry**, mirroring how `_KIND_*` sets already work. This is the DRY,
   SOLID (open/closed) shape the epic asks for.
2. **`BdClient.update_field(bead_id, flag, value)`** — a thin sibling of the
   existing `_run_mutate`, serialized on the same `_subprocess_gate`, using
   `--body-file -`/stdin for long text, passing `--actor`. Clears `_show_cache`
   + invalidates caches like `remember` does.
3. **One POST route** `POST /api/bead/{id}/field` (CSRF-checked via the existing
   `_check_csrf`) that validates the field against the registry (reject anything
   not `editable`), invokes `update_field`, broadcasts `beads_changed`, and
   returns the re-rendered field row (HTMX swap) — exactly the optimistic
   re-render the memory mutations already do.
4. **HTMX inline edit UI** in `bead_modal.html`: an "edit" affordance per
   editable field that swaps the `<dd>` for the matching input, posts, and
   swaps back the rendered value. WCAG 2.2 AA: real `<label>`s, keyboard
   operable, focus management, `aria-live` for save/error feedback.

This reuses 100% of the existing write/CSRF/SSE/cache plumbing; the genuinely
new surface is the **registry** (the extensibility seam) + per-field UI.

---

## 6. Follow-up beads (proposed; link via discovered-from to bdboard-7q9)

1. **Build the field registry + `_ordered_fields` editability hints** (the
   extensibility seam). No UI yet. (task, P2) — *foundational; others depend on it.*
2. **Add `BdClient.update_field` + `POST /api/bead/{id}/field` route** with
   CSRF, registry validation, stdin for long text, `--actor`, SSE broadcast,
   cache invalidation. (task, P2, depends on #1)
3. **HTMX inline-edit UI in the bead modal** for the v1 field set, WCAG 2.2 AA.
   (task, P2, depends on #1, #2)
4. **Notes: append-only "Add a note" affordance** (NOT replace). (task, P2,
   depends on #2)
5. **Concurrency hardening: `updated_at` optimistic-lock precondition** to
   prevent silent clobber. (task, P3) — v2.
6. **Decide & design status-transition affordance** (separate from value edit;
   guard invalid transitions, handle close `--session`/`close_reason`). (spike
   or design, P3)
7. **(Optional/deferred) shape edits** — labels chips editor, metadata kv
   editor, reparenting — only if the epic's scope is later widened. (epic/spike, P3)

> A `bd remember` is also warranted: **"`bd update --notes` REPLACES notes;
> agent verification history lives in notes — UI must use `--append-notes`."**
> Filing that memory should accompany follow-up #4.
