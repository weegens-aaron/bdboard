"""WCAG AA contrast tests for Closed lane filter badges.

bdboard-bcx acceptance criteria 5: Active/inactive states are visually
distinct, not color-alone, and pass WCAG 2.2 AA contrast.
"""

from pathlib import Path

from css_test_utils import extract_style_property, parse_css_variables
from wcag_utils import contrast_ratio


def _extract_filter_badge_colors(css_content: str) -> dict[str, tuple[str, str]]:
    """Extract foreground and background colors for filter badges.

    Returns: {state: (fg_color, bg_color)}
    """
    colors = {}
    variables = parse_css_variables(css_content)

    # Inactive badge - gray text on white background
    inactive_fg = extract_style_property(
        css_content, ".filter-badge", "color", variables
    )
    inactive_bg = extract_style_property(
        css_content, ".filter-badge", "background", variables
    )
    if inactive_fg and inactive_bg:
        colors["inactive"] = (inactive_fg, inactive_bg)

    # Active badge - white text on blue background
    active_fg = extract_style_property(
        css_content, ".filter-badge-active", "color", variables
    )
    active_bg = extract_style_property(
        css_content, ".filter-badge-active", "background", variables
    )
    if active_fg and active_bg:
        colors["active"] = (active_fg, active_bg)

    # Hover state - blue text on light blue background
    hover_fg = extract_style_property(
        css_content, ".filter-badge:hover", "color", variables
    )
    hover_bg = extract_style_property(
        css_content, ".filter-badge:hover", "background", variables
    )
    if hover_fg and hover_bg:
        colors["inactive_hover"] = (hover_fg, hover_bg)

    return colors


def test_filter_badge_inactive_meets_wcag_aa():
    """Inactive filter badge must meet WCAG AA 4.5:1 for small text."""
    css_path = Path(__file__).parent.parent / "src/bdboard/static/styles.css"
    css_content = css_path.read_text()
    colors = _extract_filter_badge_colors(css_content)

    assert "inactive" in colors, "Could not extract inactive badge colors from CSS"
    fg, bg = colors["inactive"]
    ratio = contrast_ratio(fg, bg)

    # WCAG AA requires 4.5:1 for normal text (font-size: 10px)
    assert ratio >= 4.5, (
        f"Inactive badge contrast {ratio:.2f}:1 fails WCAG AA (need 4.5:1). fg={fg} bg={bg}"
    )


def test_filter_badge_active_meets_wcag_aa():
    """Active filter badge must meet WCAG AA contrast (white on blue)."""
    css_path = Path(__file__).parent.parent / "src/bdboard/static/styles.css"
    css_content = css_path.read_text()
    colors = _extract_filter_badge_colors(css_content)

    assert "active" in colors, "Could not extract active badge colors from CSS"
    fg, bg = colors["active"]
    ratio = contrast_ratio(fg, bg)

    # WCAG AA requires 4.5:1 for normal text
    assert ratio >= 4.5, (
        f"Active badge contrast {ratio:.2f}:1 fails WCAG AA (need 4.5:1). fg={fg} bg={bg}"
    )


def test_filter_badge_hover_meets_wcag_aa():
    """Hover state must meet WCAG AA contrast."""
    css_path = Path(__file__).parent.parent / "src/bdboard/static/styles.css"
    css_content = css_path.read_text()
    colors = _extract_filter_badge_colors(css_content)

    assert "inactive_hover" in colors, (
        "Could not extract inactive hover badge colors from CSS"
    )
    fg, bg = colors["inactive_hover"]
    ratio = contrast_ratio(fg, bg)

    # WCAG AA requires 4.5:1 for normal text
    assert ratio >= 4.5, (
        f"Inactive hover badge contrast {ratio:.2f}:1 fails WCAG AA (need 4.5:1). fg={fg} bg={bg}"
    )


def test_filter_badges_have_visual_weight_difference():
    """Active and inactive badges must differ in more than just color.

    Per acceptance criteria: "not color-only; include visual weight change
    or border so it works with color-blind viewing."
    """
    css_path = Path(__file__).parent.parent / "src/bdboard/static/styles.css"
    css_content = css_path.read_text()
    variables = parse_css_variables(css_content)

    # Active badge should have stronger font-weight
    active_font_weight = extract_style_property(
        css_content, ".filter-badge-active", "font-weight", variables
    )
    inactive_font_weight = extract_style_property(
        css_content, ".filter-badge", "font-weight", variables
    )

    assert active_font_weight and inactive_font_weight, (
        "Could not extract font-weight from CSS"
    )

    active_weight = int(active_font_weight)
    inactive_weight = int(inactive_font_weight)

    assert active_weight > inactive_weight, (
        f"Active badge font-weight ({active_weight}) must be heavier than inactive ({inactive_weight})"
    )

    # Active badge should have box-shadow for additional visual weight
    active_shadow = extract_style_property(
        css_content, ".filter-badge-active", "box-shadow", variables
    )
    assert active_shadow, (
        "Active badge must have box-shadow for non-color visual distinction"
    )
