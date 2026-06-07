# Data Layer (Dolt) — Coverage Findings

> Owner bead: bdboard-svbo. Field-guide chapter: `field-guide-08-data-layer.html` (chapter 8).

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `data-layer`                                       |
| Field-guide ref  | `field-guide-08-data-layer.html` (chapter 8)                          |
| bdboard owner    | `bdboard-svbo`                                       |
| Primary sources  | `src/bdboard/bd.py` (`list_active`/`list_closed`/`list_closed_history`, `revision_signature`, `watch_targets`, `_subprocess_gate`); `src/bdboard/store.py` (three-way split cache, `refresh`); `src/bdboard/watcher.py` (`RefreshScheduler`); `src/bdboard/events.py` (`EventBus`); `src/bdboard/app.py` (`_watch_beads`, `sse_events`); `src/bdboard/templates/base.html` (live-status pill); `docs/decisions/0003`,`0004`,`0005`; `docs/catalog/store-cache.md`, `sse-live-refresh.md` |
| Status           | `done`                                  |

---

## 1. AVAILABLE — what the field guide documents

Source note: chapter 8's rendered prose ships as a compressed React bundle (same
constraint as chapters 3 & 7). The surface below is sourced from the chapter's
**verified reference outline**
(`training/beads/volumes/field-guide-08-data-layer/OUTLINE.md`, audited against
bd v1.0.4 `ce242a879` against `gastownhall/beads` `docs/SYNC_CONCEPTS.md`), which
supersedes the slide bundle.

Chapter 8 ("The Data Layer — Dolt, Sync & Federation") is the **primary owner of
where beads LIVE and how they MOVE**. Key surface (OUTLINE §I–VIII):

- **Three layers, one source of truth** (OUTLINE §I). (1) The **Dolt DB** is
  canonical for every read AND write (`bd list/show/ready/...`). (2) The **wire**
  is `refs/dolt/data` — a git-compatible ref namespace on the *same* remote as
  the code, separate from `refs/heads/*`. (3) **`.beads/issues.jsonl` is a
  passive export** ("a souvenir, not the cargo"): human-diffable, git-tracked,
  regenerated from the DB, **NOT** the sync channel.
- **Storage / engine modes** (OUTLINE §II). Embedded (in-process,
  `.beads/embeddeddolt/`) vs sql-server (`.beads/dolt/`). `dolt-auto-commit
  off|on|batch` controls commit amplification. `.beads/` anatomy: DB dirs are
  gitignored (travel via `refs/dolt/data`); `issues.jsonl`, `interactions.jsonl`,
  `config.yaml`, `metadata.json`, `hooks/` are tracked; `ephemeral.sqlite3*`
  (wisps), locks, `export-state.json`, `.beads-credential-key` are local-only.
  `bd sql` is **unsupported in embedded mode**.
- **Sync, concretely** (OUTLINE §III). `bd dolt push` / `bd dolt pull` (a true
  three-way DB *row* merge, not a JSONL text merge), plus
  `bd dolt status|commit|remote add|list|remove`. `bd init` auto-wires a Dolt
  remote `origin` from `git remote get-url origin`. `bd bootstrap` is the
  fresh-clone/recovery command (auto-detects: sync.remote → `refs/dolt/data` →
  backup → JSONL import → fresh). Git hooks: **pre-commit refreshes the JSONL
  export** when `export.auto=true`; post-merge/post-checkout *skip* JSONL import
  when `sync.remote` is set; **durable sync is always `bd dolt push/pull`.**
- **JSONL is a souvenir** (OUTLINE §IV). `bd export` (excludes infra beads + memories
  by default), `bd import` (**upsert-only** — cannot infer deletions). **Anti-patterns:**
  (1) treating JSONL as truth, (2) `bd import` as a `bd dolt pull` substitute
  (silently drifts), (3) third-party Dolt hosting before the default origin. The
  one exception: `no-db: true` config makes JSONL the source of truth (opt-in, off
  by default).
- **Version control over issues** (OUTLINE §V). `bd branch`, `bd vc
  status|commit|merge`, `bd history <id>` (per-issue version history),
  `bd diff <a> <b>`. `bd history`/`diff` are the DB-wide view of the same
  append-only audit trail Vol I surfaces per bead.
- **Several stores behind one workspace** (OUTLINE §VI). `bd kv set|get|list|clear`
  (Dolt kv table). **Memories are kv rows under the `memory.` prefix** (Vol IV
  is the user surface). **Wisps/ephemeral molecules live in a separate SQLite DB
  `.beads/ephemeral.sqlite3` — gitignored, never hits the wire** (Vol V).
- **Federation & cross-project** (OUTLINE §VII). `bd federation
  add-peer|list-peers|remove-peer|status|sync` (peer towns, encrypted creds,
  sovereignty tiers); `bd repo add|list|remove|sync` (multi-repo hydration,
  distinct from federation); `bd ship` / `external:<project>:<capability>` edges.
- **History maintenance** (OUTLINE §VIII). `bd compact` (squash old Dolt
  commits), `bd flatten` (squash ALL — irreversible), `bd gc` (decay+compact+gc),
  `bd prune`/`bd purge` (permanently DELETE rows from the DB), `bd backup
  init|sync|restore|status` (the real off-machine backup flow), `bd restore <id>`
  (recover a compacted issue's pre-truncation text — NOT a backup restore),
  `bd migrate`, `bd batch`.

bdboard's own deployment uses exactly this model: Dolt remote `origin` →
`refs/dolt/data` on the code origin, `bd dolt push` to replicate, `bd bootstrap`
to hydrate (ADR 0003).

## 2. REFLECTED — what bdboard actually displays

**Headline: bdboard is a faithful *reader* of the local Dolt DB but a total
*blind spot* on sync.** It correctly honors the chapter's #1 doctrine ("Dolt DB
via the bd CLI is truth; JSONL is a souvenir") — and it is structurally
always-fresh against *local* Dolt. But it surfaces **zero** of the chapter's
movement layer: no `bd dolt push/pull/status/remote`, no ahead/behind, no remote
config, no "is this read-only" badge. A repo-wide search of `src/bdboard/**` for
`dolt`, `push`, `pull`, `remote`, `bootstrap`, `federation`, `repo`, `ship`,
`backup`, `prune`, `kv`, `branch`, `vc`, `flatten` returns **no feature code** —
only descriptive comments in `bd.py`/`store.py` about Dolt's *internals* (the
manifest/noms churn the watcher copes with). Itemized:

### 2.1 Runtime source of truth is faithful — bd CLI JSON, never the JSONL

bdboard reads bead state **only** through `bd … --json` (`BdClient` in `bd.py`),
**never** `.beads/issues.jsonl`, and **never writes** to `.beads/` (ADR 0004;
`docs/catalog/store-cache.md` "Source of truth"). It even refuses to *require*
the JSONL to exist (`bd.py:244-246`: "modern bd workspaces are dolt-backed and
the JSONL is just a secondary export that may be absent or stale"). This is the
chapter's anti-pattern #1 honored correctly — bdboard treats Dolt-via-CLI as
canonical and the JSONL as the deprecated souvenir it is.

### 2.2 The read is a three-way split, not a single fetch

`list_active()` / `list_closed()` / `list_closed_history()` (`bd.py:263-376`)
back three independent `Store` caches (`store.py` `_active_snap` /
`_closed_snap` / `_history_snap`). All `bd` subprocesses serialize through one
`asyncio.Semaphore(1)` (`_subprocess_gate`, `bd.py:118`) precisely because **bd's
embedded Dolt server is single-writer and lock-prone** (the chapter's
embedded-mode reality). This is bdboard reflecting a Dolt *constraint* in its
architecture, even though it never names Dolt in the UI.

### 2.3 Live freshness is built on watching Dolt's own object store

The watcher (`app.py:_watch_beads`, scheduled by `RefreshScheduler` in
`watcher.py`) watches each Dolt db's `.dolt/noms/` dir **non-recursively** plus
`.beads/` (`bd.py:watch_targets`, ADR 0005). It copes with two Dolt-specific
realities the chapter implies: (a) a *read-only* `bd list` still rewrites the
`noms/` manifest, so `Store.refresh()` first compares
`BdClient.revision_signature()` — the per-db **manifest root-hash**
(`bd.py:200-235`) — and **skips the subprocess when the committed Dolt state is
byte-identical** (the self-feedback-loop guard, bdboard-ywep); (b) one logical
`bd` write fans out to 3–5 files, absorbed by the debounce/cooldown. So bdboard's
liveness is literally a reflection of Dolt's commit mechanics. SSE then
broadcasts a single `beads_changed` only when the bead list structurally changed
(`events.py`; `docs/catalog/sse-live-refresh.md`).

### 2.4 The only "history/VC" surface that IS reflected: per-bead `bd history`

The modal's Lifecycle + Audit-trail views are built from `bd history <id>`
(`bd.py:history`, `derive/history.py`, `templates/partials/bead_audit.html`) —
i.e. the chapter §V per-issue version history. But this is the *only* slice of
the VC surface present: no DB-wide `bd diff`, no `bd branch`/`bd vc status`, no
commit identity. (Detailed in area 1/anatomy + area 7/swarms audits; noted here
for completeness, not re-filed.)

### 2.5 The "live · push" pill reflects the SSE socket, NOT Dolt sync

The masthead/footer live-status pill (`base.html:223-224`, JS `:533-544`) shows
`connecting…` → **`live · push`** (`live-on`) → `reconnecting…` (`live-off`).
These map *only* to the browser `EventSource` connection lifecycle
(`sse-live-refresh.md` "What it shows"). The word **"push"** here means "the SSE
server is pushing refresh signals," **not** `bd dolt push` and **not** "your
data is synced to origin." This is the single most confusable surface in the
whole data layer (see GAP 1, GAP 4).

### 2.6 NOT reflected — the entire movement & maintenance layer

Explicitly absent (silence stated as a finding per the template):

- **Sync state:** no indication of whether a remote is configured, whether local
  Dolt is **ahead of** origin (unpushed local writes) or **behind** origin
  (someone else pushed `refs/dolt/data`; you haven't `bd dolt pull`ed). bdboard
  reads *local* Dolt and has no concept of `origin` at all.
- **Read-only posture:** bdboard never writes `.beads/` (ADR 0004) but **never
  tells the user that** — there is no "read-only / never exports" badge, so a
  user can't distinguish "bdboard won't touch my data" from "bdboard might."
- **dolt-auto-commit policy**, **engine mode** (embedded vs sql-server),
  **backup status** (`bd backup status`): none surfaced.
- **kv store** (`bd kv list`): not surfaced. (Memories — the `memory.`-prefixed
  kv rows — ARE surfaced via the Memory page, but as memories, owned by area 4;
  the generic kv table is invisible.)
- **Federation / `bd repo` / `ship`**: zero awareness.
- **Maintenance verbs** (`compact`/`flatten`/`gc`/`prune`/`purge`): no signal —
  e.g. a board can't tell a user that closed beads were pruned vs simply outside
  the window (compounds GAP 2).

## 3. GAPS — what's misrepresented or unshown, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | **No sync-state visibility whatsoever:** bdboard reads local Dolt and never calls `bd dolt status/remote`, so it cannot show unpushed local writes (ahead of origin) or unpulled remote writes (behind origin) — a teammate's `bd dolt push` leaves your board silently stale-vs-origin with no signal. | P2 | File a bead: add a sync badge that shells `bd dolt status` / `bd dolt remote list` (e.g. "↑N unpushed · ↓ behind · no remote") in the masthead. |
| 2   | **Window-bounded closed lane silently clips old closures:** the board Closed lane AND masthead CLOSED KPI only show closures within `BOARD_CLOSED_WINDOW_DAYS = 3` (`derive/lanes.py:40`, `bd.py:298-304`) with no "showing last 3 days" affordance — a user can't tell "no old closures" from "old closures hidden." | P2 | File a bead: label the Closed lane with its active window + a "see History for older" link (History page is uncapped, bdboard-a194). |
| 3   | **Refresh-failure silent staleness:** if `bd list` repeatedly raises, `Store.refresh()` keeps the previous snapshot and returns `False` (`store.py` serve-stale-on-failure) — correct for a transient blip, but a *sustained* failure freezes the board on stale data with **only a log line**, no UI banner. | P2 | File a bead: surface refresh-error state (e.g. a "data stale — last updated HH:MM" banner) when N consecutive refreshes fail. |
| 4   | **The "live · push" pill is confusable with `bd dolt push`/origin sync:** it reflects only the SSE socket (`base.html:543`), so it can read "live · push" while the board is frozen-stale (GAP 3) or behind origin (GAP 1). | P3 | Minor: relabel to "live · updates" / "connected" so it can't be read as a Dolt-sync indicator. |
| 5   | **No read-only / never-exports posture shown:** bdboard never writes `.beads/` or runs `bd export` (ADR 0004/0005) but gives the user no badge saying so — a safety property left invisible. | P3 | Minor: add a subtle "read-only view" indicator so users know bdboard never mutates their workspace. |
| 6   | **Active-only first paint can transiently mis-derive blocked-by-closed:** before the closed cache lazy-loads, a bead depending on a closed bead shows blocked until phase 2 (ADR 0004 / bdboard-owz). Self-healing, ~one refresh window. | P4 | Cosmetic/known trade-off; cross-ref area 2 (dependency-graph) — do not double-file. |
| 7   | **kv store / engine mode / dolt-auto-commit / backup status unsurfaced:** workspace-health facts a "data layer" dashboard could show are entirely absent (memories aside, owned by area 4). | P3 | File a bead (optional): a small "workspace" panel — engine mode, remote, last backup, kv count — for operators. |

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

- **Freshness verdict (the core ask):** bdboard is **never silently stale
  against *local* Dolt** — it is structurally always-fresh (live refresh ~250ms,
  revision-signature skip, serve-stale-*only*-on-failure-with-a-loud-log). The
  silent-staleness paths are all about (a) **local-vs-origin divergence**, which
  bdboard has no concept of (GAP 1), (b) the **3-day closed window** clipping
  old closures unannounced (GAP 2), and (c) **sustained refresh failure**
  freezing the board with no UI signal (GAP 3). None are rated above P2 because
  none *misrepresent a bead's state so a user acts on the wrong bead* (that would
  be P0); they withhold context the user would want, which is textbook P2.
- **Why no P0/P1 here:** unlike the dependency-direction P0 (`bdboard-fjk`) or a
  statusless lane (a P1), nothing in the data layer makes the board show a *wrong*
  bead state. The board is faithful to *local* truth; it just doesn't narrate the
  movement layer around that truth. The most "dangerous" item is GAP 1+4 in
  combination (a `live · push` pill while silently behind origin), but even then
  the displayed beads are accurate to local Dolt — so P2/P3, not P1.
- **Faithful-by-design, not gaps:** reading bd-CLI-JSON over `issues.jsonl`,
  never writing `.beads/`, and the subprocess gate are all *correct* reflections
  of the chapter's doctrine (anti-pattern #1, embedded single-writer). They are
  strengths, recorded in §2.1–2.3, not gaps.
- **Cross-section:** GAP 2 (closed window) touches area 3 (status-lifecycle) and
  the board-counts catalog; GAP 6 touches area 2 (dependency-graph). Reference,
  don't duplicate. Memories-as-kv (chapter §VI) is owned by area 4.
