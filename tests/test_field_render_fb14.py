"""Tests for the FB-14 anatomy field-render fixes (bdboard-d7ud).

Three nits, three concerns locked here:

1. ``design`` renders as markdown AND sits in the content group (not the
   alphabetical tail): it's in ``_FIELD_ORDER`` right after
   ``acceptance_criteria`` and in ``_KIND_MARKDOWN`` so ``_classify_field``
   types it as ``markdown`` (ADR/design rationale keeps its formatting).
2. The ``issue_type`` inline-edit dropdown is NON-LOSSY: ``_ISSUE_TYPE_OPTIONS``
   covers every bd built-in type, so editing a spike/story/milestone can
   preserve its own type.
3. Magic labels (``dim:``, ``gt:``, ``provides:``, ``export:``, ``template``)
   decode to a distinct category + value via ``_decode_label`` instead of
   rendering as undifferentiated grey chips; freeform tags fall back to "tag".
"""

from __future__ import annotations

from pathlib import Path

from bdboard import app

CSS_PATH = Path("src/bdboard/static/styles.css")

# bd's full built-in type set, sourced from `bd types --json` (9 core types).
# The dropdown MUST be able to select every one of these to be non-lossy.
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
)


# ---- (1) design: markdown + content-group ordering -------------------------


def test_design_is_classified_as_markdown():
    """A design value rendered through the markdown kind, not raw scalar."""
    assert "design" in app._KIND_MARKDOWN
    assert app._classify_field("design", "## Rationale\n\n- a\n- b") == "markdown"


def test_design_is_in_field_order_content_group():
    """design must have an explicit slot (no alphabetical-tail exile)."""
    assert "design" in app._FIELD_ORDER
    # Sits in the content group: after acceptance_criteria, before state/meta
    # (issue_type is the first state/meta key).
    order = app._FIELD_ORDER
    assert order.index("design") > order.index("acceptance_criteria")
    assert order.index("design") < order.index("issue_type")


def test_design_row_renders_markdown_kind():
    bead = {"id": "x1", "title": "t", "design": "**bold** plan", "status": "open"}
    rows = {r["key"]: r for r in app._ordered_fields(bead)}
    assert rows["design"]["kind"] == "markdown"


# ---- (2) non-lossy issue_type dropdown -------------------------------------


def test_issue_type_options_cover_every_builtin():
    """Every bd built-in type is selectable (the bead's acceptance criterion)."""
    missing = [t for t in BUILTIN_TYPES if t not in app._ISSUE_TYPE_OPTIONS]
    assert not missing, f"issue_type dropdown can't select built-ins: {missing}"


def test_issue_type_options_have_no_duplicates():
    opts = app._ISSUE_TYPE_OPTIONS
    assert len(set(opts)) == len(opts), f"duplicate type options: {opts}"


def test_issue_type_registry_enum_is_the_full_set():
    """The registry select sources from the same non-lossy option tuple."""
    spec = app._field_spec("issue_type")
    assert spec.editor == "select"
    assert spec.enum_options == app._ISSUE_TYPE_OPTIONS


# ---- (3) magic label decoding ----------------------------------------------


def test_prefix_magic_labels_decode_to_category_and_value():
    cases = {
        "dim:wcag": ("dim", "dim", "wcag"),
        "gt:merge": ("gate", "gt", "merge"),
        "provides:report": ("provides", "provides", "report"),
        "export:html": ("export", "export", "html"),
    }
    for raw, (category, prefix, value) in cases.items():
        decoded = app._decode_label(raw)
        assert decoded["category"] == category, raw
        assert decoded["prefix"] == prefix, raw
        assert decoded["value"] == value, raw
        assert decoded["kind_label"], raw  # carries a human label for a11y


def test_bare_template_flag_decodes_distinctly():
    decoded = app._decode_label("template")
    assert decoded["category"] == "template"
    assert decoded["prefix"] == ""  # no colon -> whole-string flag
    assert decoded["value"] == "template"


def test_freeform_tag_falls_back_to_tag_category():
    decoded = app._decode_label("anatomy")
    assert decoded["category"] == "tag"
    assert decoded["prefix"] == ""
    assert decoded["value"] == "anatomy"


def test_magic_categories_are_mutually_distinct():
    """Each known marker maps to its OWN category (visually differentiable)."""
    cats = {
        app._decode_label(x)["category"]
        for x in ("dim:a", "gt:b", "provides:c", "export:d", "template", "plain")
    }
    assert cats == {"dim", "gate", "provides", "export", "template", "tag"}


def test_decode_label_is_case_insensitive_on_prefix():
    assert app._decode_label("DIM:x")["category"] == "dim"
    assert app._decode_label("Template")["category"] == "template"


def test_decode_label_handles_none_and_empty():
    for val in (None, "", "   "):
        decoded = app._decode_label(val)
        assert decoded["category"] == "tag"  # safe freeform fallback, no crash


def test_unknown_prefix_is_a_freeform_tag():
    """A colon'd label whose prefix isn't magic stays a plain tag (not magic)."""
    decoded = app._decode_label("ns:something")
    assert decoded["category"] == "tag"
    assert decoded["value"] == "ns:something"


def test_decode_label_registered_as_jinja_filter():
    assert app.TEMPLATES.env.filters.get("decode_label") is app._decode_label


# ---- per-category chip styling exists --------------------------------------


def test_each_magic_chip_category_has_a_css_rule():
    """Every magic category gets its own chip style so they're distinct."""
    css = CSS_PATH.read_text(encoding="utf-8")
    for category in ("dim", "gate", "provides", "export", "template"):
        assert f".chip-{category}" in css, f"no .chip-{category} chip style"
    assert ".chip-tag" in css, "freeform tag chip style missing"
