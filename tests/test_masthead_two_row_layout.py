"""Structural tests for the two-row masthead layout (bdboard-vbz line, final
intent clarified in bdboard-xgu).

Final intended layout (bdboard-xgu):

* TOP row    = brand (left) + counts/stats strip (right).
* SECOND row = page nav (left) + actions group, i.e. the theme toggle and
  '+ Pour Formula' button (right) \u2014 sharing the row opposite the nav.

History of the bug chain these tests guard against:

* bdboard-9y7: a wrapping top row let the actions group reflow ABOVE/below the
  brand and get mis-aligned. Fix: nowrap rows.
* bdboard-xgu: the actions were on the TOP row (inline beside the brand when
  wide, wrapped above it when narrow). The clarified intent moves them to the
  SECOND row, right-aligned opposite the nav, at all widths.

These assert on the stylesheet + templates so a future edit can't silently
put the actions back on the top row, drop the nowrap guard, or break the
left/right split.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import extract_style_property

CSS_PATH = Path("src/bdboard/static/styles.css")
TEMPLATES = Path("src/bdboard/templates")
# History migrated into the Analytics tab (bdboard-ove7); analytics.html is the
# full-page surface that now shares the two-row masthead structure. Coordination
# was reverted off its own tab back onto the board as a second epic-lane-style
# strip (bdboard-xiwd), so it no longer has its own full-page surface here.
SURFACES = ("dashboard.html", "analytics.html", "memory.html")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def test_rows_do_not_wrap():
    """Both masthead rows are nowrap so the right-hand group never wraps over
    its row-mate at narrow widths (the bdboard-9y7 / bdboard-xgu bug)."""
    css = _css()
    wrap = extract_style_property(css, ".masthead-row", "flex-wrap")
    assert wrap == "nowrap", (
        f".masthead-row must be nowrap so the right group can't wrap above its "
        f"row-mate (bdboard-9y7/bdboard-xgu); got {wrap!r}"
    )


def test_rows_split_left_and_right():
    """Each row splits its two children left vs right via space-between."""
    css = _css()
    justify = extract_style_property(css, ".masthead-row", "justify-content")
    assert justify == "space-between", (
        f".masthead-row must use justify-content:space-between so each row's "
        f"left item and right group sit on opposite edges; got {justify!r}"
    )


def test_actions_group_pins_right():
    """The actions group hugs the right edge of its row."""
    css = _css()
    margin = extract_style_property(css, ".masthead-actions", "margin-left")
    assert margin == "auto", (
        f".masthead-actions must use margin-left:auto to stay hard-right even "
        f"if its row-mate is absent; got {margin!r}"
    )
    justify = extract_style_property(css, ".masthead-actions", "justify-content")
    assert justify == "flex-end", (
        f".masthead-actions content should be flex-end (right); got {justify!r}"
    )


def test_actions_group_still_wraps_internally():
    """Narrow-width graceful degradation (bdboard-c52) is preserved.

    The rows are nowrap, so the actions group itself must wrap internally
    rather than overflow or push above the nav when space is tight.
    """
    css = _css()
    wrap = extract_style_property(css, ".masthead-actions", "flex-wrap")
    assert wrap == "wrap", (
        f".masthead-actions must wrap internally so the nowrap rows still "
        f"degrade gracefully at narrow widths (bdboard-c52); got {wrap!r}"
    )


def test_actions_live_on_the_second_row_not_the_top():
    """The theme toggle + Pour Formula must sit on the SECOND row (with the
    nav), not on the top row beside the brand (bdboard-xgu).

    Verified structurally: in every surface the .masthead-actions group appears
    AFTER the .masthead-nav-row opens, and the nav partial is included before
    the actions inside that same second row.
    """
    for name in SURFACES:
        html = (TEMPLATES / name).read_text(encoding="utf-8")
        nav_row_idx = html.find('class="masthead-row masthead-nav-row"')
        actions_idx = html.find('class="masthead-actions"')
        assert nav_row_idx != -1, f"{name} is missing the second .masthead-nav-row"
        assert actions_idx != -1, f"{name} is missing the .masthead-actions group"
        assert actions_idx > nav_row_idx, (
            f"{name}: .masthead-actions must be inside the SECOND row "
            f"(.masthead-nav-row), not on the top row (bdboard-xgu)"
        )
        # The nav partial should come before the actions within that second row.
        nav_include_idx = html.find("partials/nav.html")
        assert nav_include_idx != -1, f"{name} is not including the nav partial"
        assert nav_include_idx < actions_idx, (
            f"{name}: page nav should be left of the actions on the second row"
        )


def test_counts_strip_is_not_inside_the_actions_group():
    """The counts/stats strip belongs on the TOP row with the brand, NOT inside
    the second-row actions group (bdboard-xgu).

    Board has #counts on its masthead. Memory and Analytics have no masthead
    counts strip (Analytics' History sub-view owns its own stats host inside
    the panel body, not the masthead — bdboard-ove7), so only the board is
    checked here.
    """
    checks = {"dashboard.html": 'id="counts"'}
    for name, needle in checks.items():
        html = (TEMPLATES / name).read_text(encoding="utf-8")
        counts_idx = html.find(needle)
        actions_idx = html.find('class="masthead-actions"')
        assert counts_idx != -1, f"{name} is missing its counts host {needle}"
        # The counts host appears in the TOP row, which is emitted before the
        # second-row actions group.
        assert counts_idx < actions_idx, (
            f"{name}: the counts strip must stay on the top row, before the "
            f"second-row actions group (bdboard-xgu)"
        )


def test_all_surfaces_share_the_two_row_structure():
    """Board / History / Memory all use identical two-row wiring: a top
    .masthead-row plus a .masthead-row.masthead-nav-row holding nav + actions."""
    for name in SURFACES:
        html = (TEMPLATES / name).read_text(encoding="utf-8")
        assert 'class="masthead-row masthead-nav-row"' in html, (
            f"{name} is missing the second .masthead-nav-row"
        )
        assert 'class="masthead-actions"' in html, f"{name} is missing the .masthead-actions group"
        assert "partials/nav.html" in html, f"{name} is not including the nav partial"
        assert "partials/theme_toggle.html" in html, (
            f"{name} is not including the theme toggle in its actions group"
        )
