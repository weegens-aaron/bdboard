# Memory create / edit

Part of the **Memory** page. See also [memory-list.md](./memory-list.md)
(list & search) and [memory-delete.md](./memory-delete.md) (forget).

## What it shows

The Memory page exposes two affordances that both open the **same** native
`<dialog id="memory-form-dialog">` modal:

- A **"+ New Memory"** button in the toolbar (`role` toolbar, next to the
  search strip). It has `aria-haspopup="dialog"` and calls
  `showModal()` to open the form blank.
- An **Edit** button (pencil icon) on every memory card (`memory_list.html`). It calls
  `editMemory(key, body)`, which pre-fills the dialog with the card's current
  key + body, **locks the key** (`readonly`, because `bd remember` can't rename
  a key), flips the title to **"Edit Memory"**, and focuses the body field.

The dialog itself is a single create-or-edit form with:

- a **Key** text input (`#memory-key-input`, `required`) plus a hint —
  *"A short identifier (e.g., `dev-workflow`). If it exists, the body is
  updated."* — making the upsert semantics visible up front,
- a **Body** textarea (`#memory-body-input`, `required`, `rows=6`,
  markdown-supported),
- **Cancel** (closes the dialog) and a primary **Save Memory** submit button.

Being a native `<dialog>` shown via `showModal()`, it traps keyboard focus
automatically and dismisses on `Esc`. On close, a `close` listener resets the
form back to the blank "New Memory" state (title reset, key cleared and
`readonly` removed, body cleared) so the next open starts fresh — there is no
separate "edit dialog"; the one modal is reused for both flows.

## Where the data comes from

The form is served by the `POST /api/memory` route:

- **Route:** `api_memory_create` in `src/bdboard/app.py` (~line 621). It takes
  `key` and `body` as required `Form(...)` fields, a `csrf_token` form field
  (aliased `csrf`), and an `X-CSRF-Token` header.
- **Derive/mutation layer:** `BdClient.remember(key, body)` in
  `src/bdboard/bd.py` (~line 459), which shells out to
  `bd remember "<body>" --key <key>` via the shared `_run_mutate` helper
  (~line 704, `REMEMBER_TIMEOUT_S = 10.0`s — writes are slower because of the
  dolt commit). Note the body is passed as a **positional** argument and the
  key via the `--key` flag. After the subprocess returns, `remember` clears the
  in-process `_memories_cache` so the next read reflects the write.
- **Source of truth:** the bd workspace's local Dolt store. `bd remember` is
  bdboard's **first write path** to bd; bdboard keeps no separate copy beyond
  the short-lived `_memories_cache`.

On success the route does **not** return a status code or JSON — it re-renders
`partials/memory_list.html` with the freshly re-fetched `await bd.memories()`
(query reset to `""`) and returns it as HTML. HTMX swaps that fragment into
`#memory-list`, so the new/updated card appears immediately (optimistic
refresh) without waiting for the SSE round trip.

## What changes its state

- **User submits the form** → the form's `hx-post="/api/memory"` fires with
  `hx-target="#memory-list"` and `hx-swap="innerHTML"`. The CSRF token is sent
  **two ways**: via `hx-headers='{"X-CSRF-Token": "..."}'` *and* a hidden
  `csrf_token` form field. The `onsubmit` handler schedules
  `dialog.close()` ~50ms later so the modal dismisses after the request is
  dispatched. The returned partial replaces `#memory-list`.
- **Server broadcasts SSE** → after a successful `bd remember`, the route calls
  `bus.broadcast("beads_changed")` so **other** open tabs/clients refresh their
  memory list too (the acting tab already got its swap from the response).
- **Cache invalidation** → `BdClient.remember` clears `_memories_cache` so the
  next `memories()` read reflects the new state even before the watcher fires.

The create path never re-runs in the background; the only refresh triggers are
the direct HTMX swap and the SSE-driven re-render in other tabs.

## Edge cases & notes

- **Upsert / update-in-place semantics.** There is no separate "update" route.
  `bd remember` is an upsert: a known key has its body **replaced**, an unknown
  key creates a new memory. So "Edit" and "Create" are the same server
  operation — the only difference is the client pre-fills and locks the key.
  This also means a "key collision" is not an error: creating with an existing
  key silently overwrites that memory's body. The dialog hint warns about this
  ("If it exists, the body is updated.").
- **Key is immutable once set.** Because `bd remember` keys by `--key`, you
  can't rename a key through this form. Editing locks the key field
  (`readonly`); to "rename" you'd create a new key and forget the old one.
- **CSRF required (header *or* form field).** The route calls
  `_check_csrf(x_csrf_token, csrf)` (~line 604). Unlike delete (header-only),
  create accepts **either** the `X-CSRF-Token` header **or** the `csrf_token`
  form field — the form supplies both, so non-JS form posts still validate via
  the hidden field. A missing/incorrect token on both raises
  `HTTPException(403)` ("Invalid or missing CSRF token. Please refresh the page
  and try again."). The token is a per-process `secrets.token_urlsafe(32)`
  (`_CSRF_TOKEN`, ~line 112) injected into every template as the `csrf_token`
  Jinja global (~line 113). (Covered by `test_create_memory_requires_csrf_token`,
  `test_create_memory_accepts_valid_csrf_header`,
  `test_create_memory_accepts_valid_csrf_form_field`.)
- **Validation: empty key / empty body.** Both `key` and `body` are
  `.strip()`-ed server-side. An empty/whitespace key returns HTTP **400** with
  an inline `<p class="memory-error" role="alert">Key cannot be empty.</p>`; an
  empty/whitespace body returns 400 with `Body cannot be empty.`. The browser
  also enforces `required` on both inputs, but the server validates
  independently. (Covered by `test_create_memory_rejects_empty_key` and
  `test_create_memory_rejects_empty_body`.)
- **bd failure → 500.** If `bd remember` raises `RuntimeError`, the route logs
  a warning and returns HTTP **500** with an inline
  `<p class="memory-error" role="alert">Could not save: <err></p>` fragment.
  (Covered by `test_create_memory_shows_error_on_bd_failure`.)
- **Errors render inline, replacing the list.** Both the 400 and 500 responses
  return a small `memory-error` fragment that HTMX swaps into `#memory-list`,
  so on error the error message replaces the list region (the list is gone
  until the next refresh) rather than appearing as a toast.
- **SSE fires only on success.** A failed create returns before
  `bus.broadcast`, so other tabs are not nudged to refresh on error.
- **Optimistic + reset-to-full-list.** The success response re-renders with
  `query=""`, so submitting while a search filter is active resets the list
  back to the unfiltered view.

## Source files

- `src/bdboard/app.py` — `api_memory_create` (route, ~621), `_check_csrf`
  (~604), `_CSRF_TOKEN` global + `csrf_token` Jinja global (~112-113).
- `src/bdboard/bd.py` — `BdClient.remember` (~459), `REMEMBER_TIMEOUT_S` (~41),
  `_run_mutate` (~704).
- `src/bdboard/templates/memory.html` — the `+ New Memory` button, the
  `#memory-form-dialog` create/edit modal (form `hx-post`, CSRF header + hidden
  field), and the `editMemory()` / form-reset JS.
- `src/bdboard/templates/partials/memory_list.html` — the per-card Edit
  button (pencil icon) (`editMemory(...)`) and the re-rendered swap target.
- `tests/test_memory_mutations.py` — create coverage (CSRF header/form,
  empty-key, empty-body, SSE broadcast, bd-failure → 500).
