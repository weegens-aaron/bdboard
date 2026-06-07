# Design: status-transition affordance (separate from value edit)

- **Bead:** bdboard-o9v.6 (spike / design)
- **Parent epic:** bdboard-o9v — Enable manual editing of bead field values
- **Discovered from:** bdboard-7q9 (manual-field-editing spike), §3 & §5
- **Status:** design / recommendation only — **no shipped status-edit code**
- **Date:** 2026-05-29

> Deliverable for bdboard-o9v.6. This doc designs a **separate, explicit**
> status-transition affordance with transition guards. It deliberately ships
> **no code** — like the bdboard-7q9 spike, it produces a recommendation +
> follow-up beads. Verified empirically against the installed `bd`
> (`bd help update`, `bd help close`, `bd list --status=…`) and the current
> bdboard source (`app.py`, `bd.py`, `partials/field_row.html`), not docs alone.

---

## 1. Why status is NOT a field value (the whole reason this bead exists)

The bdboard-7q9 editability matrix (§3) classed `status` as **🚫 out of scope**
for the generic value editor, with this rationale:

> Status transitions are lifecycle, not "field value." Mixing into a generic
> editor invites bad transitions (e.g. closing without `--session`/
> `close_reason`). Keep lifecycle a **separate, explicit** affordance.

Three concrete reasons status cannot ride the `update_field` path:

1. **It is a state machine, not a scalar.** A `priority` can flip P0→P4 freely;
   a status cannot legally jump anywhere → anywhere. `open → closed` directly is
   suspicious (no work tracked); `closed → in_progress` is a *reopen*, a
   semantically distinct act. A free `<select>` of all 7 values invites invalid
   or meaningless transitions.

2. **Some transitions require side data the value editor has no slot for.**
   `bd update -s closed` wants a `--session` (Claude Code session id) and a
   close reason; `bd close` takes `-r/--reason` / `--reason-file -`. The generic
   `POST /api/bead/{id}/field` route (app.py ~L665) carries exactly one `value`
   form field — it structurally cannot supply a close reason. Folding status in
   would either drop the reason silently or bolt a special-case onto the generic
   route, breaking its single responsibility.

3. **Close is judge-territory in this very workspace.** This repo runs a
   bead-chain LLM-judge pipeline that is the *only* legitimate closer (`bd close`
   is actively blocked for agents — verified: it refused mid-spike). A human
   clicking "close" in bdboard is a different actor with different rules than an
   agent. The affordance must encode that distinction, not pretend close is a
   value assignment. (This is workspace policy, not a bd-universal rule, but the
   affordance should be configurable enough to honour it — see §6 "close
   policy".)

**Conclusion:** status gets its own affordance, its own route, its own guard
table. It stays OUT of `_FIELD_REGISTRY`'s `editable` set (it already is — and
must remain so; the registry is the whitelist and read-only is the default).

---

## 2. The status state machine (verified valid values)

`bd` rejects unknown statuses with an explicit allow-list (verified:
`bd list --status=foo` → *"valid: open, in_progress, blocked, deferred, closed,
pinned, hooked"*). The seven statuses, grouped by role:

| Status | Role | Notes |
|---|---|---|
| `open` | backlog / ready | The "not started" resting state. |
| `in_progress` | active work | Set atomically by `--claim` (also sets assignee). |
| `blocked` | waiting on a dependency | Soft state; bd also derives blocked-ness from dep edges. |
| `deferred` | intentionally parked | Distinct from blocked: a *choice*, not a dependency wait. |
| `closed` | terminal / done | Requires `--session` via update; `bd close` is the richer surface (reason). |
| `pinned` | infra / never-auto-close | Special: pinned issues resist auto-close (`bd close --force` needed). |
| `hooked` | molecule/formula machinery | bd-internal lifecycle; **not** a human-facing manual target. |

### 2.1 Proposed allowed manual transitions

Not every value is a sensible *manual* target. bdboard is a human-facing
dashboard; `pinned` and `hooked` are bd-machinery states a human should not be
nudged toward via a casual dropdown. The affordance offers a **curated subset**
of transitions, guarded server-side:

```
            ┌─────────────────────────────────────────────┐
            ▼                                             │ (reopen)
  ┌──────┐ claim  ┌─────────────┐  done   ┌────────┐      │
  │ open │ ─────▶ │ in_progress │ ──────▶ │ closed │ ─────┘
  └──────┘        └─────────────┘         └────────┘
     ▲ ▲             │      ▲                  ▲
     │ │      block/ │      │ unblock/         │ (close from any
     │ │      defer  ▼      │ resume           │  active/parked state,
     │ │        ┌─────────┐ │                  │  with reason)
     │ └────────│ blocked │─┘                  │
     │          └─────────┘────────────────────┤
     │          ┌──────────┐                    │
     └──────────│ deferred │────────────────────┘
                └──────────┘
```

**Allowed-transition table** (source `→` target). `✔` = offered & permitted,
blank = not offered:

| from \ to    | open | in_progress | blocked | deferred | closed |
|--------------|:----:|:-----------:|:-------:|:--------:|:------:|
| open         |  —   |     ✔(claim)|   ✔     |    ✔     |   ✔*   |
| in_progress  |  ✔   |      —      |   ✔     |    ✔     |   ✔    |
| blocked      |  ✔   |     ✔       |   —     |    ✔     |   ✔    |
| deferred     |  ✔   |     ✔       |   ✔     |    —     |   ✔    |
| closed       |  ✔(reopen) | ✔(reopen) |   ✔   |   ✔     |   —    |

Notes:
- `pinned` / `hooked` are **never** manual targets and never *sources* the UI
  offers transitions from (if a bead is pinned/hooked, show status read-only
  with a tooltip explaining it's bd-managed).
- `✔*` open→closed direct is *permitted but soft-warned* ("Closing without ever
  starting — sure?"). It's legal in bd; we don't block it, we nudge.
- Every transition into `closed` routes through the close sub-flow (§4.2),
  which collects a reason and respects close policy.
- `closed → *` is a **reopen**; label it "Reopen" not "Set status", and confirm,
  because reopening a judged-closed bead in a bead-chain workspace is meaningful.

This table is the **guard**: the server validates `(current_status, target)`
against it and rejects anything not marked `✔`, exactly mirroring how
`_field_spec` rejects non-whitelisted fields. Invalid transitions can never be
written even from a crafted request.

---

## 3. What the generic value editor already does (the substrate to mirror, not reuse)

The manual-field-editing path (bdboard-o9v.1–.4, now landed) gives us a proven
template. The status affordance should **mirror its shape** but **not reuse its
route**:

- **`BdClient.update_field(bead_id, flag, value, actor)`** (bd.py ~L367):
  serialized on `_subprocess_gate`, streams long text via stdin, forwards
  `--actor`, clears `_show_cache` + `invalidate_caches()`. → We add a *sibling*
  `BdClient.transition_status(...)`, not an overload, because status needs extra
  args (`--claim`, `--session`, reason) the field signature can't carry cleanly.
- **`POST /api/bead/{id}/field`** (app.py ~L665): CSRF guard, registry
  validation, optimistic re-render of one field row, SSE `beads_changed`. → We
  add a *separate* `POST /api/bead/{id}/status` route that runs the
  transition-guard check instead of the registry-editable check.
- **`_FIELD_REGISTRY` / `FieldSpec`**: the whitelist seam. → Status gets its own
  parallel seam: a `_STATUS_TRANSITIONS` guard table (§2.1) + a small
  `StatusActionSpec` describing each offered action (label, target, needs_reason,
  confirm). Same DRY/open-closed shape: adding/altering an allowed transition is
  one table entry.
- **`partials/field_row.html`**: the status row is currently a plain read-only
  scalar. → Replace *only the status row's* render with a status-action control
  (a small partial, e.g. `partials/status_control.html`), leaving every other
  field row untouched.

**Why a separate route instead of widening `field`?** Single Responsibility.
`/field` answers "set this scalar to this string." `/status` answers "perform
this lifecycle transition, collecting any required side-data, subject to the
guard table and close policy." Cramming both into one handler means a pile of
`if field == "status"` special-cases — the exact anti-pattern the registry was
built to avoid.

---

## 4. Proposed affordance design

### 4.1 The control (non-close transitions)

In the bead modal's status row, render a small **action menu** (not a raw
`<select>` of all 7 values). It lists *only the transitions allowed from the
current status* (per §2.1), labelled as **verbs**, e.g.:

- from `open`: **Claim (start work)** · Mark blocked · Defer · Close…
- from `in_progress`: Mark blocked · Defer · Move to open · Close…
- from `blocked`: Resume (in progress) · Move to open · Defer · Close…
- from `closed`: **Reopen…** (to in_progress / open)

Verb labels make the lifecycle legible and prevent the "it's just a value"
mental model that causes invalid transitions. Each non-close, non-reopen verb
is a one-click HTMX POST → `/api/bead/{id}/status` with `target=<status>`.
`open→in_progress` uses `--claim` (atomic assignee+status) rather than
`-s in_progress`, matching bd's intended idiom.

### 4.2 The close sub-flow (needs a reason + session + policy)

"Close…" and "Reopen…" open a **small inline form / popover** (not a one-click)
because they need side-data and confirmation:

- **Close form fields:** a required-ish **reason** textarea (maps to
  `bd close -r` / `--reason-file -` for long text, mirroring the stdin pattern
  in `update_field`), and the session id sourced server-side from
  `$CLAUDE_SESSION_ID` (never typed by the user). Submit → `/api/bead/{id}/status`
  with `target=closed`.
- **Close policy guard (workspace-aware):** this workspace's bead-chain blocks
  agent `bd close`. The affordance must NOT silently bypass that. Design:
  a `CLOSE_POLICY` setting (`allow` | `confirm` | `deny`), default `confirm`:
  - `confirm` → human gets a "This closes the bead outside the judge pipeline.
    Continue?" confirmation; on yes, run `bd close` with `--actor=<human>` so the
    audit trail shows a human, not an agent.
  - `deny` → render close disabled with a tooltip ("Closing is handled by the
    LLM-judge pipeline in this workspace"). This is the safe default for
    judge-driven repos; surfaced as config so non-bead-chain users get `allow`.
  - The route enforces the policy server-side regardless of UI state.
- **Reopen** = `closed → open|in_progress`; confirm ("Reopening a closed bead"),
  then `bd update -s <target>`.

### 4.3 `BdClient.transition_status` (sketch — NOT shipped here)

```python
async def transition_status(
    self,
    bead_id: str,
    target: str,
    *,
    reason: str | None = None,
    actor: str | None = None,
    session: str | None = None,
) -> None:
    """Perform a guarded lifecycle transition. Sibling of update_field.

    Caller (the route) has ALREADY validated (current, target) against the
    transition guard table. This method just maps target → the right bd verb:
      - target == 'in_progress' from open  -> `bd update <id> --claim`
      - target == 'closed'                 -> `bd close <id> -r <reason> [--session ...]`
                                              (reason via --reason-file - for long text)
      - everything else                    -> `bd update <id> -s <target>`
    Serialized on _subprocess_gate; clears _show_cache + invalidate_caches()
    exactly like update_field. --actor forwarded so the audit trail attributes
    the human.
    """
```

### 4.4 The route (sketch — NOT shipped here)

```
POST /api/bead/{id}/status   (CSRF-checked via existing _check_csrf)
  form: target, reason?, csrf_token
  1. read current status (store snapshot / show_long)
  2. reject if current is pinned/hooked (bd-managed)
  3. reject if (current, target) not in _STATUS_TRANSITIONS guard  -> 400
  4. if target == closed: enforce CLOSE_POLICY; require/forward reason+session
  5. await bd.transition_status(...)
  6. broadcast('beads_changed'); optimistic re-render of the status control
     + (ideally) the whole modal header, since status drives lane/badge.
```

---

## 5. WCAG 2.2 AA notes (the control is interactive — it must be accessible)

- The action menu is keyboard operable (real `<button>`s, not div-clicks);
  focus moves into the close/reopen popover on open and returns to the trigger
  on close (focus management, SC 2.4.3).
- Close/reopen confirmations use `aria-live="polite"` for save/error feedback
  (consistent with the field-edit `role="alert"` errors already in app.py).
- Status conveyed by **text label + shape**, never colour alone (SC 1.4.1) —
  reuse the existing lane/badge text labels; don't introduce a colour-only
  status cue.
- The reason textarea has a real `<label>`; required-ness is announced, not just
  visually starred.
- Disabled "Close" (under `deny` policy) uses `aria-disabled` + an accessible
  explanation, not a bare greyed button with no reason.

---

## 6. Risks & sharp edges

- **Closing outside the judge pipeline (HIGH, workspace-specific):** see §4.2.
  Mitigation = `CLOSE_POLICY` defaulting to `confirm`/`deny`, server-enforced,
  with human `--actor` attribution. The UI must never make bypassing the judges
  a frictionless one-click.
- **Invalid transitions (MED):** mitigated by the §2.1 guard table enforced
  server-side; the UI only *offers* legal verbs, but the route is the real
  gate (defence in depth, mirroring the registry pattern).
- **pinned/hooked confusion (MED):** these look like statuses but are
  bd-machinery. Render read-only with explanation; never offer them as targets
  or transition from them.
- **Reason loss on close (MED):** the one-`value` generic route can't carry a
  reason — exactly why we use a separate route + form. Long reasons stream via
  `--reason-file -`/stdin like `update_field` does for description/design.
- **Lane/header staleness (LOW):** status drives the kanban lane + header badge,
  so the optimistic re-render should refresh more than a single field row;
  rely on the SSE `beads_changed` broadcast to reconcile the board, and
  re-render at least the modal header on the response.
- **Multi-writer races (LOW):** same single-`_subprocess_gate` serialization as
  field edits; a stale current-status read could let through a transition that's
  no longer valid. v2 hardening: re-check current status inside the gate, or
  fold into the bdboard-o9v.5 `updated_at` optimistic-lock work.
- **Session id availability (LOW):** `--session` for close comes from
  `$CLAUDE_SESSION_ID`; when absent (a plain human session), `bd close -r` still
  works without it — design must not hard-require a session that isn't there.

---

## 7. Recommendation (summary)

Ship status as a **separate, explicit, verb-labelled affordance**, NOT a value
in `_FIELD_REGISTRY`:

1. A **`_STATUS_TRANSITIONS` guard table** (§2.1) = the single source of truth
   for which transitions are legal, mirroring `_FIELD_REGISTRY`'s role. Curated
   subset: `open/in_progress/blocked/deferred/closed` only; `pinned`/`hooked`
   are bd-managed and read-only.
2. A **`BdClient.transition_status`** sibling of `update_field` that maps target
   → the correct bd verb (`--claim` / `bd close -r` / `-s <status>`),
   serialized, cache-invalidating, `--actor`-attributed.
3. A **separate `POST /api/bead/{id}/status`** route: CSRF, guard-table check,
   close-policy enforcement, optimistic re-render, SSE broadcast.
4. A **status control partial** replacing only the status row's render: a verb
   action-menu for simple transitions + an inline close/reopen form (reason +
   confirm). WCAG 2.2 AA throughout.
5. A **`CLOSE_POLICY` setting** (`allow|confirm|deny`, default `confirm`/`deny`
   for judge-driven repos) so bdboard never silently bypasses a workspace's
   close governance (this repo's bead-chain judges).

This reuses the *patterns* of the field-edit epic (serialized mutate, CSRF, SSE,
optimistic re-render, single-source-of-truth table as the extensibility seam)
while keeping status' lifecycle semantics in their own, guarded surface — the
exact separation §3/§5 of the bdboard-7q9 spike called for.

---

## 8. Follow-up beads (proposed; link via discovered-from to bdboard-o9v.6)

1. **Status guard table + `StatusActionSpec`** (`_STATUS_TRANSITIONS`), no UI —
   the extensibility seam. (task, P3) *foundational; others depend on it.*
2. **`BdClient.transition_status`** mapping target → bd verb (`--claim` /
   `bd close -r --reason-file -` / `-s`), serialized, cache-invalidating,
   `--actor`. (task, P3, depends on #1)
3. **`POST /api/bead/{id}/status` route** with CSRF, guard check, close-policy
   enforcement, SSE broadcast, optimistic re-render. (task, P3, depends on #1, #2)
4. **Status control partial + modal wiring** (verb action-menu + close/reopen
   inline form), WCAG 2.2 AA. (task, P3, depends on #1, #3)
5. **`CLOSE_POLICY` config** (`allow|confirm|deny`) wired through the route and
   UI, default safe for judge-driven workspaces. (task, P3, depends on #3)
6. **Concurrency hardening:** re-check current status inside `_subprocess_gate`
   (or fold into bdboard-o9v.5's `updated_at` optimistic-lock). (task, P3) v2.
