"""WCAG 2.2 AA contrast verification for Activity filter badges.

Per bdboard-36v spec: active/inactive badge states must be visually distinct
(not color-only) and meet WCAG 2.2 AA contrast requirements (4.5:1 for small
text, 3:1 for large text / UI components).

Activity badges share the same .filter-badge styles as Closed badges, so they
inherit the same WCAG AA compliance. These tests verify that the shared styles
remain compliant.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import extract_style_property, parse_css_variables
from wcag_utils import contrast_ratio, hex_to_rgb


def _get_css_content() -> str:
    """Load styles.css content."""
    css_path = Path(__file__).parent.parent / "src/bdboard/static/styles.css"
    return css_path.read_text()


def _get_color_value(css: str, selector: str, prop: str) -> tuple[int, int, int] | None:
    """Get a resolved RGB color value from a CSS selector property."""
    variables = parse_css_variables(css)
    val = extract_style_property(css, selector, prop, variables)
    if not val:
        return None
    try:
        return hex_to_rgb(val)
    except ValueError:
        return None


def test_filter_badge_inactive_meets_wcag_aa():
    """Inactive badge must meet WCAG AA contrast (4.5:1 for small text)."""
    css = _get_css_content()
    fg = _get_color_value(css, ".filter-badge", "color")
    bg = _get_color_value(css, ".filter-badge", "background")
    assert fg is not None, "Could not parse .filter-badge color"
    assert bg is not None, "Could not parse .filter-badge background"
    # Convert RGB tuples to hex for contrast_ratio
    fg_hex = "#" + "".join(f"{c:02x}" for c in fg)
    bg_hex = "#" + "".join(f"{c:02x}" for c in bg)
    ratio = contrast_ratio(fg_hex, bg_hex)
    # WCAG AA requires 4.5:1 for small text
    assert ratio >= 4.5, f"Inactive badge contrast {ratio:.2f}:1 fails WCAG AA (4.5:1)"


def test_filter_badge_active_meets_wcag_aa():
    """Active badge must meet WCAG AA contrast (4.5:1 for small text)."""
    css = _get_css_content()
    fg = _get_color_value(css, ".filter-badge-active", "color")
    bg = _get_color_value(css, ".filter-badge-active", "background")
    assert fg is not None, "Could not parse .filter-badge-active color"
    assert bg is not None, "Could not parse .filter-badge-active background"
    # Convert RGB tuples to hex for contrast_ratio
    fg_hex = "#" + "".join(f"{c:02x}" for c in fg)
    bg_hex = "#" + "".join(f"{c:02x}" for c in bg)
    ratio = contrast_ratio(fg_hex, bg_hex)
    # WCAG AA requires 4.5:1 for small text
    assert ratio >= 4.5, f"Active badge contrast {ratio:.2f}:1 fails WCAG AA (4.5:1)"


def test_filter_badge_hover_meets_wcag_aa():
    """Hover badge must meet WCAG AA contrast (4.5:1 for small text)."""
    css = _get_css_content()
    fg = _get_color_value(css, ".filter-badge:hover", "color")
    bg = _get_color_value(css, ".filter-badge:hover", "background")
    assert fg is not None, "Could not parse .filter-badge:hover color"
    assert bg is not None, "Could not parse .filter-badge:hover background"
    # Convert RGB tuples to hex for contrast_ratio
    fg_hex = "#" + "".join(f"{c:02x}" for c in fg)
    bg_hex = "#" + "".join(f"{c:02x}" for c in bg)
    ratio = contrast_ratio(fg_hex, bg_hex)
    # WCAG AA requires 4.5:1 for small text
    assert ratio >= 4.5, f"Hover badge contrast {ratio:.2f}:1 fails WCAG AA (4.5:1)"


def test_filter_badges_have_visual_weight_difference():
    """Active and inactive badges must differ in visual weight, not just color.

    WCAG 2.2 requires non-color distinguishability. We verify that the active
    badge has heavier font-weight AND a box-shadow, so the difference is
    perceivable even in grayscale or for color-blind users.
    """
    css = _get_css_content()
    variables = parse_css_variables(css)
    inactive_weight = extract_style_property(css, ".filter-badge", "font-weight", variables)
    active_weight = extract_style_property(css, ".filter-badge-active", "font-weight", variables)
    assert inactive_weight is not None, "Could not find .filter-badge font-weight"
    assert active_weight is not None, "Could not find .filter-badge-active font-weight"
    # Active should be heavier (700 -> 800)
    assert int(active_weight) > int(inactive_weight), "Active badge must have heavier font-weight"
    # Active should also have a box-shadow for additional visual weight
    shadow = extract_style_property(css, ".filter-badge-active", "box-shadow", variables)
    assert shadow is not None, "Active badge must have box-shadow"
    assert "inset" in shadow, "Active badge box-shadow should be inset"
