# FlowDoc "Consistent and Explicit" Rubric + Scoring Method

> **Bead:** bdboard-pf4f (spike) | **Epic:** bdboard-6ucx | **Consumed by:** bdboard-70o2
> (score formula test-run output vs agent reference) and the tighten beads
> bdboard-8hbe / bdboard-irrn / bdboard-bmji.
>
> **Sources studied:** the three loop agents
> `~/rep_engineer_station/.code_puppy/agents/flowdoc.json` (maintainer-docs generator),
> `flowdoc-maintainer.json` (drift auditor), `flowdoc-user.json` (end-user docs),
> plus the realized HTML reference output under `~/rep_engineer_station/docs/<service>/`
> (e.g. `rep-order-service/`). The agent prompts are the *spec*; the rendered docs
> are the *gold output*. This rubric distills what makes them reliable so two
> outputs can be compared objectively.

In the Gate column below, `Y` = pass/fail must-have, `-` = scored but not a gate.

---

## 0. Scope: three output families

The compare task scores **three distinct artifacts**, each judged against its own
reference. A dimension only applies to a family if the "Applies" column lists it.

| Family | Output dir | Reference agent | What it is |
|--------|-----------|-----------------|------------|
| **M** - Maintainer docs (markdown) | `__docs/` (double underscore) | `flowdoc` | Feature/flow/endpoint/concept docs for developers, with impl maps + mermaid |
| **U** - User docs (markdown) | `_docs/` (single underscore) | `flowdoc-user` | Diataxis end-user docs; NO source paths, NO internal URLs |
| **H** - Rendered site (HTML) | `docs/` (`index.html` + per-section dirs + `style.css`) | the md->html build (md-to-html skill) | Static site built from M (and/or U) markdown |

> **Naming trap (carry this into scoring):** maintainer = `__docs/`,
> user = `_docs/`. Mixing them is an automatic structure miss.

---

## 1. The rubric - dimensions of "consistent and explicit"

Each dimension has an ID, the families it applies to, a **weight** (1 = normal,
2 = critical structural), and a **gate** flag. **Gate dimensions are pass/fail
must-haves:** scoring 0 on any gate dimension fails the whole artifact regardless
of the weighted total (you can ship a beautiful doc set that is worthless if every
link is broken or every template token is left unfilled).

### Structure and filesystem

| ID | Dimension | Applies | Weight | Gate | What "2 = full" looks like |
|----|-----------|---------|--------|------|----------------------------|
| **S1** | Correct output directory | M, U, H | 2 | Y | M in `__docs/`, U in `_docs/`, H in `docs/` with `index.html` at root. Wrong/duplicated root = 0. |
| **S2** | Required top-level files present | M, U, H | 2 | Y | M: `index.md`, `Architecture.md`, `_Manifest.md`, `Troubleshooting.md`. U: `index.md`, `Overview.md`, `_Manifest.md`, `FAQ.md`. H: `index.html`, `style.css`, `Architecture.html`/`Troubleshooting.html` (mirrors source md). |
| **S3** | Required section subdirs + per-section index | M, U, H | 2 | - | M: `Features/`, `Flows/`, `Concepts/`, plus `Endpoints/` (backend) and/or `Views/` (frontend), each with an index. U: `Getting-Started/`, `Guides/`, `Tutorials/`, `Reference/`, `Concepts/`, each with an index. H mirrors whichever source it built from. Missing index per section = partial (1). |
| **S4** | One item per file, no orphans | M, U, H | 1 | - | Every manifest entry has exactly one backing file; no files exist that are not in the manifest (except Troubleshooting/FAQ). |

### Manifest schema

| ID | Dimension | Applies | Weight | Gate | What "2 = full" looks like |
|----|-----------|---------|--------|------|----------------------------|
| **MF1** | Progress block | M, U | 1 | - | `## Progress` with **Total / Completed / Remaining** counters that reconcile with checkbox counts. |
| **MF2** | Grouped sections | M, U | 1 | - | M: Features / Flows / API Endpoints / Views / Concepts, sub-grouped by domain. U: Getting Started / Guides / Tutorials / Reference / Concepts, sub-grouped by capability. |
| **MF3** | Stable item ID numbering | M, U | 1 | - | Numeric prefixes per band (M: 001 features, 010/020/030 flows, 050+ endpoints, 060/070 views, 080+ concepts; U: 001 getting-started, 010+ guides, 040+ tutorials, 060/070/080 reference, 090+ concepts). Maintainer drift queue uses **letter prefixes** U/N/R/M/V - preserve those if auditing. |
| **MF4** | Checkbox + arrow-link line format | M, U | 2 | Y | Each item is `- [ ] NNN \| Type: Name -> [LinkText](Path)` and every link target resolves to a real file. Completed runs show `- [x]`. |

### Required sections per doc type (template completeness)

| ID | Dimension | Applies | Weight | Gate | What "2 = full" looks like |
|----|-----------|---------|--------|------|----------------------------|
| **T1** | Architecture / Overview completeness | M, U | 2 | - | M `Architecture.md`: What Is This, Quick Start, Tech Stack table, System Diagram (mermaid), Features-at-a-Glance, Key Flows, External Deps, Directory Guide, API Surface (if backend), Views (if frontend). U `Overview.md`: What Is It, Key Features, Requirements (user-only), Getting Started (access/install), Next Steps. |
| **T2** | Per-item template sections filled | M, U | 2 | - | M Feature: What/Why/How (user+system)/Impl Map/Config/Edge Cases/Errors/Testing/Related. M Flow: What/Trigger/Outcome/Step-by-Step/Data Transforms/Failure Handling/Perf/Debugging/Related. M Endpoint, View, Concept: their full template. U Guide/Tutorial/Reference/Concept: their Diataxis template. A doc missing >1 required section scores 1; missing the spine (How-It-Works / Steps) scores 0. |
| **T3** | Troubleshooting / FAQ finalized | M, U | 1 | - | M `Troubleshooting.md`: Quick Diagnostics, Common Issues, "Where to Look When...", Emergency Procedures. U `FAQ.md`: grouped Q&A with links. Not left as an empty stub. |

### Explicitness (the "no hand-waving" dimensions)

| ID | Dimension | Applies | Weight | Gate | What "2 = full" looks like |
|----|-----------|---------|--------|------|----------------------------|
| **E1** | No unfilled template tokens | M, U, H | 2 | Y | Zero literal `{placeholder}`, `{Feature Name}`, `path/to/file`, `N` counters, or `...` left in shipped output. Any leftover token is the number-one explicitness failure. |
| **E2** | Concrete implementation maps | M, H | 2 | - | Every M Impl Map / "Where" field names a **real file path** in the repo, not a generic placeholder. Spot-check at least 3 paths exist. |
| **E3** | Audience purity (user docs) | U, H | 2 | Y | U docs expose **no** source file paths, class/function names, dev-setup (clone/build/test), or internal/stage URLs - only production access + user-facing language, second person, active voice. Any leaked `src/...`, `npm install`, localhost/stage URL = 0. |
| **E4** | Diagrams present where templated | M, U, H | 1 | - | Mermaid blocks present where the template calls for them (system diagram, sequence per feature/endpoint, flowchart per flow). H: mermaid actually renders (not raw fenced text). |
| **E5** | Callouts | M, U, H | 1 | - | `> [!WARNING] / [!NOTE] / [!TIP] / [!CAUTION] / [!IMPORTANT]` used for gotchas/edge cases; in H they render as styled boxes (see `style.css` callout vars). |

### Naming and cross-links

| ID | Dimension | Applies | Weight | Gate | What "2 = full" looks like |
|----|-----------|---------|--------|------|----------------------------|
| **N1** | PascalCase item filenames | M, U, H | 1 | - | Files are `OrderEnrichment.md` / `.html`, not `order_enrichment` or `order-enrichment`; section dirs PascalCase (`Features/`, `Getting-Started/`). |
| **N2** | Manifest link vs file parity | M, U | 2 | Y | Every manifest arrow-link path matches an existing file exactly (case-sensitive). |
| **L1** | Cross-link integrity | M, U, H | 2 | Y | All inline `[text](path)` and "Related/See Also" links resolve to existing docs. H: relative hrefs resolve within the site, sidebar nav links all 200. Any broken link = 0. |
| **L2** | Bidirectional "Related" links | M, U | 1 | - | Items reference related items both ways where the template has a Related/See-Also section. |

### HTML-render fidelity (H only)

| ID | Dimension | Applies | Weight | Gate | What "2 = full" looks like |
|----|-----------|---------|--------|------|----------------------------|
| **H1** | Persistent sidebar nav | H | 2 | - | `<aside class="sidebar">` with grouped `nav-section` headers (Overview / Concepts / Endpoints / Features / Flows ...) and a link per page, active state on current. |
| **H2** | Source-to-output parity | H | 2 | Y | Every source `.md` produced exactly one `.html`; no markdown left unconverted, no extra pages invented. |
| **H3** | Styling + code highlighting | H | 1 | - | `style.css` linked, callout color theme present, code blocks highlighted (highlight.js), responsive viewport meta. |
| **H4** | No internal-process file leakage | H | 1 | - | Build does not publish `_Manifest`/`_UpdateQueue` as user-facing pages. (`_AuditLog.html` is a per-build decision - the reference *does* ship it; flag mismatch, do not auto-fail.) |

### Tone / loop hygiene (cross-cutting)

| ID | Dimension | Applies | Weight | Gate | What "2 = full" looks like |
|----|-----------|---------|--------|------|----------------------------|
| **C1** | "Features/flows, not files" framing | M | 1 | - | Docs answer "how does X work?" not "what is in X.java?"; behavior-first, file-second. |
| **C2** | Consistent voice | M, U | 1 | - | M: maintainer-explanatory. U: second-person, active, "show don't tell" with expected output after every command. |

---

## 2. Scoring method

### Per-dimension score (0 / 1 / 2)

For each applicable dimension, score the artifact against the **reference** output:

| Score | Meaning |
|-------|---------|
| **2** | Matches reference quality - dimension fully satisfied. |
| **1** | Partial - present but incomplete, inconsistent, or thinner than reference. |
| **0** | Absent or broken. |

### Two gates -> pass/fail before any math

An artifact **FAILS outright** (do not bother with the percentage) if **either**:

1. **Any Gate=Y dimension scores 0**, or
2. **Weighted score < 70%** of its applicable maximum.

Gate dimensions encode the non-negotiables: right output dir (S1), required files
(S2), manifest line format + link parity (MF4, N2), resolving links (L1), no
leftover template tokens (E1), audience purity for user docs (E3), and HTML
source-to-output parity (H2). A doc set that violates one of these is not "lower
quality" - it is broken, and the percentage would lie about it.

### Weighted percentage

```
weighted_score   = sum( dimension_score * weight )   over applicable dims
weighted_maximum = sum( 2 * weight )                 over applicable dims
fidelity_pct     = round( 100 * weighted_score / weighted_maximum )
```

Suggested bands (after gates pass):

| Band | fidelity_pct | Verdict |
|------|--------------|---------|
| Faithful | >= 90 | Matches the agent reference; no tightening needed for this family. |
| Close | 75-89 | Minor deltas; log targeted fixes for the tighten bead. |
| Drifting | 70-74 | Material gaps; tighten bead is justified. |
| Fail | < 70 OR any gate=0 | Output is not usable as-is. |

### Comparing two outputs (the actual compare task, bdboard-70o2)

For each family (M, U, H), fill one **scorecard** per output (reference and
candidate), then diff:

```
| Dim | Weight | Gate | Reference | Candidate | Delta (cand-ref) | Note / gap |
|-----|--------|------|-----------|-----------|------------------|------------|
| S1  | 2      | Y    | 2         | 2         | 0                | ok         |
| ... | ...    | ...  | ...       | ...       | ...              | ...        |
| TOTAL (fidelity_pct)      | 100%  | 82%   | -18 pts          |            |
```

- **Delta < 0** on any row = a concrete, actionable gap, feeding the matching
  tighten bead (8hbe maintainer / irrn user / bmji html). Route by the dimension's
  family.
- The reference is expected to score 100%; the candidate's distance from it *is*
  the gap list. Sort gaps by `abs(Delta) * weight` descending so the tighten beads
  attack the highest-leverage fixes first.
- Gate failures are reported separately and explicitly (not buried in the
  percentage) so reviewers see "broken" vs "thin" at a glance.

### Repeatability notes

- **Same reference service for every run.** Pin one reference (e.g.
  `rep-order-service`) so scores are comparable across iterations.
- **Spot-check sampling for E2/L1 at scale:** when a family has dozens of pages,
  check the top-level files + a random sample of at least 5 item pages rather than
  all; record which were sampled so the run is reproducible.
- **Score the same way twice = same number.** Every dimension is a yes/partial/no
  observation, not a vibe - two reviewers (or two LLM judges) should land within
  one point per dimension.
