"""Tests for the per-type glyph/badge (bdboard-2n6g / audit FB-2).

bdboard used to render every bead type as identical uppercase grey text
(memory bdboard-anatomy-type-flat), so a milestone / gate / coordination bead
was indistinguishable from a chore at a glance. This bead maps issue_type ->
a field-guide glyph + a reinforcing per-type color on the card and the modal
header.

Two concerns are locked here:

1. The ``type_glyph`` Jinja filter (``app._type_glyph``): every built-in type
   gets a distinct non-empty glyph; an unknown/custom/None type falls back to
   "" so the badge renders the plain grey label with no glyph (no crash).
2. WCAG: the glyph is a non-text graphical object reinforcing the (already
   AA-contrast) label, so each ``.type-<slug> .bead-type-glyph`` color must
   clear the 1.4.11 non-text 3:1 ratio against the card surface (``--paper-3``)
   in BOTH themes. The label itself stays ``--ink-2`` (AA), so meaning is never
   conveyed by color alone (WCAG 1.4.1).
"""

from __future__ import annotations

from pathlib import Path

from bdboard import app
from css_test_utils import (
    dark_theme_variables,
    extract_style_property,
    parse_css_variables,
    resolve_css_value,
)
from wcag_utils import contrast_ratio

CSS_PATH = Path("src/bdboard/static/styles.css")

AA_NON_TEXT = 3.0  # WCAG 1.4.11 non-text (the glyph is a graphical object)

# The 9 built-in bead types + the `event` pseudo-type (field guide ch1). Each
# MUST have a distinct glyph (the bead's named acceptance criterion).
BUILTIN_TYPES = (
    "task",
    "bug",
    "feature",
    "chore",
    "epic",
    "decision",
    "spike",
    "story",
    "milestone",
    "event",
)

# Internal container types the audit also glyphs (FB-3 / FB-5 downstream).
INTERNAL_TYPES = ("gate", "molecule")

ALL_GLYPHED = BUILTIN_TYPES + INTERNAL_TYPES


# ---- filter behavior -------------------------------------------------------


def test_every_builtin_type_has_a_nonempty_glyph():
    for t in BUILTIN_TYPES:
        assert app._type_glyph(t), f"built-in type {t!r} has no glyph"


def test_builtin_glyphs_are_all_distinct():
    """Each built-in type renders a DISTINCT glyph (bead acceptance criterion)."""
    glyphs = [app._type_glyph(t) for t in BUILTIN_TYPES]
    assert len(set(glyphs)) == len(glyphs), f"duplicate glyphs among built-ins: {glyphs}"


def test_internal_container_types_have_glyphs():
    for t in INTERNAL_TYPES:
        assert app._type_glyph(t), f"internal type {t!r} has no glyph"


def test_glyph_lookup_is_case_insensitive():
    assert app._type_glyph("Task") == app._type_glyph("task")
    assert app._type_glyph("  BUG ") == app._type_glyph("bug")


def test_unknown_and_empty_types_fall_back_to_no_glyph():
    """Unknown/custom/None type -> "" so the badge shows plain text, no crash."""
    assert app._type_glyph("custom-thing") == ""
    assert app._type_glyph("") == ""
    assert app._type_glyph(None) == ""


# ---- WCAG non-text contrast (glyph color on the card surface) --------------


def _glyph_color(slug: str, variables: dict[str, str]) -> str:
    raw = extract_style_property(
        CSS_PATH.read_text(encoding="utf-8"),
        f".type-{slug} .bead-type-glyph",
        "color",
        variables,
    )
    assert raw is not None, f"no .type-{slug} .bead-type-glyph color rule found"
    color = resolve_css_value(raw, variables)
    assert color.startswith("#"), f"type {slug} glyph color did not resolve to hex: {color!r}"
    return color


def _card_surface(variables: dict[str, str]) -> str:
    surface = resolve_css_value("var(--paper-3)", variables)
    assert surface.startswith("#"), f"--paper-3 did not resolve to hex: {surface!r}"
    return surface


def test_every_glyphed_type_has_a_color_rule_in_both_themes():
    css = CSS_PATH.read_text(encoding="utf-8")
    light = parse_css_variables(css)
    dark = dark_theme_variables(css)
    for slug in ALL_GLYPHED:
        # Resolves to hex under both palettes or the helper assertions fire.
        _glyph_color(slug, light)
        _glyph_color(slug, dark)


def test_glyph_colors_meet_non_text_contrast_light():
    light = parse_css_variables(CSS_PATH.read_text(encoding="utf-8"))
    surface = _card_surface(light)
    failures = []
    for slug in ALL_GLYPHED:
        ratio = contrast_ratio(_glyph_color(slug, light), surface)
        if ratio < AA_NON_TEXT:
            failures.append(f"{slug}: {ratio:.2f}:1 < {AA_NON_TEXT}:1 on {surface}")
    assert not failures, "Light theme glyph non-text contrast failures:\n" + "\n".join(failures)


def test_glyph_colors_meet_non_text_contrast_dark():
    dark = dark_theme_variables(CSS_PATH.read_text(encoding="utf-8"))
    surface = _card_surface(dark)
    failures = []
    for slug in ALL_GLYPHED:
        ratio = contrast_ratio(_glyph_color(slug, dark), surface)
        if ratio < AA_NON_TEXT:
            failures.append(f"{slug}: {ratio:.2f}:1 < {AA_NON_TEXT}:1 on {surface}")
    assert not failures, "Dark theme glyph non-text contrast failures:\n" + "\n".join(failures)


def test_builtin_glyph_colors_are_distinct_light():
    """Each built-in type also gets a DISTINCT color (not just glyph) in light."""
    light = parse_css_variables(CSS_PATH.read_text(encoding="utf-8"))
    colors = [_glyph_color(t, light) for t in BUILTIN_TYPES]
    # event deliberately reuses chore's muted; the other 9 built-ins are unique.
    non_event = [c for t, c in zip(BUILTIN_TYPES, colors, strict=True) if t != "event"]
    assert len(set(non_event)) == len(non_event), f"duplicate built-in glyph colors: {colors}"
