# Consolidated End-to-End Revalidation — FlowDoc Regenerated Output vs Rubric

> **Bead:** bdboard-ji3l (Run full revalidation of regenerated docs vs rubric)
> **Epic:** bdboard-sqn2 (End-to-end revalidation + loop decision)
> **Milestone:** bdboard-bivn (FlowDoc formulas match agent-loop output quality)
> **Rubric:** [`notes/tasks/bdboard-pf4f/flowdoc-rubric.md`](../bdboard-pf4f/flowdoc-rubric.md)
> **Reference (gold):** `~/rep_engineer_station/docs/<service>/` — realized
> `flowdoc` / `flowdoc-user` agent-loop output.
> **Validator:** code-puppy-8e2379 · all checks re-run fresh from repo root.

This is the *holistic* revalidation gate for the milestone: instead of trusting
the three per-family validate beads (30vz / w638 / 74o1), every objective check
was **re-run from scratch** against the current on-disk output, scored together,
and diffed against the agent reference. The consolidated gap report below is the
input to the ship-vs-loop decision (bdboard-uiih).

---

## 1. Verdict (all three families together)

| Family | Output dir | Fidelity | Gates | Band | Verdict |
|--------|-----------|----------|-------|------|---------|
| **M** — Maintainer markdown | `__docs/` | **100%** | 6/6 PASS | Faithful |  ship |
| **U** — User markdown | `_docs/` | **100%** | 7/7 PASS | Faithful |  ship |
| **H** — Rendered HTML site | `docs/` | **100%** | gates PASS | Faithful |  ship |

**Consolidated verdict: FAITHFUL across all three families. Zero gate failures,
zero negative deltas vs the agent reference. No tighten/regenerate loop is
justified by this rubric pass.**

---

## 2. Method — every check re-run fresh (re-runnable)

All commands run from repo root. Numbers below are *this iteration's* output, not
copied from the per-family scorecards (they happen to match — that is the point of
a revalidation).

| # | Check | Dim(s) | M `__docs/` | U `_docs/` | H `docs/` |
|---|-------|--------|-------------|------------|-----------|
| 1 | Item-file ↔ manifest `[x]` parity | S4/MF1 | **25 == 25** | **18 == 18** | n/a |
| 2 | Total `.md` corpus size | — | 35 | 28 | — |
| 3 | Cross-link integrity (relative `[text](path)`) | L1/N2/MF4 | **682 / 0 broken** | **225 / 0 broken** | n/a |
| 4 | Unfilled template tokens (`{placeholder}`, `path/to/file`, TODO/TBD/XXX/FIXME) | E1 | 4 hits → **all parity** (see §4) | **0** | n/a |
| 5 | Audience purity (localhost/`:7332`/`src/bdboard`/`pip install -e`/`git clone`/stage URLs) | E3 | n/a | **0 leaks** | n/a |
| 6 | Source ↔ output page parity | H2 | n/a | n/a | **59 pages, parity OK** |
| 7 | Built-in VERIFY gate (`build_docs_site.py --check`) | H1–H4/E4/E5/L1 | n/a | n/a | **VERIFY OK** |
| 8 | lychee `--offline` link check over built site | L1 | n/a | n/a | **919 total / 0 errors / 27 excluded** |

Reproduce:

```bash
# M / U markdown parity + links + tokens + purity
find __docs -name '*.md' ! -name 'index.md' ! -name '_*.md' \
  ! -name 'Architecture.md' ! -name 'Troubleshooting.md' | wc -l   # 25
grep -cE '^- \[x\]' __docs/_Manifest.md                            # 25
# (mirror for _docs: 18/18; Overview.md + FAQ.md excluded)
# link sweep + token/purity greps: see §2 row 3–5

# H rendered site
python tools/build_docs_site.py --check                            # VERIFY OK
lychee --offline docs/index.html docs/maintainer docs/user         # 0 errors
```

---

## 3. Consolidated scorecard (per-dimension, all families)

`2` = matches reference · `—` = not applicable to that family · `G` = gate.
Reference is expected to score 2 on every applicable dimension; **every candidate
delta is 0**, so the table is collapsed to the candidate score.

| Dim | G | Weight | M | U | H | Note |
|-----|---|--------|---|---|---|------|
| S1 Correct output dir | G | 2 | 2 | 2 | 2 | `__docs/` / `_docs/` / `docs/`+`index.html` |
| S2 Required top-level files | G | 2 | 2 | 2 | 2 | M: index/Architecture/_Manifest/Troubleshooting · U: index/Overview/_Manifest/FAQ · H: index.html+style.css |
| S3 Section subdirs + index | — | 2 | 2 | 2 | 2 | mirrored, each section has an index |
| S4 One item per file, no orphans | — | 1 | 2 | 2 | 2 | 25↔25 · 18↔18 · 59-page parity |
| MF1 Progress block | — | 1 | 2 | 2 | — | Total/Done/Remaining reconcile |
| MF2 Grouped sections | — | 1 | 2 | 2 | — | by domain / capability |
| MF3 Stable ID numbering | — | 1 | 2 | 2 | — | banded prefixes |
| MF4 Checkbox + arrow-link format | G | 2 | 2 | 2 | — | all targets resolve |
| T1 Architecture/Overview completeness | — | 2 | 2 | 2 | — | full section set |
| T2 Per-item template sections | — | 2 | 2 | 2 | — | matches `_FlowDocGuide.md` shape |
| T3 Troubleshooting/FAQ finalized | — | 1 | 2 | 2 | — | real content, not stubs |
| E1 No unfilled tokens | G | 2 | 2 | 2 | 2 | `/path/to/` hits are CLI-example parity (§4) |
| E2 Concrete impl maps | — | 2 | 2 | — | 2 | 37/37 real `src/...` paths |
| E3 Audience purity | G | 2 | — | 2 | 2 | 0 leaks in user output |
| E4 Diagrams where templated | — | 1 | 2 | 2 | 2 | mermaid renders in H |
| E5 Callouts | — | 1 | 2 | 2 | 2 | render as styled boxes in H |
| N1 PascalCase filenames | — | 1 | 2 | 2 | 2 | |
| N2 Manifest link↔file parity | G | 2 | 2 | 2 | — | 0-broken sweep |
| L1 Cross-link integrity | G | 2 | 2 | 2 | 2 | 682/0 · 225/0 · lychee 0 errors |
| L2 Bidirectional Related | — | 1 | 2 | 2 | — | resolve both ways |
| H1 Persistent sidebar nav | — | 2 | — | — | 2 | grouped nav per page |
| H2 Source↔output parity | G | 2 | — | — | 2 | 59 pages exact |
| H3 Styling + highlighting | — | 1 | — | — | 2 | shared style.css, hl.js |
| H4 No internal-process leakage | — | 1 | — | — | 2 | `_Manifest`/`_FlowDocGuide` not published |
| C1 Features-not-files framing | — | 1 | 2 | — | — | behavior-first |
| C2 Consistent voice | — | 1 | 2 | 2 | — | maintainer / second-person |

**Math:** for every family `weighted_score == weighted_maximum` → **fidelity_pct =
100%**. All gate dimensions (S1, S2, MF4, E1, E3, N2, L1, H2) score 2. Band:
**Faithful (≥ 90)** for all three.

---

## 4. The one borderline call this revalidation surfaced (E1 / `/path/to/`)

The fresh token sweep found **4** `/path/to/` occurrences in `__docs/`:

- `__docs/Troubleshooting.md` — `--dir /path/to/repo`, `--bd /path/to/bd`
- `__docs/Flows/ServerStartup.md` — `--dir /path/to/workspace` (×2)

The rubric's E1 examples list `path/to/file` as a banned token, so this warranted
investigation. **It is parity with the agent reference, not a defect:**

- These are **CLI usage examples** (`--dir /path/to/repo`) where `/path/to/X` is
  the idiomatic "substitute your real path here" convention — the same form
  `man` pages and `--help` output use. They are *deliberate instructional
  placeholders*, not *unfilled template tokens* (the E1 target is leftover
  scaffolding like `{Feature Name}` in a Feature doc's Impl Map).
- The **gold reference output does the exact same thing**:
  `~/rep_engineer_station/docs/rep-security/Troubleshooting.html` ships
  `path/to/access_config.properties` in its Troubleshooting CLI example.
- Neither the reference nor our output contains any true unfilled `{Name}` token
  (`grep -roE '\{[A-Z][a-z]+ ?[A-Za-z]*\}'` → 0 in the reference).

Verdict: **E1 = 2 (parity).** No action. Recorded here for auditability so the
decision bead (uiih) reflects that the revalidation looked hard and found nothing
shippable-blocking.

---

## 5. Residuals carried forward (non-blocking, already filed)

These are *not* rubric gaps in the regenerated output — they are pre-existing,
already-tracked items. None blocks shipping:

1. **`bdboard-irrn` formula-level residual (user family):** the realized `_docs/`
   is clean, but a fresh re-pour of the user formula could reintroduce a
   `path/to/` placeholder + editable `-e` install in the Installation page (fixed
   inline during w638). This is a *formula* tightening note, not an *output* gap.
2. **`bdboard-4iud` (deferred):** the `flowdoc-pour-gate` defect — `bd formula
   pour` spawns a disconnected generation epic that auto-closes on pour. The HTML
   build worked around it via the portable build contract (`tools/build_docs_site.py`).
3. **Windows activate line in `_docs/Getting-Started/Installation.md`** — POSIX
   `source .venv/bin/activate` only; non-rubric polish, outside scope.

---

## 6. Conclusion (feeds bdboard-uiih)

All three regenerated families score **Faithful (100%, all gates pass)** against
the rubric and at parity with the agent-loop reference. The fidelity gap the
milestone exists to close **is closed** in the output. The recommendation to the
decision bead (bdboard-uiih) is **SHIP** — do not run another tighten/regenerate
loop. The only carry-forward is the already-filed formula-level residual
(bdboard-irrn) and the deferred pour-gate defect (bdboard-4iud), neither of which
degrades the shipped output.
