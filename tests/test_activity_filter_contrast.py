"""WCAG 2.2 AA contrast verification for Activity filter badges.

Per bdboard-36v spec: active/inactive badge states must be visually distinct
(not color-only) and meet WCAG 2.2 AA contrast requirements (4.5:1 for small
text, 3:1 for large text / UI components).

Activity badges share the same .filter-badge styles as Closed badges, so they
inherit the same WCAG AA compliance. These tests verify that the shared styles
remain compliant.
"""

from __future__ import annotations

import re
from pathlib import Path


def _parse_css_color(val: str) -> tuple[int, int, int] | None:
    """Parse hex color to RGB tuple. Returns None if not a hex color."""
    val = val.strip()
    if val.startswith("#") and len(val) == 7:
        return (int(val[1:3], 16), int(val[3:5], 16), int(val[5:7], 16))
    return None


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG relative luminance formula."""

    def _chan(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * _chan(r) + 0.7152 * _chan(g) + 0.0722 * _chan(b)


def _contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    """Compute WCAG contrast ratio between foreground and background colors."""
    l1 = _relative_luminance(*fg)
    l2 = _relative_luminance(*bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _get_css_content() -> str:
    """Load styles.css content."""
    css_path = Path(__file__).parent.parent / "src/bdboard/static/styles.css"
    return css_path.read_text()


def _extract_style_value(css: str, selector: str, prop: str) -> str | None:
    """Extract a CSS property value from a selector block."""
    # Find the selector block
    pattern = re.escape(selector) + r"\s*\{([^}]+)\}"
    match = re.search(pattern, css)
    if not match:
        return None
    block = match.group(1)
    # Find the property
    prop_pattern = re.escape(prop) + r"\s*:\s*([^;]+);"
    prop_match = re.search(prop_pattern, block)
    return prop_match.group(1).strip() if prop_match else None


def _resolve_var(css: str, var_name: str) -> str | None:
    """Resolve a CSS variable from :root."""
    pattern = r":root\s*\{([^}]+)\}"
    match = re.search(pattern, css, re.DOTALL)
    if not match:
        return None
    root_block = match.group(1)
    var_pattern = re.escape(var_name) + r"\s*:\s*([^;]+);"
    var_match = re.search(var_pattern, root_block)
    if not var_match:
        return None
    value = var_match.group(1).strip()
    # If the value is itself a var(), recursively resolve
    if value.startswith("var(") and value.endswith(")"):
        nested_var = value[4:-1].strip()
        return _resolve_var(css, nested_var)
    return value


def _get_color_value(css: str, selector: str, prop: str) -> tuple[int, int, int] | None:
    """Get a resolved RGB color value from a CSS selector property."""
    val = _extract_style_value(css, selector, prop)
    if not val:
        return None
    # Resolve CSS variable if needed
    if val.startswith("var(") and val.endswith(")"):
        var_name = val[4:-1].strip()
        val = _resolve_var(css, var_name)
        if not val:
            return None
    return _parse_css_color(val)


def test_filter_badge_inactive_meets_wcag_aa():
    """Inactive badge must meet WCAG AA contrast (4.5:1 for small text)."""
    css = _get_css_content()
    fg = _get_color_value(css, ".filter-badge", "color")
    bg = _get_color_value(css, ".filter-badge", "background")
    assert fg is not None, "Could not parse .filter-badge color"
    assert bg is not None, "Could not parse .filter-badge background"
    ratio = _contrast_ratio(fg, bg)
    # WCAG AA requires 4.5:1 for small text
    assert ratio >= 4.5, f"Inactive badge contrast {ratio:.2f}:1 fails WCAG AA (4.5:1)"


def test_filter_badge_active_meets_wcag_aa():
    """Active badge must meet WCAG AA contrast (4.5:1 for small text)."""
    css = _get_css_content()
    fg = _get_color_value(css, ".filter-badge-active", "color")
    bg = _get_color_value(css, ".filter-badge-active", "background")
    assert fg is not None, "Could not parse .filter-badge-active color"
    assert bg is not None, "Could not parse .filter-badge-active background"
    ratio = _contrast_ratio(fg, bg)
    # WCAG AA requires 4.5:1 for small text
    assert ratio >= 4.5, f"Active badge contrast {ratio:.2f}:1 fails WCAG AA (4.5:1)"


def test_filter_badge_hover_meets_wcag_aa():
    """Hover badge must meet WCAG AA contrast (4.5:1 for small text)."""
    css = _get_css_content()
    fg = _get_color_value(css, ".filter-badge:hover", "color")
    bg = _get_color_value(css, ".filter-badge:hover", "background")
    assert fg is not None, "Could not parse .filter-badge:hover color"
    assert bg is not None, "Could not parse .filter-badge:hover background"
    ratio = _contrast_ratio(fg, bg)
    # WCAG AA requires 4.5:1 for small text
    assert ratio >= 4.5, f"Hover badge contrast {ratio:.2f}:1 fails WCAG AA (4.5:1)"


def test_filter_badges_have_visual_weight_difference():
    """Active and inactive badges must differ in visual weight, not just color.

    WCAG 2.2 requires non-color distinguishability. We verify that the active
    badge has heavier font-weight AND a box-shadow, so the difference is
    perceivable even in grayscale or for color-blind users.
    """
    css = _get_css_content()
    inactive_weight = _extract_style_value(css, ".filter-badge", "font-weight")
    active_weight = _extract_style_value(css, ".filter-badge-active", "font-weight")
    assert inactive_weight is not None, "Could not find .filter-badge font-weight"
    assert active_weight is not None, "Could not find .filter-badge-active font-weight"
    # Active should be heavier (700 -> 800)
    assert int(active_weight) > int(inactive_weight), (
        "Active badge must have heavier font-weight"
    )
    # Active should also have a box-shadow for additional visual weight
    shadow = _extract_style_value(css, ".filter-badge-active", "box-shadow")
    assert shadow is not None, "Active badge must have box-shadow"
    assert "inset" in shadow, "Active badge box-shadow should be inset"
