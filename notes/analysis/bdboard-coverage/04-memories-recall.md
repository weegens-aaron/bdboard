# Memories & Recall — Coverage Findings

> Owner bead: bdboard-hdol. Field-guide chapter: `field-guide-04-memories-and-recall.html` (chapter 4).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `memories-recall`                              |
| Field-guide ref  | `field-guide-04-memories-and-recall.html` (chapter 4) |
| bdboard owner    | `bdboard-hdol`                                 |
| Primary sources  | `src/bdboard/templates/memory.html`, `templates/partials/memory_list.html`, `memory_skeleton.html`; `src/bdboard/bd.py` (`memories`/`remember`/`forget`); `src/bdboard/app.py` (`page_memory`, `api_memory`, `api_memory_create`, `api_memory_delete`); `notes/catalog/memory-list.md`, `memory-create.md`, `memory-delete.md`; `notes/design/bdboard-5p1/memory-view-design.md` |
| Status           | `done`                                         |

---

## 1. AVAILABLE — what the field guide documents

bd 1.0.5 exposes a **persistent-memory layer**: short, keyed insights that
survive across sessions and account rotations and are **injected at `bd prime`**
so every agent session starts warm. Chapter 4 ("Memories & Recall") frames this
as the durable knowledge store. The chapter 4 rendered prose ships as the same
compressed React/`__bundler` base64 payload as chapter 3 (the lone `bm25`
substring in the 2.9 MB file is a coincidental fragment **inside** a base64
blob, not prose — verified), so the surface below is sourced from the **installed
`bd` binary's own `--help` and `--json` behaviour** (a stronger citation than
un-extractable slide text) and corroborated by the bdboard spike in
`notes/design/bdboard-5p1/memory-view-design.md` section 2.

**The four memory verbs (verified against `bd 1.0.5 (6a3f515ce)`):**

- **`bd remember "<insight>" [--key <key>]`** — store a memory. The body is a
  **positional** arg; `--key` is optional. *"If a memory with this key already
  exists, it will be updated in place"* (verbatim from `--help`) — i.e. it is an
  **UPSERT, not an append**. **If `--key` is omitted, bd auto-generates a key
  from the content.**
- **`bd memories [search]`** — list all memories, or filter by a search term.
  Search is bd's own **case-insensitive substring match across key AND body**.
  `--json` returns a **flat `{key: body}` object plus a `schema_version: 1`
  sentinel**; a no-match search returns just `{"schema_version": 1}`. Ordering
  is **alphabetical by key** — there is **no ranking**.
- **`bd recall <key>`** — retrieve the full content of **one** memory by its
  **exact key**. `--json` -> `{"found": bool, "key", "schema_version", "value"}`.
  This is a point-lookup, **not** a ranked/fuzzy retrieval.
- **`bd forget <key>`** — delete a memory by key. Key-not-found is a **failure**
  (non-zero exit), not a silent no-op.

**Prime injection:** memories are surfaced automatically at `bd prime` — that is
the whole reason the store exists (no manual loading per session).

### 1.1 CRITICAL — the "wing / scope / BM25 ranking" hypothesis is REFUTED

The bead's GAP prompt asks about *"wing/scope, BM25 ranking, key collisions,
upsert-vs-append semantics."* Empirically, **bd's memory layer has none of the
first two**:

- **No wing / no scope.** None of the four verbs accept a `--wing`/`--scope`
  flag (verified: full `--help` for all four shows only `--key` on `remember`
  plus global flags). bd memories are a **single flat namespace** keyed by a
  string.
- **No BM25 / no ranking.** `bd memories <term>` is a flat substring filter
  returned **alphabetically by key** (verified: `bd memories formula --json`
  returned 6 hits in pure key-alpha order, not relevance order). `bd recall` is
  an **exact-key fetch**. There is no scoring anywhere.

Those scope/wing/BM25 semantics belong to a **different** memory system (the
code-puppy "kennel": `repo:`/`agent:`/`user:` wings, BM25-ranked recall) — **not
to bd**. This matters for the synthesis bead (`bdboard-bk1r`): do **not** file a
"add wing filter / ranked search to bdboard's memory view" gap. bdboard faithful
to bd means a flat alphabetical list with substring search — which is exactly
what it ships. (See GAP 6 / Notes.)

The remaining two hypotheses **do** apply and are real: **upsert-vs-append** is a
genuine semantic bdboard must convey (it does — see section 2), and **key
collisions** are a silent-overwrite consequence of upsert (also conveyed — see
section 2 / GAP 5).

---

## 2. REFLECTED — what bdboard actually displays

bdboard ships a dedicated **Memory page** at `/memory` (`templates/memory.html`)
with a lazy list partial at `/api/memory` (`templates/partials/memory_list.html`).
It reflects **three** of the four verbs (`memories`, `remember`, `forget`) and
deliberately omits the fourth (`recall`).

**list + search — FAITHFUL.** `BdClient.memories()` (`bd.py:378-415`) shells
`bd memories [term] --json`, strips the `schema_version` sentinel
(`bd.py:414`, `SCHEMA_VERSION_KEY` `bd.py:58`), and returns `{key, body}` dicts
**sorted alphabetically by key** (`bd.py:412-414`) — matching the CLI's ordering
exactly. Search is **server-side**: the term is passed straight to
`bd memories <term>` (`bd.py:396-398`), so bdboard never re-implements matching
in Python or JS — case-insensitive substring across key+body stays identical to
the CLI (catalog: `memory-list.md`, "Search is bd's logic, not ours"). The search
strip is a debounced HTMX input (`memory.html`: `hx-trigger="keyup changed
delay:250ms, search"`, `hx-sync="this:replace"`). Cards render the **key** as a
monospace `<h3 class="memory-key">` and the **body** through the shared markdown
filter (`memory_list.html`: `{{ m.body | md | safe }}`). The count line is
`aria-live` (`memory_list.html`), with distinct empty-vs-no-match copy.

**create / edit (remember = upsert) — FAITHFUL, incl. the upsert semantic.**
`BdClient.remember(key, body)` (`bd.py:590-609`) shells `bd remember "<body>"
--key <key>` (body positional, key via flag — `bd.py:602`) and clears the cache.
The route `api_memory_create` (`app.py ~621`, per `memory-create.md`) is the swap
target. The create/edit dialog (`memory.html` `#memory-form-dialog`) **surfaces
the upsert semantic explicitly**: the Key hint reads *"A short identifier... If it
exists, the body is updated."* Edit reuses the same dialog and **locks the key
`readonly`** (`memory.html` `editMemory()`) because `bd remember` keys by
`--key` and can't rename. There is **one** server op for both create and edit —
correctly mirroring bd's single upsert verb (no phantom "update" route).

**forget — FAITHFUL, with deliberate friction.** `BdClient.forget(key)`
(`bd.py:611-620`) shells `bd forget <key>`. The forget button opens a dedicated
confirm dialog (`memory.html` `#memory-forget-dialog`) whose warning copy names
the exact key and states memories are *"injected at `bd prime`, so forgetting one
silently degrades every future agent session"* — i.e. the **prime-injection**
concept is surfaced exactly where it matters most.

**prime injection — REFLECTED only as copy.** bdboard never renders the actual
assembled `bd prime` block, but the list *is* the set of memories that get
injected, and the create-hint plus forget-warning both name the prime mechanism.
Adequate for a read-mostly viewer.

### 2.1 NOT reflected (explicit)

- **`bd recall <key>` — not wired at all.** No `recall` call exists anywhere in
  `bd.py` (grep: zero matches outside this finding). bdboard exposes **no
  single-key fetch / permalink / detail view**. *Mitigation:* the list cards
  always render the **full** markdown body (not a truncated preview), so the
  user value of `recall` — read a memory's full content by key — is already met
  by the list. The design doc (`bdboard-5p1` section 2) noted recall as "useful
  for a detail/permalink fetch" but it was scoped out of v1. (See GAP 2.)
- **Auto-key generation — not exposed.** bd's `remember` auto-generates a key
  when `--key` is omitted; bdboard's create form makes **Key `required`**
  (`memory.html #memory-key-input required`), so the user must always supply a
  key. (See GAP 1.)
- **Recency / timestamps — impossible to show.** `bd memories --json` carries
  **no** `created_at`/`updated_at` (verified; design `bdboard-5p1` section 2.2),
  so bdboard can only sort alphabetically by key. A user cannot tell fresh from
  stale memories. This is an **upstream bd** data gap, not a bdboard rendering
  bug. (See GAP 3.)

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | Auto-key generation is unsurfaced: bd `remember` auto-derives a key from content when `--key` is omitted, but bdboard's create form makes **Key `required`** (`memory.html #memory-key-input`), so the affordance never appears. | P3 | File a bead: allow a blank Key on create -> omit `--key` so bd auto-generates (or add a "leave blank to auto-key" hint). |
| 2   | `bd recall <key>` (exact single-key fetch) is **not wired** (no `recall` in `bd.py`); there is no per-memory permalink/detail view. Mitigated because cards already render the full markdown body. | P3 | Optional: add a `/memory/{key}` permalink backed by `bd recall` for deep-linking/sharing a single memory. |
| 3   | No recency ordering possible: `bd memories --json` carries no `created_at`/`updated_at` (design `bdboard-5p1` section 2.2), so the list is alphabetical-by-key only — a user can't distinguish fresh from stale memories. Upstream bd data gap, not a render bug. | P3 | Track upstream: consume a bd timestamp field if/when `bd memories --json` adds one; until then keep alpha sort (don't shell `dolt` directly). |
| 4   | Forgetting a **nonexistent key** surfaces as a raw HTTP 500 ("Could not delete: <err>") rather than a graceful 404/no-op — bd treats key-not-found as a failure and the route passes it through (`memory-delete.md`). | P3 | File a bead: treat key-not-found on forget as a soft no-op (re-render the list) instead of a 500 alert. |
| 5   | Key-collision on **create** is only warned **statically** (the dialog hint) — there is no at-submit "key exists, overwrite?" check, so a fresh "+ New Memory" with an existing key silently overwrites that memory's body. Faithful to bd's upsert, but the friction is asymmetric vs forget's confirm dialog. | P4 | Optional: on create (not edit), pre-check the key and confirm before overwriting an existing memory. |
| 6   | **NO ACTION** — bd's memory layer has **no wing/scope and no BM25/ranking** (verified empirically); bdboard correctly invents none. Recorded so synthesis doesn't file a phantom "add scope filter / ranked search" gap. | P4 | None — flat alphabetical list + substring search **is** the faithful design. Wing/scope/BM25 belong to a different system (code-puppy kennel), not bd. |

### Severity rubric (DISPLAY tool)

| Sev | Meaning                                                                                                          |
| --- | -------------------------------------------------------------------------------------------------------------- |
| P0  | Display misrepresents bead state so a user decides wrong (e.g. blocked shown as Ready; reversed dependency direction — cf. `bdboard-fjk`). |
| P1  | A board-meaning concept is silently wrong or absent (e.g. a status that has no lane; a gate bead shown as plain work). |
| P2  | A capability is unsurfaced where showing it would materially improve fidelity.                                |
| P3  | Minor; narrow impact or workaround exists.                                                                    |
| P4  | Cosmetic / future-proofing only.                                                                             |

---

## Notes / open questions

- **Overall verdict: HIGH fidelity, no P0/P1.** bdboard's memory view is one of
  the most faithful surfaces audited so far. It mirrors three of bd's four verbs
  exactly (list/search/upsert/forget), delegates matching to bd (no divergence),
  preserves the CLI's alpha-by-key ordering, and — crucially — **conveys the
  upsert-vs-append semantic** in plain copy ("If it exists, the body is
  updated"). The only honest gaps are P3 unsurfaced capabilities and one upstream
  data limitation.
- **The headline correction (GAP 6 / section 1.1):** the bead prompt's
  "wing/scope/BM25 ranking" hypothesis does **not** apply to bd — those are
  code-puppy *kennel* concepts. bd's memory store is a flat, single-namespace,
  unranked key->body map. bdboard is faithful precisely **because** it doesn't
  invent scoping or ranking UI that bd has no data to back.
- **Cross-section:** the design bead `bdboard-5p1` deliberately scoped v1 to
  read+search and deferred recency (its bead D) and curate (its bead E, which
  later shipped — create/edit/forget are live). Recall (`bd recall`) was never
  picked up; GAP 2 is the only remaining verb-coverage hole, and it is
  effectively covered by full-body cards.
- **Methodology note:** AVAILABLE was sourced from the installed `bd 1.0.5`
  binary (`--help` + `--json` probes) because chapter 4's HTML ships as an
  un-extractable base64/React bundle — same constraint recorded for chapter 3
  in `03-status-lifecycle.md`. Runtime behaviour is a stronger citation than
  un-renderable slide prose.