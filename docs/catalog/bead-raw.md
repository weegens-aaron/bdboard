# Bead raw JSON view

Part of the **Board** page. See also [bead-modal.md](./bead-modal.md) (the
detail modal that links to this view), [bead-audit.md](./bead-audit.md) (the
other deep-dive view over a single bead), and
[store-cache.md](./store-cache.md) (the cache layer that backs the fallback
path).

## What it shows

The **raw JSON view** is an escape hatch: it dumps **every field bd knows
about** for a single bead as unstyled `application/json`, rendered by the
browser's own JSON viewer. It is reached via the **`raw JSON`** link in the
bead detail modal's view-source line (`view: … · raw JSON`), which opens
`/api/bead/{id}/raw` in a **new tab** (`target="_blank"`).

Unlike the modal — which curates and orders a known subset of fields for human
reading — this view shows the **complete, unshaped record**: schema-version
sentinels, internal/diagnostic keys, dependency arrays, timestamps, and any new
fields bd starts emitting that the modal hasn't been taught to render yet. It
exists for the moment you need to see something the modal layout hides.

There is no styling, no template, and no interactivity — it is a pure data
response a human (or a script) can read.

## Where the data comes from

- **Route:** `GET /api/bead/{bead_id}/raw` → `api_bead_raw` in
  `src/bdboard/app.py` (~1209), declared with `response_class=JSONResponse`. It
  returns a FastAPI `JSONResponse(full)` — the bead dict serialized straight to
  JSON, no Jinja template involved.
- **Primary read:** `bd.show_long(bead_id)` in `src/bdboard/bd.py` (~384) shells
  `bd show <id> --long --json`, unwraps bd's single-element array, and returns
  `(bead_dict, error)`. This is the **same fetch the modal uses**, so within the
  show cache's TTL the modal and the raw view serve the identical snapshot. The
  call is TTL-cached and in-flight-deduped via `BdClient._cached` (~342) under a
  per-bead key.
- **Fallback read:** if the live read returns no bead (`full is None` — timeout
  or bd error), the route calls `await store.snapshot()` to ensure the store's
  in-memory caches are loaded, then falls back to `store.bead(bead_id)`
  (`src/bdboard/store.py` ~248), which looks the id up in the active snapshot
  first, then the closed snapshot. This mirrors the modal's
  live-read-then-cache fallback (see [bead-modal.md](./bead-modal.md)).
- **Last-resort shape:** if **both** the live read and the cached snapshot miss,
  the response body is a synthetic `{"error": err or "not found"}` object — the
  endpoint always returns valid JSON with HTTP 200, never a 404 or an empty
  body.
- **Source of truth:** the bd workspace's local Dolt store. `bd show --long`
  *is* the canonical full record; the store snapshot is just bdboard's
  short-lived cache of the same data.

## What changes its state

- **On-demand fetch only.** This view has no persistent state of its own. Every
  time the `raw JSON` link is followed, the route runs a fresh `show_long`
  (subject to the cache TTL) and serializes whatever snapshot it gets at that
  instant. There is no SSE push, no polling, and no auto-refresh — reload the
  tab to re-fetch.
- **Shared cache invalidation.** Because it reads through the same
  `_show_cache` as the modal, a watcher-fire that calls
  `BdClient.invalidate_caches()` (~448) drops the cached show entry, so the next
  raw fetch reflects post-mutation state. Within the success TTL, repeated
  fetches return the cached snapshot.
- **Read-only.** The endpoint never mutates the bead; it only reads and
  serializes. Inline edits, status changes, etc. are made elsewhere and merely
  *observed* here on the next fetch.

## Edge cases & notes

- **Always-200 contract.** The route never raises to the client: a missing bead
  yields `{"error": "not found"}` (or the upstream error message) rather than an
  HTTP error. Consumers should check for an `error` key in the body, not rely on
  the status code, to detect a miss.
- **Two data sources, two shapes.** On the happy path the body is the full
  `bd show --long` record. On the fallback path it is the **store snapshot**
  shape (from `bd list`), which is **sparser** — it omits the expanded fields
  that only `--long` emits (e.g. full dependency arrays). The view does not flag
  which source it served, so the field set you see can differ depending on
  whether bd was reachable. (Contrast the modal, which surfaces this via its
  `view: Live details` / `Cached snapshot` line — the raw view has no such
  indicator.)
- **Shape is intentionally unstable / pass-through.** This endpoint deliberately
  does **no** shaping, ordering, or field-allow-listing — it echoes bd's output
  verbatim. That means the JSON shape tracks **whatever bd emits**: new fields,
  renamed fields, or schema-version bumps flow through untouched. Do **not**
  treat this as a stable API contract; it is a diagnostic escape hatch, not a
  versioned interface. Anything that needs a stable shape should read bd
  directly or go through a curated route.
- **Consumers.** The only in-app consumer is the modal's `raw JSON` link
  (`partials/bead_modal.html`, ~13), opened in a new browser tab. Beyond that
  it is a human/debugging surface — handy for `curl`/`jq` against a running
  instance — but nothing in bdboard parses its output programmatically.
- **No template, no tests.** There is no Jinja partial for this view (the
  browser renders the JSON) and, as of this writing, no dedicated test module
  exercises the route — the underlying `show_long` and `store.bead` paths are
  covered by the modal's tests. A future change should consider adding a small
  route test for the not-found / fallback branches.
- **New tab, not the modal.** Following the link navigates away into a fresh
  tab rather than swapping modal content, so it never disturbs the open modal or
  its lazily-loaded audit section.

## Source files

- `src/bdboard/app.py` — `api_bead_raw` (route, ~1209).
- `src/bdboard/bd.py` — `BdClient.show_long` (`bd show --long --json`, ~384),
  `_cached` (~342), `invalidate_caches` (~448).
- `src/bdboard/store.py` — `Store.snapshot` (~105) and `Store.bead` (~248), the
  cached-fallback path.
- `src/bdboard/templates/partials/bead_modal.html` — the `raw JSON` link in the
  modal's view-source line (~13) that opens this endpoint in a new tab.
