"""WCAG AA contrast tests for Closed lane filter badges.

bdboard-bcx acceptance criteria 5: Active/inactive states are visually
distinct, not color-alone, and pass WCAG 2.2 AA contrast.
"""

import re
from pathlib import Path


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #rrggbb hex color to (r, g, b) tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Compute relative luminance per WCAG definition."""
    r, g, b = (c / 255.0 for c in rgb)
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg: str, bg: str) -> float:
    """Compute WCAG contrast ratio between foreground and background colors."""
    l1 = _relative_luminance(_hex_to_rgb(fg))
    l2 = _relative_luminance(_hex_to_rgb(bg))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _extract_filter_badge_colors(css_content: str) -> dict[str, tuple[str, str]]:
    """Extract foreground and background colors for filter badges.

    Returns: {state: (fg_color, bg_color)}
    """
    colors = {}

    # Extract CSS variables first
    paper_3_match = re.search(r"--paper-3:\s*(#[0-9a-fA-F]{6});", css_content)
    gray_100_match = re.search(r"--gray-100:\s*(#[0-9a-fA-F]{6});", css_content)
    blue_100_match = re.search(r"--blue-100:\s*(#[0-9a-fA-F]{6});", css_content)
    brand_blue_l_match = re.search(r"--brand-blue-l:\s*(#[0-9a-fA-F]{6});", css_content)

    if not all([paper_3_match, gray_100_match, blue_100_match, brand_blue_l_match]):
        return colors

    paper_3 = paper_3_match.group(1)
    gray_100 = gray_100_match.group(1)
    blue_100 = blue_100_match.group(1)
    brand_blue_l = brand_blue_l_match.group(1)

    # Inactive badge - gray text on white background
    inactive_match = re.search(
        r"\.filter-badge\s*\{[^}]*?color:\s*var\(--muted\);", css_content, re.DOTALL
    )
    if inactive_match:
        colors["inactive"] = (gray_100, paper_3)

    # Active badge - white text on blue background
    active_match = re.search(
        r"\.filter-badge-active\s*\{[^}]*?background:\s*var\(--blue-100\);",
        css_content,
        re.DOTALL,
    )
    if active_match:
        colors["active"] = ("#ffffff", blue_100)

    # Hover state - blue text on light blue background
    hover_match = re.search(
        r"\.filter-badge:hover\s*\{[^}]*?color:\s*var\(--blue-100\);",
        css_content,
        re.DOTALL,
    )
    if hover_match:
        colors["inactive_hover"] = (blue_100, brand_blue_l)

    return colors


def test_filter_badge_inactive_meets_wcag_aa():
    """Inactive filter badge must meet WCAG AA 4.5:1 for small text."""
    css_path = Path(__file__).parent.parent / "src/bdboard/static/styles.css"
    css_content = css_path.read_text()
    colors = _extract_filter_badge_colors(css_content)

    assert "inactive" in colors, "Could not extract inactive badge colors from CSS"
    fg, bg = colors["inactive"]
    ratio = _contrast_ratio(fg, bg)

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
    ratio = _contrast_ratio(fg, bg)

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
    ratio = _contrast_ratio(fg, bg)

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

    # Active badge should have stronger font-weight
    active_font_weight = re.search(
        r"\.filter-badge-active\s*\{[^}]*?font-weight:\s*(\d+);", css_content, re.DOTALL
    )
    inactive_font_weight = re.search(
        r"\.filter-badge\s*\{[^}]*?font-weight:\s*(\d+);", css_content, re.DOTALL
    )

    assert active_font_weight and inactive_font_weight, (
        "Could not extract font-weight from CSS"
    )

    active_weight = int(active_font_weight.group(1))
    inactive_weight = int(inactive_font_weight.group(1))

    assert active_weight > inactive_weight, (
        f"Active badge font-weight ({active_weight}) must be heavier than inactive ({inactive_weight})"
    )

    # Active badge should have box-shadow for additional visual weight
    active_shadow = re.search(
        r"\.filter-badge-active\s*\{[^}]*?box-shadow:", css_content, re.DOTALL
    )
    assert active_shadow, (
        "Active badge must have box-shadow for non-color visual distinction"
    )
