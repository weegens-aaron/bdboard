"""WCAG AA contrast tests for bead status badges in modal views.

Tests the .status-* selectors used in modal dialogs for individual beads.
Complements test_epic_status_contrast.py which tests .epic-status.* badges.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import (
    contrast_ratio,
    extract_style_property,
    parse_css_variables,
)

CSS_PATH = Path("src/bdboard/static/styles.css")
# Status values that can appear in modal bead detail views
# Note: 'closed', 'resolved', 'done' share colors via combined selector in CSS
BEAD_STATUS_KEYS = ("open", "in_progress", "blocked", "done")
AA_NORMAL_TEXT_MIN_RATIO = 4.5


def _extract_bead_status_colors(
    css: str, status_key: str, variables: dict[str, str]
) -> tuple[str, str]:
    """Extract foreground and background colors for a bead status badge.

    Args:
        css: CSS content
        status_key: Status key (e.g., "open", "done")
        variables: Pre-parsed CSS variables

    Returns:
        Tuple of (foreground_color, background_color) as hex strings

    Note:
        The CSS uses `.status-closed, .status-resolved, .status-done {...}`
        as a combined selector. The extractor can only parse the last selector
        in a group, so we test 'done' to cover all three closed-family states.
    """
    selector = f".status-{status_key}"
    foreground = extract_style_property(css, selector, "color", variables)
    background = extract_style_property(css, selector, "background", variables)

    if not foreground or not background:
        raise AssertionError(f"Missing color or background for {selector}")

    return foreground, background


def test_bead_status_badges_meet_wcag_aa_contrast_for_normal_text():
    """Verify all modal bead status badges meet WCAG AA contrast requirements."""
    css = CSS_PATH.read_text(encoding="utf-8")
    variables = parse_css_variables(css)

    for status_key in BEAD_STATUS_KEYS:
        foreground, background = _extract_bead_status_colors(css, status_key, variables)
        ratio = contrast_ratio(foreground, background)
        assert ratio >= AA_NORMAL_TEXT_MIN_RATIO, (
            f".status-{status_key} contrast {ratio:.2f}:1 is below "
            f"WCAG AA {AA_NORMAL_TEXT_MIN_RATIO}:1"
        )
