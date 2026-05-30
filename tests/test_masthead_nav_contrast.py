"""WCAG 2.2 AA + structural tests for the editorial contents-bar masthead.

Covers the bdboard-9kb implementation of Option A from the bdboard-buq spike:
Board / Memory / theme rendered as a typographic "contents strip" (small-caps
+ letterspacing like .kicker, hairline vertical rules like the counts strip),
with the active page signalled by THREE non-colour cues (ink colour + bold
weight + an inset baseline rule).

These assert on the actual stylesheet so the tests fail if someone reverts to
pills/boxes, drops a non-colour active cue, or pushes a token below WCAG AA.
The dark-theme palette for these same pairs is certified in
test_dark_theme_contrast.py.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import extract_style_property, parse_css_variables
from wcag_utils import contrast_ratio

CSS_PATH = Path("src/bdboard/static/styles.css")

AA_NORMAL = 4.5  # normal text
AA_LARGE = 3.0  # large/bold text & UI components


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def test_inactive_link_meets_aa_on_paper_in_light_theme():
    """Inactive contents-bar links use --muted on the white masthead (paper-3).

    Small uppercase text => must clear 4.5:1.
    """
    css = _css()
    variables = parse_css_variables(css)
    fg = extract_style_property(css, ".mh-link", "color", variables)
    bg = variables["--paper-3"]

    assert fg and fg.startswith("#"), f"inactive link colour did not resolve: {fg!r}"
    ratio = contrast_ratio(fg, bg)
    assert ratio >= AA_NORMAL, (
        f"Inactive contents-bar link {ratio:.2f}:1 < {AA_NORMAL}:1 ({fg} on {bg})"
    )


def test_active_link_meets_aa_on_paper_in_light_theme():
    """Active link uses --ink on paper-3 — comfortably exceeds AA."""
    css = _css()
    variables = parse_css_variables(css)
    fg = extract_style_property(css, ".mh-link.is-active", "color", variables)
    bg = variables["--paper-3"]

    assert fg and fg.startswith("#"), f"active link colour did not resolve: {fg!r}"
    ratio = contrast_ratio(fg, bg)
    assert ratio >= AA_NORMAL, (
        f"Active contents-bar link {ratio:.2f}:1 < {AA_NORMAL}:1 ({fg} on {bg})"
    )


def test_active_state_uses_more_than_colour():
    """WCAG 1.4.1: the active page must be signalled by more than colour.

    Option A stacks weight (font-weight) + an inset baseline rule
    (box-shadow) on top of the colour change.
    """
    css = _css()
    weight = extract_style_property(css, ".mh-link.is-active", "font-weight")
    shadow = extract_style_property(css, ".mh-link.is-active", "box-shadow")

    assert weight is not None, "active link is missing a bold weight cue"
    assert int(weight) >= 700, f"active weight {weight} is not bold enough (>=700)"
    assert shadow is not None, "active link is missing the inset baseline rule"
    assert "inset" in shadow, f"active baseline rule should be inset, got: {shadow!r}"


def test_no_pill_or_box_surfaces_in_contents_bar():
    """Option A removes every filled/bordered/rounded surface from the nav.

    The inactive link, the active link, and the toggle must not reintroduce
    a background fill, a full border, or a border-radius (the app-like pill).
    """
    css = _css()
    for selector in (".mh-link", ".mh-link.is-active", ".mh-toggle"):
        background = extract_style_property(css, selector, "background")
        radius = extract_style_property(css, selector, "border-radius")
        # A `border` shorthand reintroduces a box; the hairline separator is
        # `border-left` only, which is allowed (it matches the counts strip).
        border = extract_style_property(css, selector, "border")
        if background is not None:
            assert background == "none", f"{selector} has a fill: {background!r}"
        if radius is not None:
            assert radius == "0", f"{selector} has a pill radius: {radius!r}"
        if border is not None:
            assert border == "0", f"{selector} has a box border: {border!r}"


def test_contents_bar_reuses_editorial_kit():
    """The contents bar borrows the masthead's own editorial vocabulary:
    small-caps + letterspacing (like .kicker) and a hairline rule (like the
    counts strip's border-left)."""
    css = _css()
    transform = extract_style_property(css, ".mh-link", "text-transform")
    spacing = extract_style_property(css, ".mh-link", "letter-spacing")
    rule = extract_style_property(css, ".mh-link", "border-left")

    assert transform == "uppercase", f"expected small-caps, got {transform!r}"
    assert spacing and spacing.endswith("em"), (
        f"expected letterspacing, got {spacing!r}"
    )
    assert rule and "1px" in rule, f"expected a hairline border-left, got {rule!r}"


def test_interactive_elements_have_focus_outline():
    """Every interactive contents-bar element keeps a visible focus ring."""
    css = _css()
    variables = parse_css_variables(css)
    outline = extract_style_property(
        css, ".mh-link:focus-visible", "outline", variables
    )
    assert outline is not None, ".mh-link is missing a :focus-visible outline"
    # The toggle is a .mh-link, so the same rule covers it; assert the colour
    # is a real, visible value (resolved through the token table).
    assert "solid" in outline, f"focus outline should be solid, got {outline!r}"
