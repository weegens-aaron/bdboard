# Design spike: more editorial masthead chrome

- **Bead:** bdboard-buq (spike)
- **Type:** design / exploration only — **no implementation in this bead**
- **Date:** 2026-05-30
- **Affected code (for the follow-up, not this bead):**
  `src/bdboard/templates/partials/nav.html` and the `.masthead*` /
  `.theme-toggle` rules in `src/bdboard/static/styles.css`.

> This document is the deliverable for bdboard-buq. It sketches 2–3 concrete
> masthead treatments, evaluates each against the editorial/serif aesthetic
> and against accessibility, recommends a direction, and points at the filed
> follow-up implementation bead. It deliberately ships **no** runtime CSS.

---

## 1. Problem

The masthead pairs a genuinely editorial serif wordmark (`bdboard`, in
`--display`) with chrome that reads like a web app:

| Element | Today | Why it fights the aesthetic |
| --- | --- | --- |
| Board nav | boxed blue **pill** (`.masthead-nav-link.is-active` with `background`, `border`, `border-radius`) | A filled pill button is app UI, not masthead. |
| Memory nav | plain padded link | Reads as a button-in-waiting, not a contents entry. |
| Theme toggle | rounded **pill** `☀ Light` / `☽ Dark` with border + bg | A bordered pill is the most "app" thing in the header. |

Reference: `notes/bugs/bdboard-buq/current-header.png`.

### 1.1 The vocabulary is already in the header

Crucially, two neighbours in the *same* masthead already nail the editorial
voice, so we are matching existing precedent, not inventing one:

- **The kicker** (`.kicker`): uppercase, `letter-spacing: 0.12em`, 11px,
  `--sans` — small-caps masthead label.
- **The counts strip** (`.counts-*`): uppercase letterspaced labels +
  serif/display numerals, separated by **hairline vertical rules**
  (`border-left: 1px solid var(--rule)`).

The fix is to make Board / Memory / theme read from that same kit
(small-caps + letterspacing, hairline separators, underline-as-rule) instead
of pills and filled backgrounds.

---

## 2. Hard constraints (must survive any option)

These come from the existing markup and the bdboard-35e work; the redesign
is **visual only** and must not regress them:

1. **Nav is real navigation.** Board/Memory stay inside `<nav aria-label="Primary">`
   as `<a href>`; the current page keeps `aria-current="page"`.
2. **Theme toggle is an action**, not a link. It stays a `<button type="button">`
   with `aria-pressed` maintained in JS, and stays **outside** `<nav>`.
3. **Active page signalled by more than colour.** WCAG 1.4.1 — today the
   active link adds an underline rule on top of colour; any option must keep
   a non-colour cue (weight, underline rule, or a leading marker).
4. **Visible focus** on every interactive element (`:focus-visible` outline),
   AA contrast (4.5:1 text, 3:1 UI) in **both** themes — reuse the vetted
   tokens; no new raw hex (the styles.css "no hex outside :root" rule).
5. **DRY:** the partial is shared by `dashboard.html` and `memory.html`; the
   toggle's label-swap stays CSS-driven off `<html data-theme>` (JS flips one
   attribute — the single source of truth from bdboard-35e).
6. **The toggle label is the action** (shows the theme you'll switch *to*) and
   keeps an `aria-label` so it's understandable without the visual glyph.

---

## 3. Options

Each option shows the intended *markup shape* and an *illustrative* CSS
sketch. *Illustrative only — none of this is applied to `styles.css` in this
bead.*

### Option A — "Contents bar": small-caps text links + hairline rules

Treat Board / Memory / theme as a single typographic **contents strip**,
echoing the counts strip. No fills, no pill borders. Items are small-caps,
letterspaced, separated by the same hairline vertical rule used between
counts. Active page = ink colour + a thin underline *rule* (a baseline rule,
like a section underline), inactive = muted. Theme toggle is the last cell in
the same strip, visually identical to a nav item but semantically a button.

```html
<!-- nav.html (shape only) -->
<nav class="masthead-nav" aria-label="Primary">
  <a href="/"        class="mh-link is-active" aria-current="page">Board</a>
  <a href="/memory"  class="mh-link">Memory</a>
</nav>
<button type="button" id="theme-toggle" class="mh-link mh-toggle"
        aria-pressed="false" aria-label="Toggle dark mode">
  <span class="theme-toggle-to-dark"  aria-hidden="true">Dark</span>
  <span class="theme-toggle-to-light" aria-hidden="true">Light</span>
</button>
```

```css
/* illustrative */
.mh-link {
  font-family: var(--sans);
  text-transform: uppercase;
  letter-spacing: 0.10em;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);                 /* inactive: de-emphasised */
  background: none; border: 0; border-radius: 0;
  padding: 2px 14px;                    /* room for the hairline rule */
  border-left: 1px solid var(--rule);  /* same separator as .counts-cell */
  cursor: pointer;
}
.masthead-nav .mh-link:first-child { border-left: 0; }
.mh-link:hover { color: var(--ink); }
.mh-link.is-active {                    /* >colour: weight + baseline rule */
  color: var(--ink);
  box-shadow: inset 0 -2px 0 var(--brand-blue);  /* thin underline rule */
}
.mh-link:focus-visible { outline: 2px solid var(--brand-blue); outline-offset: 2px; }
```

- **Editorial fit:** ★★★★★ — reads as a masthead contents bar; matches the
  counts strip exactly; zero "app" surfaces.
- **Accessibility:** active state = colour **+** weight **+** baseline rule
  (3 cues); focus ring preserved; `aria-current` / `aria-pressed` unchanged.
  Caveat: 11px uppercase is small — keep ≥11px and ≥4.5:1 (`--muted` on
  `--paper-3` is 6.36:1 dark / ~4.7:1 light, both pass).
- **Risk:** the toggle borrows `.mh-link` styling so it *looks* like a nav
  item; mitigated by `aria-pressed` + `aria-label` and the to-dark/to-light
  label swap. Hairline `border-left` on the toggle visually ties it to the
  nav even though it's a separate element — acceptable (the counts strip
  already groups heterogeneous cells with the same rule).

### Option B — "Slash dateline": inline serif links, slash-separated

A single serif line in the masthead voice: `Board / Memory` rendered in
`--serif` (matching the wordmark), separator a typographic slash, active item
in ink, inactive muted. Theme toggle becomes a trailing serif word with a
leading hairline rule: `… / Memory   ·   Light`. Closer to a newspaper
section dateline than a contents bar.

```html
<nav class="masthead-nav" aria-label="Primary">
  <a href="/" class="mh-serif is-active" aria-current="page">Board</a>
  <span class="mh-sep" aria-hidden="true">/</span>
  <a href="/memory" class="mh-serif">Memory</a>
</nav>
<button type="button" id="theme-toggle" class="mh-serif mh-toggle" …>…</button>
```

```css
.mh-serif {
  font-family: var(--serif);
  font-size: 16px;
  color: var(--muted);
  text-decoration: none;
  background: none; border: 0;
}
.mh-serif.is-active {
  color: var(--ink);
  font-style: italic;                 /* non-colour cue: italic + rule */
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 4px;
}
.mh-sep { color: var(--rule-2); font-family: var(--serif); }
```

- **Editorial fit:** ★★★★☆ — very magazine, ties to the serif wordmark; the
  slash is a strong editorial signal.
- **Accessibility:** active cue can't be *italic alone* (italic isn't a
  reliable non-colour cue for low-vision users), so it must also keep the
  underline rule — which works. Slash separators must be `aria-hidden` so SR
  users don't hear "Board slash Memory."
- **Risk:** serif links at 16px look like body copy / clickable prose; the
  affordance that these are nav is weaker than Option A. Two competing serif
  sizes (wordmark 38px vs nav 16px) can feel like a sub-headline rather than
  chrome. Slightly more fiddly to keep AA on the muted inactive state at
  serif weights.

### Option C — minimal-diff "de-chrome": keep current structure, drop the boxes

Lowest-risk: keep the existing `.masthead-nav-link` / `.theme-toggle`
elements and markup exactly, but strip the pill/box treatment — remove
`background`, `border`, `border-radius` from the active link and the toggle;
keep the small-caps-ish sans at current size; signal active with weight +
the existing underline rule; render the toggle as a borderless text affordance
with a leading hairline `·` separator.

```css
.masthead-nav-link { background: none; border: 0; border-radius: 0; padding: 4px 8px; }
.masthead-nav-link.is-active {
  background: none; border: 0;
  color: var(--ink); font-weight: 800;
  text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px;
}
.theme-toggle {
  background: none; border: 0; border-radius: 0; padding: 4px 8px;
  color: var(--muted);
}
.theme-toggle::before { content: "·"; color: var(--rule-2); margin-right: 8px; }
.theme-toggle:hover { color: var(--ink); background: none; }
```

- **Editorial fit:** ★★★☆☆ — removes the worst offenders (the boxes) with
  minimal churn, but the result is "plain links" rather than a designed
  contents bar; it doesn't *add* editorial character, just subtracts app-ness.
- **Accessibility:** trivially preserves all current semantics and the
  underline-rule active cue; lowest regression risk of the three.
- **Risk:** lowest implementation risk, lowest design payoff. Good fallback if
  the follow-up wants a conservative first step.

---

## 4. Comparison

| Criterion | A: Contents bar | B: Slash dateline | C: De-chrome |
| --- | --- | --- | --- |
| Editorial feel | ★★★★★ | ★★★★☆ | ★★★☆☆ |
| Matches existing header kit | ★★★★★ (counts strip) | ★★★☆☆ (new serif size) | ★★★☆☆ |
| Nav affordance clarity | ★★★★☆ | ★★★☆☆ | ★★★★☆ |
| A11y (non-colour active, focus) | ★★★★★ | ★★★★☆ | ★★★★★ |
| Implementation risk | ★★★☆☆ | ★★☆☆☆ | ★★★★★ (lowest) |
| Net | **Recommended** | Strong alt | Safe fallback |

---

## 5. Recommendation

**Adopt Option A ("Contents bar"), with Option C as the conservative
fallback if review wants a smaller first step.**

Rationale:

- It reuses the masthead's **own** established editorial vocabulary — the
  small-caps letterspacing of `.kicker` and the **hairline vertical rules**
  of the counts strip — so the header reads as one coherent magazine
  masthead instead of "wordmark + app chrome." This is the strongest "matches
  existing precedent" story.
- It removes every filled/bordered surface (the bead's core complaint)
  without weakening affordance the way Option B's serif-as-prose does.
- The active state stacks **three** non-colour cues (ink colour + bold weight
  + inset baseline rule), comfortably satisfying WCAG 1.4.1 and beating
  today's single underline.
- It keeps the exact semantic shape from bdboard-35e: `<nav>` + `aria-current`
  for the links, `<button aria-pressed>` outside `<nav>` for the toggle,
  CSS-driven to-dark/to-light label swap. The change is class names + visual
  rules, not behaviour — low blast radius.

Borrow from B only the idea of *optionally* setting the nav in `--serif` if,
in review, the small-caps sans feels too utilitarian; that's a one-line
`font-family` swap the implementer can A/B.

### 5.1 Open questions for the implementer (decide during the follow-up)

- **Toggle separator:** hairline `border-left` (Option A) vs a `·` glyph
  (Option C). Prefer the hairline to match the counts strip exactly.
- **Nav typeface:** small-caps `--sans` (A, default) vs `--serif` (B flavour).
  Default to `--sans`; spike both in a branch and eyeball in both themes.
- **Hover affordance:** colour shift only (muted→ink) vs colour + underline
  on hover. Keep it colour-only to avoid double-signalling with the active
  baseline rule.

---

## 6. Acceptance-criteria mapping (this spike)

| Bead acceptance criterion | Satisfied by |
| --- | --- |
| 2–3 concrete header treatments | §3 Options A, B, C |
| Each evaluated vs editorial aesthetic **and** a11y | §3 per-option + §4 table |
| Recommended direction + rationale | §5 (Option A; recorded in bead notes) |
| Follow-up implementation bead filed (discovered-from) | §7 / bead notes |
| No regression to nav semantics / toggle behaviour | §2 constraints, carried into the follow-up's acceptance criteria |

---

## 7. Follow-up implementation bead

A `feature` bead implements Option A (with C as fallback), wired
**`discovered-from`** this spike (the spike isn't blocked by it). Its
acceptance criteria carry the §2 constraints forward verbatim:

- Replace pill/box treatment in `nav.html` + `.masthead*` / `.theme-toggle`
  with the Option A contents-bar styling (hairline rules, small-caps,
  baseline-rule active state).
- Preserve `<nav>`/`aria-current` for links and `<button>`/`aria-pressed`
  outside `<nav>` for the toggle; keep the CSS-driven label swap.
- AA contrast in both light and dark; no raw hex outside `:root`; visible
  `:focus-visible` on every interactive element.
- Update/extend any masthead contrast tests; `ruff`-clean.

See the bead's `discovered-from` edge for the filed ID.

---

## 8. Out of scope for this bead

- Any runtime CSS / template changes (this is a spike).
- Counts strip and wordmark restyling (they already read editorially).
- Footer chrome.
