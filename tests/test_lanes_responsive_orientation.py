"""Structural tests for consistent swim-lane orientation on small screens
(bdboard-0m4i).

The board lanes are a CSS grid: ``repeat(6)`` wide, narrowing to ``repeat(3)``
@1600px. The narrow regime used to drop to ``repeat(2)`` @900px, but the lane
count varies (6-9, since the Pinned/Gate/Swarm lanes only render when
populated), so a 2-column grid left a ragged last row that read as a mix of
orientations - a half-and-half board.

The fix collapses the narrow regime to ONE full-width column so every lane is
uniformly stacked (and stacked lanes get a natural page scroll). These tests
assert on the stylesheet so a future edit can't silently reintroduce the
uneven multi-column narrow grid, and can't regress the wider breakpoints.
"""

from __future__ import annotations

from pathlib import Path

CSS_PATH = Path("src/bdboard/static/styles.css")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _media_block(css: str, header: str) -> str:
    """Return the body of the FIRST ``@media`` block whose header matches AND
    which contains a ``.lanes`` rule, using balanced-brace scanning (regex
    can't match nested braces inside a media query).

    ``header`` is the literal text after ``@media`` and before the opening
    brace, e.g. ``"(max-width: 900px)"``. There can be more than one media
    query at the same width (the lanes one and an unrelated field-grid one), so
    we pick the block that actually styles ``.lanes``.
    """
    needle = "@media " + header
    start = 0
    while True:
        idx = css.find(needle, start)
        if idx == -1:
            raise AssertionError(f"no @media {header} block styling .lanes found")
        brace = css.find("{", idx)
        depth = 0
        i = brace
        while i < len(css):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    body = css[brace + 1 : i]
                    if ".lanes" in body:
                        return body
                    break
            i += 1
        start = i + 1


# ----- AC: single consistent orientation at narrow widths -----


def test_narrow_lanes_are_single_column():
    """At <=900px the lanes collapse to ONE full-width column (1fr)."""
    body = _media_block(_css(), "(max-width: 900px)")
    assert "grid-template-columns: 1fr" in body, (
        "the <=900px lanes must use a single full-width column "
        "(grid-template-columns: 1fr) for a consistent orientation (bdboard-0m4i)"
    )


def test_narrow_lanes_have_no_multicolumn_grid():
    """No multi-column (repeat(2)/repeat(3)) grid survives in the narrow regime;
    a 2-col grid was the exact half-and-half bug this bead fixes."""
    body = _media_block(_css(), "(max-width: 900px)")
    assert "repeat(2" not in body, "the uneven 2-column narrow grid must be gone (bdboard-0m4i)"
    assert "repeat(3" not in body, "the narrow regime must not reintroduce a multi-column grid"


def test_narrow_board_scrolls_as_a_page():
    """Stacked lanes need the board to scroll as a page (not crammed into the
    viewport with each lane a sliver), so the narrow regime flips overflow."""
    body = _media_block(_css(), "(max-width: 900px)")
    assert "overflow-y: auto" in body, (
        "the <=900px board must scroll as a page so stacked lanes stay usable"
    )
    # A long lane still scrolls internally rather than dwarfing the rest.
    assert "max-height: 80vh" in body or "max-height:80vh" in body, (
        "each narrow lane should cap its height so one long lane doesn't dominate"
    )


# ----- no regression at the wider breakpoints -----


def test_base_lanes_are_six_columns():
    """The widest layout is still 6 columns (no regression)."""
    css = _css()
    # The base .lanes rule (outside any media query) keeps repeat(6).
    assert "repeat(6, minmax(0, 1fr))" in css, "base .lanes must remain a 6-column grid"


def test_intermediate_breakpoint_is_three_columns():
    """The 900-1600px regime is still 3 columns (no regression)."""
    body = _media_block(_css(), "(max-width: 1600px)")
    assert "repeat(3, minmax(0, 1fr))" in body, (
        "the <=1600px regime must remain a 3-column grid (no regression)"
    )
