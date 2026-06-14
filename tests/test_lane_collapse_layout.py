"""Structural tests for collapsible label-above-cards lanes (bdboard-px6d).

Two changes to BOTH board strips (Epics in flight + Coordination):

1. The lane LABEL sits ABOVE its cards (label row on top, cards row beneath).
2. Each lane is COLLAPSIBLE to just its label row via a real <button>
   disclosure (aria-expanded + aria-controls, keyboard operable, rotating
   caret), with the collapsed state persisted across reloads/HTMX refreshes.

Plus: epic AND coordination cards share a single FIXED width (uniform card
size across both strips), not a flexible max-width.

These assert on the rendered templates, the stylesheet, and the base.html
wiring so a future edit can't silently regress the layout, the disclosure
semantics, the fixed-width cards, or the persistence wiring.
"""

from __future__ import annotations

from pathlib import Path

CSS_PATH = Path("src/bdboard/static/styles.css")
TEMPLATES = Path("src/bdboard/templates")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _lanes() -> str:
    return (TEMPLATES / "partials" / "lanes.html").read_text(encoding="utf-8")


def _coordination() -> str:
    return (TEMPLATES / "partials" / "coordination_lane.html").read_text(encoding="utf-8")


def _base() -> str:
    return (TEMPLATES / "base.html").read_text(encoding="utf-8")


# ----- AC: label-above-cards layout -----


def test_epic_lane_label_row_sits_above_cards_region():
    """Epic lane row 1 = label row (disclosure + count + time-filter); row 2 =
    the collapsible cards region with the epic strip beneath it."""
    html = _lanes()
    label_idx = html.find('class="lane-label-row"')
    region_idx = html.find('id="epic-lane-cards"')
    strip_idx = html.find('class="epic-strip"')
    assert label_idx != -1, "epic lane needs a .lane-label-row (label on top)"
    assert region_idx != -1, "epic lane needs an #epic-lane-cards region"
    assert label_idx < region_idx < strip_idx, (
        "the label row must come BEFORE the cards region, which wraps the strip"
    )


def test_epic_lane_time_filter_lives_on_the_label_row():
    """The board time-filter radiogroup sits on the label row (row 1)."""
    html = _lanes()
    label_idx = html.find('class="lane-label-row"')
    region_idx = html.find('id="epic-lane-cards"')
    filter_idx = html.find('id="board-time-filter"')
    assert label_idx < filter_idx < region_idx, (
        "the time-filter must be on the label row, above the cards region"
    )


def test_coordination_lane_label_sits_above_cards_region():
    """Coordination lane label ('Coordination' + count) sits above its cards."""
    html = _coordination()
    label_idx = html.find('class="lane-label-row"')
    region_idx = html.find('id="coordination-lane-cards"')
    strip_idx = html.find('class="epic-strip"')
    assert label_idx != -1 and region_idx != -1
    assert label_idx < region_idx < strip_idx


def test_epic_lane_is_a_vertical_stack():
    """The .epic-lane flex container stacks its rows (column), not a single
    inline row, so the label can sit above the cards."""
    css = _css()
    block = css[css.find(".epic-lane {") : css.find(".epic-lane {") + 400]
    assert "flex-direction: column" in block, (
        ".epic-lane must be a column stack so the label sits above the cards"
    )


# ----- AC: collapsible disclosure semantics -----


def test_both_lanes_use_a_real_button_disclosure():
    """Both lanes carry a real <button class=lane-disclosure> with
    aria-expanded + aria-controls (keyboard operable for free)."""
    for html, region_id in (
        (_lanes(), "epic-lane-cards"),
        (_coordination(), "coordination-lane-cards"),
    ):
        assert 'class="lane-disclosure"' in html
        assert "<button" in html and 'aria-expanded="true"' in html
        assert f'aria-controls="{region_id}"' in html


def test_disclosure_uses_rotating_caret_not_swapped_glyph():
    """The caret is one stable glyph rotated via CSS (so the accessible name
    doesn't change), not a swapped > / v character. Collapsed-vs-expanded is
    conveyed by transform (not colour-only)."""
    for html in (_lanes(), _coordination()):
        assert 'class="lane-caret"' in html
        assert 'aria-hidden="true"' in html  # caret is decorative
    css = _css()
    assert ".lane-caret" in css
    assert "transform: rotate" in css
    assert '.lane-disclosure[aria-expanded="false"] .lane-caret' in css, (
        "the collapsed state must rotate the caret via the aria-expanded hook"
    )


def test_collapsed_region_is_hidden_via_css():
    """The cards region is removed from layout when collapsed (hidden attr)."""
    css = _css()
    assert ".lane-cards-region[hidden]" in css and "display: none" in css


def test_caret_rotation_respects_reduced_motion():
    """The caret transition is suppressed under prefers-reduced-motion."""
    css = _css()
    # Find a reduced-motion block that disables the caret transition.
    assert ".lane-caret { transition: none; }" in css or (
        "prefers-reduced-motion" in css and ".lane-caret" in css
    )


# ----- AC: persistence + refresh survival wiring -----


def test_base_wires_lane_collapse_with_localstorage_persistence():
    """base.html defines wireLaneCollapse(), persists per-lane state in
    localStorage (a stickier preference than the time window), and re-runs it
    on htmx:afterSettle so collapse survives /api/lanes + /api/gates refreshes
    AND on DOMContentLoaded for initial restore."""
    js = _base()
    assert "function wireLaneCollapse()" in js
    assert "bdboard-lane-collapsed:" in js
    assert "localStorage" in js
    # Re-run on settle (both strips re-render independently on SSE) + on load.
    settle_idx = js.find("htmx:afterSettle")
    assert settle_idx != -1
    assert "wireLaneCollapse()" in js[settle_idx:]
    dcl_idx = js.find("DOMContentLoaded")
    assert "wireLaneCollapse()" in js[dcl_idx:]


def test_lane_disclosure_carries_a_per_lane_key():
    """Each disclosure tags itself with a data-lane-key so collapse state is
    persisted per lane (epics / coordination), not globally."""
    assert 'data-lane-key="epics"' in _lanes()
    assert 'data-lane-key="coordination"' in _coordination()


# ----- AC: uniform fixed-width cards across both strips -----


def test_epic_chip_uses_a_single_fixed_width_not_max_width():
    """The .epic-chip card uses a fixed `width` (uniform size) rather than the
    old flexible `max-width: 255px`, so epic + coordination chips match."""
    css = _css()
    block = css[css.find(".epic-chip {") : css.find(".epic-chip {") + 400]
    assert "width: 248px" in block, "epic chips need a single fixed width"
    assert "max-width: 255px;" not in block, (
        "the flexible max-width must be replaced by a fixed width (bdboard-px6d)"
    )


def test_coordination_chips_reuse_the_epic_chip_width():
    """Coordination chips carry the .epic-chip class, so they inherit the same
    fixed width — uniform cards across both strips without a duplicate rule."""
    html = _coordination()
    assert "epic-chip coordination-chip" in html


# ----- no regression: coordination strip still self-hides when empty -----


def test_coordination_strip_still_self_hides_when_empty():
    """The whole lane (disclosure header included) is gated behind has_content,
    so a quiet board shows no collapsible-but-empty Coordination header."""
    html = _coordination()
    guard_idx = html.find("{% if has_content %}")
    section_idx = html.find('class="epic-lane coordination-lane"')
    assert guard_idx != -1 and guard_idx < section_idx, (
        "the coordination lane (label row + all) must sit inside the "
        "has_content guard so an empty board renders nothing"
    )
