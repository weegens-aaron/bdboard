# bdboard-0r1 audit findings: noisy errors + historical comments

Date: 2026-05-28
Scope: `src/`, templates, and top-level `README.md`

Legend for recommended action:
- **keep**: current wording is useful and current-state focused
- **rewrite**: keep intent, tighten wording/tone/scope
- **remove**: delete without replacement
- **convert-to-bead**: track in beads as follow-up work

## 1) User-facing error messages and log output

### `src/bdboard/bd.py`
1. **L159, L163, L167**
   - Text includes full bd subcommand in error (`bd {' '.join(args)} ...`).
   - Rationale: this can leak internal command shape to users when surfaced in UI warnings (`bead_modal.html` / `bead_audit.html`). Useful for debugging, noisy for users.
   - Action: **rewrite** (user-safe message for UI path; preserve detailed command in logs only).

2. **L96**
   - Error includes full local filesystem path (`no .beads/ directory in {self.workspace}`).
   - Rationale: path disclosure is high-noise for general users; can leak machine-specific details in screenshots.
   - Action: **rewrite** (prefer workspace name or generic text in user-facing surface).

3. **L101**
   - Error includes exact binary lookup detail (`looking for {self.bd_bin!r}`).
   - Rationale: borderline implementation detail; useful in CLI, less so in web error page.
   - Action: **keep** for CLI/dev diagnostics, but sanitize in UI rendering path (follow-up implementation).

### `src/bdboard/store.py`
4. **L83 (`log.exception`)**
   - `exception` logging emits traceback on refresh failures.
   - Rationale: operator logs should keep stack traces; this is not user-facing unless logs are surfaced.
   - Action: **keep**.

### `src/bdboard/app.py`
5. **L195 (`log.exception`)**
   - Traceback-heavy watcher restart message.
   - Rationale: appropriate operational signal; not shown directly in UI.
   - Action: **keep**.

6. **L315**
   - Not-found modal returns raw `bead_id` embedded in HTML.
   - Rationale: ID itself is likely safe, but no recovery guidance and inconsistent tone.
   - Action: **rewrite** (friendlier wording + actionable next step).

### `src/bdboard/templates/partials/bead_audit.html`
7. **L4**
   - UI prints full raw backend error in `<code>{{ error }}</code>`.
   - Rationale: directly exposes internal command failures, timeouts, and parse details to end users.
   - Action: **rewrite** (show generic “history unavailable” message; keep details in logs).

### `src/bdboard/templates/partials/bead_modal.html`
8. **L12**
   - Warning banner shows raw backend error string.
   - Rationale: leaks implementation detail and produces inconsistent tone.
   - Action: **rewrite** (user-safe fallback warning text).

9. **L13**
   - `source: bd show --long` / `bd list (fallback — bd show failed)` visible in UI.
   - Rationale: exposes implementation internals with little end-user value.
   - Action: **rewrite** (replace with user-oriented source labels or remove source line).

### `src/bdboard/cli.py`
10. **L114–L115**
    - Error advises `lsof` command directly.
    - Rationale: actionable for technical users, but tone/assumption mismatch for broader audience.
    - Action: **rewrite** (short guidance + optional advanced hint).

## 2) Code comments and docstrings with historical drift

### `src/bdboard/app.py`
11. **L296 comment**
    - `# ----- bead detail (the bug fix the user actually asked for) -----`
    - Rationale: explicitly historical process note, not current intent.
    - Action: **remove**.

12. **L398–L405 duplicate heading comments**
    - Two near-duplicate comment blocks describing `_FIELD_ORDER` (first superseded by second).
    - Rationale: redundant and noisy.
    - Action: **remove** first block, **keep** single canonical block.

13. **L410**
    - `Aaron's preferred top-of-modal` in inline comment.
    - Rationale: personal history/context rather than product behavior.
    - Action: **rewrite** (describe UX intent, not person/history).

14. **L506**
    - `so v0 ships with zero ... surprises`.
    - Rationale: release-history phrasing; should describe present behavior.
    - Action: **rewrite**.

### `src/bdboard/bd.py`
15. **L15, L73, L181 + module docstring L3–L19**
    - References to `bcc/bdboard v0`, “clicked too fast = 404”, and comparative historical framing.
    - Rationale: implementation may still be valid, but wording anchors on project history.
    - Action: **rewrite** (describe failure mode/benefit without legacy references).

16. **L67–L68**
    - External project-specific breadcrumb (`mantoni/beads-ui server/bd.js withBdRunQueue`).
    - Rationale: useful provenance, but too deep for inline maintenance comment.
    - Action: **convert-to-bead** (move provenance to architecture docs), then **rewrite** inline comment shorter.

### `src/bdboard/derive.py`
17. **L6**
    - `Lane assignment (mirrors bcc's lanes.go)`.
    - Rationale: historical framing; current behavior should stand alone.
    - Action: **rewrite**.

### `src/bdboard/store.py`
18. **L28–L29**
    - `The old sorted-line hash was a workaround ...`
    - Rationale: historical detail is accurate but belongs in design docs/changelog, not primary module docstring.
    - Action: **rewrite** (briefly justify current approach only).

### `src/bdboard/templates/partials/bead_audit.html`
19. **L5**
    - Inline text references `bcc's old failure mode`.
    - Rationale: user-visible legacy/project-history detail with no user value.
    - Action: **rewrite**.

### `src/bdboard/templates/base.html`
20. **L44**
    - Comment says event fires when `.beads/issues.jsonl` changes.
    - Rationale: stale/inaccurate per current watcher behavior (`.beads/` recursive, dolt-native).
    - Action: **rewrite**.

### `README.md`
21. **L53**
    - Claims lanes derive from `.beads/issues.jsonl` while adjacent text says JSONL is not read directly.
    - Rationale: inconsistent and historically confusing.
    - Action: **rewrite**.

22. **L42+ section “What’s different from bcc” + multiple references**
    - Heavy comparative framing to prior project.
    - Rationale: historical context may be useful for migration docs, but creates drift in primary README.
    - Action: **convert-to-bead** (split “migration from bcc” into dedicated doc; simplify README to current behavior).

## 3) UI copy / template legacy language

### `src/bdboard/templates/partials/bead_modal.html`
23. **L18 `All fields`**
   - Generic heading, low information value.
   - Rationale: not legacy, but vague.
   - Action: **rewrite** to `Bead details` or equivalent.

### `src/bdboard/templates/partials/bead_audit.html`
24. **L5 muted help text**
   - User-facing mention of historical bcc failure mode.
   - Rationale: legacy concept in live UI.
   - Action: **rewrite**.

## 4) TODO/FIXME/HACK/XXX and commented-out code scan results

- Searched `src/` and `tests/` for `TODO|FIXME|HACK|XXX|NOTE` markers and obvious commented-out code blocks.
- Result: **no stale TODO/FIXME/HACK/XXX markers** and **no commented-out code blocks** found.
- Action: **keep** (no cleanup required in this category).

## Follow-up bead(s) filed for preservation and implementation

- `bdboard-68q` (task): apply this audit’s rewrites/removals for user-facing messages, stale historical comments, and README/template copy cleanup.
- Historical provenance worth preserving (e.g., prior queueing rationale) should move to architecture docs as part of that bead, not remain inline in code.
