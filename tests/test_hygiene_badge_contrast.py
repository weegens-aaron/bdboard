"""WCAG + non-color-reliance checks for the graph-hygiene badges (FB-6).

The cycle / dangling-edge / incomplete badges (bdboard-dzu2) are filled pill
chips. Two accessibility concerns are locked here:

1. WCAG 1.4.3: each badge's text must clear AA contrast (4.5:1) against its own
   fill in BOTH themes. The chips reuse the status tokens, but we assert the
   resolved bg/fg pairs directly so a future token re-point can't silently
   regress the badge.
2. WCAG 1.4.1: meaning is never carried by color alone — every badge in the
   shared partial renders a VISIBLE text label, not just a colored glyph.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import (
    dark_theme_variables,
    extract_style_property,
    parse_css_variables,
    resolve_css_value,
)
from wcag_utils import contrast_ratio

CSS_PATH = Path("src/bdboard/static/styles.css")
PARTIAL = Path("src/bdboard/templates/partials/bead_hygiene_badges.html")

AA_TEXT = 4.5  # WCAG 1.4.3 normal text

# badge css class -> the bg/fg property pair we resolve for contrast.
BADGES = ("badge-cycle", "badge-dangling", "badge-incomplete")

# Each badge's visible text label that MUST appear in the partial so meaning is
# not color-only (WCAG 1.4.1).
BADGE_LABELS = ("DEADLOCK", "DANGLING DEP", "INCOMPLETE")


def _pair(cls: str, variables: dict[str, str]) -> tuple[str, str]:
    css = CSS_PATH.read_text(encoding="utf-8")
    bg = resolve_css_value(
        extract_style_property(css, f".{cls}", "background", variables), variables
    )
    fg = resolve_css_value(extract_style_property(css, f".{cls}", "color", variables), variables)
    assert bg.startswith("#"), f"{cls} background did not resolve to hex: {bg!r}"
    assert fg.startswith("#"), f"{cls} color did not resolve to hex: {fg!r}"
    return bg, fg


def test_badge_text_contrast_light():
    light = parse_css_variables(CSS_PATH.read_text(encoding="utf-8"))
    failures = []
    for cls in BADGES:
        bg, fg = _pair(cls, light)
        ratio = contrast_ratio(fg, bg)
        if ratio < AA_TEXT:
            failures.append(f"{cls}: {ratio:.2f}:1 < {AA_TEXT}:1 ({fg} on {bg})")
    assert not failures, "Light theme badge contrast failures:\n" + "\n".join(failures)


def test_badge_text_contrast_dark():
    dark = dark_theme_variables(CSS_PATH.read_text(encoding="utf-8"))
    failures = []
    for cls in BADGES:
        bg, fg = _pair(cls, dark)
        ratio = contrast_ratio(fg, bg)
        if ratio < AA_TEXT:
            failures.append(f"{cls}: {ratio:.2f}:1 < {AA_TEXT}:1 ({fg} on {bg})")
    assert not failures, "Dark theme badge contrast failures:\n" + "\n".join(failures)


def test_every_badge_has_a_visible_text_label():
    """WCAG 1.4.1: each badge pairs its glyph with a visible text label."""
    markup = PARTIAL.read_text(encoding="utf-8")
    for label in BADGE_LABELS:
        assert label in markup, f"badge partial is missing visible label {label!r}"
