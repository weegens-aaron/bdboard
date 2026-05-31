"""Structural tests for the two-row masthead layout (bdboard-vbz / bdboard-9y7).

The two-row masthead puts the brand on the left of the TOP row with the
theme toggle + '+ Pour Formula' + counts strip right-aligned beside it, and
the page nav alone on a LEFT-aligned SECOND row.

bdboard-9y7 was a layout regression: the top ``.masthead-row`` used
``flex-wrap: wrap`` + ``justify-content: space-between``. Once the actions
group got wide enough it wrapped onto its own line, where \u2014 as the lone flex
item \u2014 ``space-between`` left-aligned it UNDER the brand instead of leaving it
right-aligned on the top row.

These assertions lock in the fix so a future edit can't silently reintroduce
the wrap-then-left-align bug:

* top row is ``nowrap`` (brand + actions stay on one line),
* the actions group pins itself right with ``margin-left: auto``,
* the nav row stays ``flex-start`` (left-aligned) on its own row.

They also assert the markup wiring is consistent across all three surfaces
(board / history / memory) so the layout can't drift per-page.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import extract_style_property

CSS_PATH = Path("src/bdboard/static/styles.css")
TEMPLATES = Path("src/bdboard/templates")
SURFACES = ("dashboard.html", "history.html", "memory.html")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def test_top_row_does_not_wrap():
    """The top masthead row keeps brand + actions on a single line.

    A wrapping top row is exactly what dropped the actions group below the
    brand and left-aligned it (the bdboard-9y7 regression).
    """
    css = _css()
    wrap = extract_style_property(css, ".masthead-row", "flex-wrap")
    assert wrap == "nowrap", (
        f".masthead-row must be nowrap so the actions group can't wrap below "
        f"the brand and get left-aligned (bdboard-9y7); got {wrap!r}"
    )


def test_top_row_no_longer_uses_space_between():
    """space-between left-aligns a lone wrapped item \u2014 the fix drops it.

    Right-alignment now comes from the actions group's own margin-left:auto.
    """
    css = _css()
    justify = extract_style_property(css, ".masthead-row", "justify-content")
    assert justify != "space-between", (
        ".masthead-row should not rely on justify-content:space-between to "
        "right-align actions \u2014 that mis-aligns a lone wrapped item (bdboard-9y7)"
    )


def test_actions_group_pins_right_with_auto_margin():
    """The actions group right-aligns via margin-left:auto on the top row."""
    css = _css()
    margin = extract_style_property(css, ".masthead-actions", "margin-left")
    assert margin == "auto", (
        f".masthead-actions must use margin-left:auto to stay right-aligned on "
        f"the top row regardless of brand width (bdboard-9y7); got {margin!r}"
    )


def test_actions_group_still_wraps_internally():
    """Narrow-width graceful degradation (bdboard-c52) is preserved.

    The top row is nowrap, so the actions group itself must wrap internally
    rather than overflow when space is tight.
    """
    css = _css()
    wrap = extract_style_property(css, ".masthead-actions", "flex-wrap")
    assert wrap == "wrap", (
        f".masthead-actions must wrap internally so the nowrap top row still "
        f"degrades gracefully at narrow widths (bdboard-c52); got {wrap!r}"
    )


def test_nav_row_is_left_aligned():
    """The second row (page nav) stays hard-left on its own line."""
    css = _css()
    justify = extract_style_property(css, ".masthead-nav-row", "justify-content")
    assert justify == "flex-start", (
        f".masthead-nav-row must be flex-start so the nav sits hard-left on its "
        f"own second row; got {justify!r}"
    )


def test_all_surfaces_share_the_two_row_structure():
    """Board / History / Memory must all use the identical two-row wiring.

    A top ``.masthead-row`` holding ``.masthead-actions`` plus a separate
    ``.masthead-row masthead-nav-row`` including the shared nav partial.
    """
    for name in SURFACES:
        html = (TEMPLATES / name).read_text(encoding="utf-8")
        assert 'class="masthead-actions"' in html, (
            f"{name} is missing the top-row .masthead-actions group"
        )
        assert 'class="masthead-row masthead-nav-row"' in html, (
            f"{name} is missing the second .masthead-nav-row"
        )
        assert "partials/nav.html" in html, f"{name} is not including the nav partial"
        assert "partials/theme_toggle.html" in html, (
            f"{name} is not including the theme toggle in its actions group"
        )
