# 0006 — Manual field-editing model (registry, whitelist, append-only notes)

- **Status:** accepted
- **Date:** 2026-06-01
- **Relates to:** bdboard-7q9 (spike,
  `notes/design/bdboard-7q9/manual-field-editing-spike.md`), parent epic
  bdboard-o9v, memory `notes-append-not-replace`. Backfills audit item **M4**.

> Manual editing of bead field *values* is driven by an explicit per-field
> **whitelist registry**, reuses bdboard's existing mutate/CSRF/SSE/cache
> plumbing, edits **only the values of fields that already exist** (never field
> shape), and treats `notes` as **append-only**.

## Context

The bdboard-o9v epic wants humans to edit bead field values from the dashboard.
Spike bdboard-7q9 verified the editing surface empirically against the installed
`bd` (`bd update --help`, live `bd show … --json`) and the current source, and
found sharp edges that forbid a naive "edit anything scalar" approach:

- **`bd update --notes` REPLACES all notes**, while `--append-notes` appends.
  The entire bug-discovery/verification protocol writes via `--append-notes`; a
  naive "edit notes" textarea would **silently destroy agent verification
  history** — the single sharpest foot-gun.
- **`story_points` has no `bd update` flag at all** — so "edit every scalar" is
  wrong on day one.
- **`status` and `parent` look like fields but are lifecycle/graph edits** —
  treating them as plain values invites invalid transitions.
- bdboard already has every primitive an edit feature needs: a serialized
  mutate path (`_run_mutate` on `_subprocess_gate`), CSRF
  (`_CSRF_TOKEN`/`_check_csrf`), optimistic re-render, SSE `beads_changed`
  broadcast, and cache invalidation. The feature is wiring + UI + a careful
  whitelist, not new infrastructure.

## Decision

- **Scope guardrail:** edit the **values of fields that already exist** on a
  bead. Adding/removing/reshaping the *set* of fields is out of scope.
- **A field registry** (one Python data structure) is the single source of
  truth: `key → {editable, flag, editor (text|textarea|md|select|number),
  enum_options?, append_only?}`. `_ordered_fields` consults it to add
  `editable`/`editor` hints per row. Adding a field later = one registry entry
  (DRY, open/closed).
- **`notes` is append-only** in the UI ("Add a note", calling `--append-notes`);
  the raw `--notes` replace path is never exposed casually.
- **One CSRF-checked route** `POST /api/bead/{id}/field` validates the field
  against the registry (reject anything not `editable`), invokes a thin
  `BdClient.update_field` (serialized on the existing `_subprocess_gate`, long
  text via `--body-file -`/stdin, passing `--actor`), broadcasts
  `beads_changed`, and returns the re-rendered row for an HTMX swap.
- **v1 whitelist:** `title`, `description`, `acceptance_criteria`, `design`,
  `priority`, `assignee`, `issue_type`, `external_ref`, `estimate`, plus
  append-only `notes`. **Deferred:** `labels`/`metadata`/`parent` (shape/graph
  edits), `status` lifecycle (separate guarded affordance), notes-replace, and
  `updated_at` optimistic-lock concurrency hardening.
- UI is WCAG 2.2 AA: real `<label>`s, keyboard-operable, focus management,
  `aria-live` for save/error feedback.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Whitelist registry + reuse existing plumbing, append-only notes** | Safe by construction; one place to widen scope; reuses 100% of write/CSRF/SSE/cache code; protects notes history | Slightly more upfront structure than a generic editor | **CHOSEN** |
| B. Generic "edit any scalar field" editor | Less code | Breaks on `story_points` (no flag); would expose `--notes` replace and destroy history; invites invalid `status`/`parent` edits | Rejected |
| C. Edit `.beads/issues.jsonl` / Dolt directly | No CLI round-trip | Violates ADR 0004 (CLI is source of truth); bypasses bd validation/locking | Rejected |

## Consequences

- Editing is additive to widen (one registry row), never a rewrite — the
  extensibility seam the epic asked for.
- Agent verification history in `notes` is structurally protected (append-only).
- Multi-writer races are last-write-wins for v1 (acceptable for a local
  single-user tool); an `updated_at` precondition is a documented v2 follow-up.
- `status` transitions and shape/graph edits stay deliberately out of the
  generic value editor; they get their own guarded affordances if ever built.
- Long-text edits go over stdin (`--body-file -`) to dodge shell arg-length and
  quoting hazards.
