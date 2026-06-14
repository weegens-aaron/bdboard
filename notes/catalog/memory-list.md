# Memory list & search

Part of the **Memory** page. See also [memory-create.md](./memory-create.md)
(create/edit) and [memory-delete.md](./memory-delete.md) (forget).

## What it shows

The Memory page (`/memory`) is the read surface for bd's persistent memories —
the short, keyed insights that get injected into every agent session at
`bd prime`. It renders, top to bottom:

- A **search strip** (`role="search"`) with a single labelled
  `<input type="search">` ("Search memories…"). Typing filters the list; the
  native search-field clear (×) returns to the full list.
- A **"+ New Memory"** button that opens the create/edit dialog (documented in
  memory-create.md).
- A **result-count line** (`<p class="memory-count" role="status"
  aria-live="polite">`) that reads either `N memories` / `1 memory` for the
  full list, or `N matching "<query>"` when a search term is active.
- The **memory list** itself — one card per memory, each showing the **key** as
  a monospace heading (`<h3 class="memory-key">`) and the **body** rendered
  from markdown into a `.prose` block. Every card carries ✏️ Edit and 🗑️ Forget
  action buttons.

Before the first fetch resolves, the list region shows a **shimmer skeleton**
(four placeholder cards) so the page paints instantly without a layout jump.

## Where the data comes from

Two routes cooperate, both in `src/bdboard/app.py`:

- **The page shell — `GET /memory`** (`page_memory`, ~line 354). This route is
  deliberately cheap: it never touches a bd subprocess. It validates the
  workspace (`_validate_or_warn()`, rendering `error.html` with status 500 on a
  broken workspace, for parity with `/`) and otherwise renders `memory.html`.
  The list region inside that template carries `hx-get="/api/memory"` with
  `hx-trigger="load, refresh from:body"`, so the actual memories are fetched
  client-side after the page paints. The `partials/memory_skeleton.html`
  placeholder ships inline as the initial content.

- **The list fragment — `GET /api/memory?q=`** (`api_memory`, ~line 573). This
  is the HTMX swap target. It reads the optional `q` query param, strips it,
  and calls `await bd.memories(term)`:
  - An empty/whitespace `q` lists **all** memories.
  - A non-empty `q` is passed straight through to bd's own search.
  On success it renders `partials/memory_list.html` with `{memories, query}`.
  On a bd `RuntimeError` it logs a warning and returns a friendly inline
  `<p class="memory-empty muted" role="status" aria-live="polite">` ("Couldn't
  load memories right now…") with HTTP **200** — it degrades rather than
  500-ing the partial swap.

- **Derive/data layer — `BdClient.memories(query)`** in `src/bdboard/bd.py`
  (~line 249). Shells out to `bd memories [term] --json` (`MEMORIES_TIMEOUT_S
  = 8.0`, ~line 40) through the shared `_cached` helper (~line 342), which
  layers a TTL cache, an `asyncio.Semaphore(1)` subprocess gate, and in-flight
  dedup over `_run_json`. Crucially, **search is server-side**: bd does its own
  case-insensitive substring match across key *and* body, so neither the
  browser nor bdboard re-implements matching. The raw JSON is a flat
  `key -> body` object plus a `schema_version` sentinel; the wrapper strips the
  sentinel (a payload of *only* the sentinel is the empty / no-match shape →
  empty list) and returns `{"key", "body"}` dicts **sorted alphabetically by
  key** to match the CLI's human ordering.

- **Source of truth:** the bd workspace's local Dolt store. bdboard holds no
  separate copy beyond the short-lived `_memories_cache`.

## What changes its state

- **Page load** → the list region's `hx-trigger="load"` fires the first
  `GET /api/memory` (no query), replacing the skeleton with the full list.
- **Debounced search** → the search input carries
  `hx-trigger="keyup changed delay:250ms, search"`,
  `hx-get="/api/memory"`, `hx-target="#memory-list"`, `hx-swap="innerHTML"`,
  and `hx-sync="this:replace"`. Each settled keystroke (after the 250ms debounce
  and only when the value *changed*) posts `q` and swaps the list. The `search`
  event also fires the request, so the native clear (×) returns to the full
  list. `hx-sync="this:replace"` cancels an in-flight request when a newer
  keystroke arrives, so fast typers never get stale results racing in.
- **Create / edit a memory** → the create dialog posts to `POST /api/memory`
  and swaps `#memory-list` with the freshly re-rendered list (query reset).
  See memory-create.md.
- **Forget a memory** → the confirm dialog's `DELETE /api/memory/{key}` returns
  the re-rendered list (query reset) and swaps `#memory-list`. See
  memory-delete.md.
- **SSE live-refresh** → the list region also carries
  `hx-trigger="refresh from:body"`. When the `.beads/` watcher detects a change
  it broadcasts over SSE, which fires `refresh` on `body`, so a memory
  created/deleted in another tab (or via the `bd` CLI directly) appears live
  without polling. See sse-live-refresh.md. Note: the SSE refresh always
  re-fetches the **unfiltered** list (`hx-get="/api/memory"` with no `q`), so a
  live push from another tab will reset an active search to the full list.

## Edge cases & notes

- **Empty state (no memories at all).** With zero memories and no query, the
  partial renders `No memories yet — click + New Memory or run bd remember to
  add one.` (Covered by `test_no_memories_at_all_empty_state`.)
- **No-match state (query with no results).** With a query that matches
  nothing, it renders `No memories matching "<query>".` — distinct from the
  "none yet" copy so the user knows their filter, not the store, is empty.
  (Covered by `test_no_match_for_query_empty_state_mirrors_cli` and, at the
  client layer, `test_no_match_search_yields_no_results`.)
- **Whitespace-only query = list all.** `q` is `.strip()`-ed in both the route
  and `BdClient.memories`, so `"   "` lists everything rather than searching
  for spaces. (Covered by `test_whitespace_query_is_treated_as_list_all` and
  `test_blank_query_is_treated_as_list_all`.)
- **Count copy pluralizes.** `1 memory` vs `N memories`; with a query it
  switches to `N matching "<query>"`. (Covered by `test_singular_count_copy`
  and `test_search_passes_query_and_renders_matching_copy`.)
- **`aria-busy` + the skeleton are an accessibility pair.** The list region
  ships `aria-busy="true"` and the skeleton is `aria-hidden="true"`, so
  assistive tech waits silently for the real list rather than announcing
  shimmer placeholders. The real list announces itself via the `aria-live`
  count line once it swaps in. (The count line is `role="status"
  aria-live="polite"`, so filter changes are spoken without stealing focus.)
- **Debounce + cancellation.** 250ms debounce plus `hx-sync="this:replace"`
  means only the latest settled query actually hits the server; intermediate
  requests are cancelled, avoiding both subprocess churn and out-of-order
  swaps. (The debounce wiring is asserted by
  `test_memory_page_search_is_htmx_debounced_to_api_memory`.)
- **Search is bd's logic, not ours.** Matching is case-insensitive substring
  across key and body, done by `bd memories <term>` — bdboard never filters in
  Python or JS, so behavior stays identical to the CLI.
- **Bodies are markdown.** Each body runs through the shared `md` Jinja filter
  (`| md | safe`); the filter is responsible for sanitization. (Covered by
  `test_body_rendered_through_markdown_filter`.)
- **Special chars are escaped in card affordances.** The edit button stuffs the
  key/body into `data-*` attributes via Jinja `| e`, and forget passes the
  escaped key into `confirmForget('…')`, so quotes/HTML in a memory don't break
  the markup or the JS handlers. (Covered by
  `test_edit_button_escapes_special_chars_in_body`.)
- **bd failure degrades, never 500s the swap.** A `RuntimeError` from
  `bd.memories` returns an HTTP-200 inline "couldn't load" message so the page
  stays usable. (Covered by `test_bd_failure_degrades_gracefully`.) Note this
  is the *route's* graceful path; the underlying `BdClient.memories` still
  *raises* on subprocess failure or a non-object payload
  (`test_non_object_payload_raises`) — the route is what catches it.
- **Cheap page shell.** `GET /memory` never blocks on bd; all the bd work
  happens in the lazy `GET /api/memory` fetch, keeping initial paint instant.
  (Covered by `test_memory_page_list_region_lazy_loads`.)

## Source files

- `src/bdboard/app.py` — `page_memory` (`GET /memory`, ~354), `api_memory`
  (`GET /api/memory`, ~573).
- `src/bdboard/bd.py` — `BdClient.memories` (~249), `MEMORIES_TIMEOUT_S` (~40),
  `_cached` (TTL cache + gate + in-flight dedup, ~342), `_run_json` (~290),
  `SCHEMA_VERSION_KEY` (sentinel stripped from the payload).
- `src/bdboard/templates/memory.html` — the page shell: search strip
  (`#memory-q`, debounced `hx-get`), `+ New Memory` button, and the
  `#memory-list` region (`hx-trigger="load, refresh from:body"`,
  `aria-busy`).
- `src/bdboard/templates/partials/memory_list.html` — the swap fragment: count
  line (`role="status" aria-live="polite"`), cards, and the empty/no-match
  states.
- `src/bdboard/templates/partials/memory_skeleton.html` — the `aria-hidden`
  shimmer placeholder shown until the first fetch resolves.
- `tests/test_api_memory.py` — list/search/empty/no-match/markdown/degrade
  coverage for the `/api/memory` partial.
- `tests/test_page_memory.py` — page shell, labelled search strip, debounced
  wiring, lazy load, workspace-error parity.
- `tests/test_bd_memories.py` — `BdClient.memories` sentinel stripping, sort
  order, blank-query-as-list-all, non-object-payload-raises.
