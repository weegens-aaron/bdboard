# Memory delete

Part of the **Memory** page. See also [memory-list.md](./memory-list.md)
(list & search) and [memory-create.md](./memory-create.md) (create/edit).

## What it shows

Every memory card on the Memory page carries a **🗑️ Forget** button in its
action row (next to the ✏️ Edit button). The button is labelled
`Forget <key>` for screen readers (`aria-label`) and has a `Forget` tooltip.

Clicking it does **not** delete immediately. It opens a dedicated
confirm-before-forget modal (`#memory-forget-dialog`) titled **"Forget
Memory?"** that:

- names the exact key being deleted (rendered into `<code id="forget-key-display">`),
- warns — prominently and in danger styling — that memories are injected at
  `bd prime`, so forgetting one silently degrades every future agent session
  that relied on it, and that the action cannot be undone,
- offers **Cancel** and a destructive **"Yes, Forget It"** button.

Only the "Yes, Forget It" button actually fires the delete. The friction is
deliberate: a stray forget is invisible until some later agent session is
quietly missing context, so the UI makes you confirm.

## Where the data comes from

The forget action is served by the `DELETE /api/memory/{key:path}` route:

- **Route:** `api_memory_delete` in `src/bdboard/app.py` (~line 670).
- **Derive/mutation layer:** `BdClient.forget(key)` in `src/bdboard/bd.py`
  (~line 480), which shells out to `bd forget <key>` via the shared
  `_run_mutate` helper (10s `FORGET_TIMEOUT_S`) and then clears the in-process
  `_memories_cache`.
- **Source of truth:** the bd workspace's local Dolt store. `bd forget`
  removes the memory there; bdboard holds no separate copy beyond the
  short-lived `_memories_cache`.

The `{key:path}` converter means keys containing slashes survive the round
trip. The client builds the URL with `encodeURIComponent(key)` in
`confirmForget()` (`src/bdboard/templates/memory.html`).

On success the route does **not** return a status code or JSON — it
re-renders `partials/memory_list.html` with the freshly re-fetched
`await bd.memories()` (query reset to `""`) and returns it as HTML. HTMX swaps
that fragment into `#memory-list`, so the deleted card disappears immediately
(optimistic refresh) without waiting for the SSE round trip.

## What changes its state

- **User confirms a forget** → the dialog's "Yes, Forget It" button fires its
  `hx-delete` (URL set dynamically by `confirmForget()`), with the CSRF token
  carried via `hx-headers='{"X-CSRF-Token": "..."}'`. The button also closes
  the dialog on click. The returned partial replaces `#memory-list`.
- **Server broadcasts SSE** → after a successful `bd forget`, the route calls
    `bus.broadcast("beads_changed")` so other open tabs/clients refresh their
  memory list too (the acting tab already got its swap from the response).
- **Cache invalidation** → `BdClient.forget` clears `_memories_cache` so the
  next `memories()` read reflects the deletion even before the watcher fires.

The delete path never re-runs in the background; the only refresh triggers are
the direct HTMX swap and the SSE-driven re-render in other tabs.

## Edge cases & notes

- **CSRF required.** The route calls `_check_csrf(x_csrf_token, None)`. Unlike
  create (which also accepts a `csrf_token` form field), delete validates the
  **header only** — there is no form-field fallback. A missing/incorrect token
  raises `HTTPException(403)` ("Invalid or missing CSRF token. Please refresh
  the page and try again."). HTMX supplies it via `hx-headers` on the confirm
  button. (Covered by `test_delete_memory_requires_csrf_token`.)
- **Confirmation is mandatory in the UI.** There is no one-click delete path
  from the card; the 🗑️ button only opens the dialog. The route itself,
  however, has no idea a dialog exists — anything with a valid CSRF token can
  call it directly, so confirmation is a UX guard, not a server guard.
- **Empty key.** A whitespace-only / empty `key` returns HTTP 400 with
  `Key cannot be empty.` before any bd call.
- **Removing a nonexistent key.** bd treats key-not-found as a failure:
  `bd forget` raises `RuntimeError`, which the route catches and returns as
  HTTP **500** with `Could not delete: <err>`. There is no graceful 404 or
  no-op — deleting something that isn't there surfaces as a server error in
  the swapped-in `memory-error` alert. (Covered by
  `test_delete_memory_shows_error_on_bd_failure`.) This is a known quirk worth
  smoothing if it ever bites users.
- **Errors render inline.** Both 400 and 500 responses return a small
  `<p class="memory-error" role="alert">...</p>` fragment that HTMX swaps into
  `#memory-list`, so the error replaces the list region (the list is gone until
  the next refresh) rather than appearing as a toast.
- **SSE fires only on success.** A failed forget returns before
  `bus.broadcast`, so other tabs are not nudged to refresh on error.
- **Path-encoded keys.** Because the route uses `{key:path}`, slashes in keys
  work; the client encodes the key before building the `hx-delete` URL.

## Source files

- `src/bdboard/app.py` — `api_memory_delete` (route, ~670), `_check_csrf`
  (~604), `_CSRF_TOKEN` global (~112).
- `src/bdboard/bd.py` — `BdClient.forget` (~480), `FORGET_TIMEOUT_S` (~42),
  `_run_mutate` (~704).
- `src/bdboard/templates/partials/memory_list.html` — the 🗑️ Forget button per
  card (`confirmForget(...)`) and the re-rendered swap target.
- `src/bdboard/templates/memory.html` — the `#memory-forget-dialog` confirm
  modal and the `confirmForget()` JS that wires up `hx-delete` + CSRF header.
- `tests/test_memory_mutations.py` — delete coverage (CSRF, success+forget,
  SSE broadcast, bd-failure → 500).
