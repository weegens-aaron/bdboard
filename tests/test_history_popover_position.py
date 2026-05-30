"""Regression test for bdboard-r1h: history stat info-popovers must stay
in the viewport rather than clipping above the top edge.

The history stats strip lives at the very top of the masthead. The original
bdboard-5wt popover anchored ABOVE its trigger (``bottom: calc(100% + 6px)``),
so there was no room above it and the panel was clipped off the top of the
window. The fix anchors the popover BELOW the trigger (``top: ...``), where the
whole page provides room, and right-anchors the last cell's popover so a wide
panel grows inward instead of off the right edge.

These assert the CSS contract directly (no browser needed): the popover opens
downward and never re-introduces the upward anchor that caused the clip.
"""

from pathlib import Path

from css_test_utils import extract_style_property

CSS = (
    Path(__file__).resolve().parent.parent / "src" / "bdboard" / "static" / "styles.css"
).read_text()


def test_popover_anchors_below_trigger_not_above() -> None:
    # Anchored downward: a `top` offset is present...
    top = extract_style_property(CSS, ".stat-info-pop", "top")
    assert top is not None, "popover must define a downward (top) anchor"
    assert "100%" in top, "popover should sit just below the trigger (calc 100% +)"


def test_popover_does_not_anchor_upward() -> None:
    # ...and the upward anchor that caused the off-screen clip is gone.
    bottom = extract_style_property(CSS, ".stat-info-pop", "bottom")
    assert bottom is None, (
        "popover must NOT anchor via `bottom` (that clipped it above the "
        "viewport top — bdboard-r1h)"
    )


def test_last_cell_popover_anchors_to_right_edge() -> None:
    # The right-most stat cell flips its popover to grow leftward so a wide
    # panel cannot overflow past the right edge of the viewport.
    right = extract_style_property(
        CSS, ".history-stats .counts-cell:last-child .stat-info-pop", "right"
    )
    assert right is not None, "last-cell popover must right-anchor (bdboard-r1h)"
