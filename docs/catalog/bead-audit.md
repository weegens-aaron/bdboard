# Bead audit/history view

Part of the **Board** page. See also [bead-modal.md](./bead-modal.md) (the
detail modal that hosts this view), [bead-inline-edit.md](./bead-inline-edit.md)
(field edits that the audit trail records), and
[store-cache.md](./store-cache.md) (the cache layer that the per-bead history
fetch participates in).

## What it shows

Inside the bead detail modal, below **Bead details**, sits a lazily-loaded
section that renders **two complementary views over the same change history**
of a single bead:

1. **Lifecycle timeline** — a compact ordered list (oldest → newest) of only
   the moments the bead's **status** changed (e.g. `open → in_progress →
   closed`). Each stop shows a status pill, when the bead entered that status,
   the **dwell time** spent in it before the next transition (the current/last
   status reads "current" instead of a duration), and who committed it. This
   block is swapped **out-of-band** to the top of the modal scroll region
   (into `#lifecycle-slot`, above "Bead details") for at-a-glance state
   context.
2. **Audit trail** — the full, field-by-field change log rendered in place. Each
   row shows the commit timestamp, the committer, a human-readable summary of
   *what* changed (e.g. `status: open → in_progress`, `set assignee`,
   `cleared design`, `created`), and the short 8-char commit hash.

While the history is being fetched the section shows a `loading history…`
placeholder; the timeline slot starts empty until the out-of-band swap fills
it.

## Where the data comes from

Both views are derived from a **single** `bd history <id>` payload — one
subprocess call feeds two render targets, so the lifecycle view costs no extra
work:

- **Route:** `GET /api/bead/{bead_id}/audit` → `api_bead_audit` in
  `src/bdboard/app.py` (~1184). It calls `bd.history(bead_id)`, shapes the
  result two ways, and returns the rendered `partials/bead_audit.html`.
- **Fetch layer:** `BdClient.history(bead_id)` in `src/bdboard/bd.py` (~412)
  shells `bd history <id> --json`, returning `(entries, error)`. bd returns one
  full issue snapshot per Dolt commit, **newest first**. The call is TTL-cached
  and in-flight-deduped via `BdClient._cached` (~342) under a per-bead key, and
  **failures are cached too** (with a shorter TTL) so a flaky bd isn't hammered.
- **Audit-trail shaping:** `_shape_audit(entries)` in `src/bdboard/app.py`
  (~1542) diffs each snapshot against the next-older one via `_diff_issue`
  (~1576) + `_short` (~1601), producing the human-readable change rows. The
  oldest snapshot is always emitted as a `created` origin row.
- **Lifecycle shaping:** `derive.status_timeline(entries)` in
  `src/bdboard/derive/history.py` (~442) is a **pure** function over the same
  payload (no I/O): it reverses to oldest-first, collapses consecutive
  identical statuses to keep only true transitions, then computes each stop's
  dwell time as the gap to the next transition.
- **Source of truth:** the bd workspace's local Dolt store, whose per-commit
  snapshots *are* the audit history. bdboard keeps no separate copy beyond the
  short-lived history cache.

The template `partials/bead_audit.html` consumes three context values —
`entries` (shaped audit rows), `timeline` (lifecycle stops), and `error` — and
chooses what to render from them.

## What changes its state

- **Modal open** → `partials/bead_modal.html` includes the audit `<section>`
  with `hx-get="/api/bead/{id}/audit"` and `hx-trigger="load"`. The modal
  itself loads via `/api/bead/{id}` first; this view fires **lazily** right
  after the modal paints, so opening a bead never blocks on the (potentially
  slow) history call.
- **Out-of-band timeline swap** → the audit response carries a
  `<div id="lifecycle-slot" hx-swap-oob="true">…</div>`, so HTMX swaps the
  lifecycle timeline into the top slot in the **same** response that fills the
  audit trail in place. One fetch, two render targets.
- **Re-open / fresh fetch** → there is no in-modal "refresh" button; closing and
  re-opening the modal re-fires the `load` trigger. Within the cache TTL the
  same `bd history` payload is served; after a watcher fire,
  `BdClient.invalidate_caches()` (~448, called by the Store) drops the history
  cache so the next open reflects post-mutation state.
- **Note:** this view is **read-only**. It records changes made elsewhere
  (inline field edits, status transitions) but never mutates the bead.

## Edge cases & notes

- **Empty history.** When `bd history` returns no entries (or the shaped audit
  is empty), the audit trail renders `no recorded history yet` and the lifecycle
  slot stays empty (the timeline `<section>` is gated on `{% if timeline %}`).
  `status_timeline([])` and `status_timeline(None)` both return `[]`, so the
  template needs no special-casing. (Covered by
  `tests/test_derive_history.py::test_status_timeline_empty_input`.)
- **Ordering.** bd returns snapshots **newest-first**. The audit trail keeps
  that descending order (newest change at the top). The lifecycle timeline is
  deliberately **reversed to oldest-first** so transitions read forward like a
  story. Don't confuse the two: same payload, opposite display order.
- **No-op Dolt commits skipped.** bd's auto-export re-serializes unchanged
  content, producing commits whose diff is empty. `_shape_audit` skips any
  non-origin snapshot whose `_diff_issue` is empty, so the audit panel isn't
  spammed with repeated no-op rows. The **oldest** snapshot is always shown as
  `created` regardless of diff, giving the trail a legitimate origin row.
- **Noise-suppressed diff fields.** `_diff_issue` skips `updated_at` (it always
  changes) and the internal `_HIDDEN` fields. High-signal keys
  (`status`, `priority`, `assignee`) get a full `old → new` summary; other
  fields collapse to `set <k>` / `cleared <k>` / `changed <k>`. Long values are
  truncated by `_short` to 40 chars (`…`); `None` renders as `∅`.
- **Dwell time.** Each timeline stop's `dwell_h` is the hours until the next
  transition. The **final** stop is the bead's current state — its dwell is
  open-ended and left `None` (rendered as "current"), not measured against
  "now". Unparseable/negative commit dates also yield `None` rather than a bogus
  duration. (Covered by `test_status_timeline_computes_dwell_hours`,
  `test_status_timeline_dwell_none_on_unparseable_date`.)
- **Blank statuses skipped.** Snapshots with an empty/whitespace status are
  ignored by `status_timeline` so they don't create phantom transitions.
  (Covered by `test_status_timeline_skips_blank_status`.)
- **Fetch failure is graceful, never blocking.** If `bd.history` returns an
  error, the route renders the partial with `entries=None`/`timeline=None`, and
  the template shows a friendly `⚠ Audit history is temporarily unavailable`
  message — **both** views are skipped, and the rest of the modal (details,
  inline edits) keeps working because the audit loads separately. (Covered by
  `tests/test_api_bead_audit.py::test_audit_error_skips_both_views`.)
- **Cached failures.** Because `_cached` stores errors too, a transient bd
  failure won't be retried on every modal open — it clears on the shorter
  error-TTL or on a cache invalidation.

## Source files

- `src/bdboard/app.py` — `api_bead_audit` (route, ~1184), `_shape_audit`
  (~1542), `_diff_issue` (~1576), `_short` (~1601).
- `src/bdboard/bd.py` — `BdClient.history` (~412), `_cached` (~342),
  `invalidate_caches` (~448).
- `src/bdboard/derive/history.py` — `status_timeline` (~442).
- `src/bdboard/templates/partials/bead_audit.html` — the dual-view template:
  error state, out-of-band lifecycle timeline, and the in-place audit trail.
- `src/bdboard/templates/partials/bead_modal.html` — the lazy
  `hx-get`/`hx-trigger="load"` audit section and the `#lifecycle-slot` OOB
  target.
- `tests/test_api_bead_audit.py` — route tests: one fetch drives both views,
  error path skips both.
- `tests/test_derive_history.py` — `status_timeline` unit tests: empty input,
  transition collapse + oldest-first ordering, dwell computation, blank-status
  skip, committer/short-hash carry-through.
