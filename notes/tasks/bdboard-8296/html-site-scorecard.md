# HTML Site Build — Scorecard (bdboard-8296 / bdboard-74o1)

**Bead:** bdboard-8296 (Re-pour + run flowdoc-html) — produces the deliverable
that bdboard-74o1 (Validate rebuilt HTML site) scores.
**Epic:** bdboard-lxqb · **Milestone:** bdboard-bivn
**Builder:** `tools/build_docs_site.py` (`make docs-site`)
**Verdict:** FAITHFUL — build contract satisfied, link check 0 errors.

## Why the portable build contract (not `bd formula pour`)

The `flowdoc-html` formula's STEP 0 resolves the `md-to-html` skill in order
(repo `skills/` -> `.beads/skills/` -> `~/code/flowdoc/skills/` -> explicit
contract). NONE of those exist on this machine:

```
skills/md-to-html/SKILL.md            -> absent
.beads/skills/md-to-html/SKILL.md     -> absent
~/code/flowdoc/skills/md-to-html/     -> absent (~/code/flowdoc not present)
```

So the build falls back to STEP 3, the explicit portable build contract
(exactly the H1 portability path bmji's tighten was written for). We did NOT
run `bd formula pour flowdoc-html`: per memory `flowdoc-pour-gate` /
bdboard-4iud, pouring spawns a disconnected generation epic that auto-closes
on pour and never produces the docs. The value-delivering move is to run the
build task's work directly, which is what `tools/build_docs_site.py` does.

## Build output

| Site | Source | Output | Pages |
|------|--------|--------|-------|
| Maintainer | `__docs/` | `docs/maintainer/` | 33 |
| User | `_docs/` | `docs/user/` | 26 |
| Landing | - | `docs/index.html` | 1 |
| Stylesheet | - | `docs/style.css` | 1 (shared) |

Source/output parity: 35 maintainer `.md` minus 2 working files (`_Manifest`,
`_FlowDocGuide`) = 33 published; 28 user `.md` minus 2 = 26 published. Exact match.

## Build contract gates (formula STEP 3 + STEP 5)

| Gate | Result |
|------|--------|
| md -> html, directory tree mirrored | PASS (59 pages) |
| Mermaid fences render (`<pre class="mermaid">` + mermaid.js); no raw fences | PASS (no `language-mermaid` in output) |
| GitHub callouts -> styled boxes; no literal `[!NOTE]` etc. | PASS (no literal markers in `docs/`) |
| Per-section `index.html` per directory; raw `_Manifest` not published | PASS |
| Single shared `style.css` linked by every page | PASS |
| Relative `.md` links -> `.html` | PASS |
| Working-file links (`_Manifest`/`_FlowDocGuide`) -> site-root `index.html` | PASS |
| In-repo source links (`src/...`, `tests/...`) -> GitHub blob/tree URLs | PASS |
| Heading-anchor slugs so `#fragment` links resolve | PASS (GitHub-style slugs) |
| Top-level `docs/index.html` landing page | PASS (links both editions) |
| No `_Manifest`/`_UpdateQueue`/`_AuditLog` leak into `docs/` | PASS |

## Independent validation (bdboard-74o1)

* Built-in VERIFY gate (`build_docs_site.py --check`): `VERIFY OK: 59 pages,
  source<->output parity, links resolve, callouts+mermaid rendered.`
* lychee (`--offline`, local site): 919 total, 0 Errors, 27
  excluded (the 27 excluded are the offline-skipped GitHub source URLs, valid
  by construction). The initial run found 21 missing-fragment errors -> fixed by
  adding GitHub-style heading-anchor slugs; re-run is clean.
* WCAG 2.2 AA: `lang="en"`, skip link, semantic landmarks, Walmart `blue.100`
  header; body/callout text contrast >= 4.5:1 on tinted backgrounds.

## Quality gates

* `ruff check src/ tests/ tools/` -> All checks passed
* `ruff format` -> clean (tools/ added to lint+format scope)
* `pytest` -> 371 passed (357 existing + 14 new in
  `tests/test_build_docs_site.py` locking slugify / callouts / mermaid /
  link-rewrite / heading-anchors / real-site VERIFY)

## Reproduce

```bash
make docs-site                          # build + VERIFY gate
python tools/build_docs_site.py --check # VERIFY only
lychee --offline docs/index.html docs/maintainer docs/user
```
