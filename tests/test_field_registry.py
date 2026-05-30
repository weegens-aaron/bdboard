"""Tests for the field editability registry + _ordered_fields hints.

Covers bdboard-o9v.1: a single source-of-truth field registry mapping each
bd field key to its edit affordances, and _ordered_fields() decorating each
modal field row with editable/editor hints. This bead ships the REGISTRY +
HINTS only — there is deliberately NO write path and NO UI, so these tests
assert structure and policy, not any `bd update` invocation.
"""

from bdboard import app


def _bead(**overrides):
    """A minimal but field-rich bead dict, like bd show --json would emit."""
    base = {
        "id": "bdboard-x1",
        "title": "Some title",
        "description": "Some **markdown** body",
        "acceptance_criteria": "- does the thing",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "assignee": "Aaron",
        "external_ref": "JIRA-1",
        "estimate": 30,
        "story_points": 3,
        "created_at": "2026-05-28T10:00:00Z",
        "updated_at": "2026-05-28T10:00:00Z",
        "labels": ["backend"],
        "notes": "verification evidence here",
    }
    base.update(overrides)
    return base


def _rows_by_key(bead):
    return {r["key"]: r for r in app._ordered_fields(bead)}


# ---- registry shape & policy ------------------------------------------------


def test_registry_is_single_source_of_truth():
    """Every registry entry is a FieldSpec; editable entries carry a flag."""
    assert app._FIELD_REGISTRY, "registry must not be empty"
    for key, spec in app._FIELD_REGISTRY.items():
        assert isinstance(spec, app.FieldSpec)
        if spec.editable:
            assert spec.flag, f"{key}: editable field must declare a bd flag"
            assert spec.editor in {
                "text",
                "textarea",
                "md",
                "select",
                "number",
            }, f"{key}: unknown editor kind {spec.editor!r}"


def test_field_spec_is_frozen():
    """The spec is immutable so the registry can't be mutated at runtime."""
    spec = app._FIELD_REGISTRY["title"]
    import dataclasses

    try:
        spec.editable = False  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guard
        raise AssertionError("FieldSpec should be frozen/immutable")


def test_unknown_field_defaults_to_readonly():
    """Fields not in the registry are non-editable (safe default)."""
    spec = app._field_spec("some_field_nobody_whitelisted")
    assert spec.editable is False
    assert spec.flag is None
    assert spec.editor is None


def test_v1_whitelist_is_editable():
    """The spike §5 v1 field set is marked editable with the right flags."""
    expected = {
        "title": "--title",
        "description": "--description",
        "acceptance_criteria": "--acceptance",
        "design": "--design",
        "priority": "--priority",
        "assignee": "--assignee",
        "issue_type": "--type",
        "external_ref": "--external-ref",
        "estimate": "--estimate",
    }
    for key, flag in expected.items():
        spec = app._field_spec(key)
        assert spec.editable, f"{key} should be editable"
        assert spec.flag == flag


def test_out_of_scope_fields_are_readonly():
    """Shape/graph/lifecycle/derived fields must NOT be editable (spike §3)."""
    for key in (
        "id",
        "status",
        "parent",
        "labels",
        "metadata",
        "story_points",  # no bd update flag exists at all
        "created_at",
        "updated_at",
        "created_by",
        "dependency_count",
        "comments",
    ):
        assert app._field_spec(key).editable is False, f"{key} must be read-only"


def test_notes_is_append_only():
    """notes is editable but append-only — replace would nuke agent history."""
    spec = app._field_spec("notes")
    assert spec.editable is True
    assert spec.append_only is True
    assert spec.flag == "--append-notes"


def test_select_fields_carry_enum_options():
    """select editors expose options server-side so the dropdown can't drift."""
    for key in ("priority", "issue_type"):
        spec = app._field_spec(key)
        assert spec.editor == "select"
        assert spec.enum_options, f"{key} select must declare enum_options"

    non_select = app._field_spec("title")
    assert non_select.enum_options is None


# ---- _ordered_fields hint wiring -------------------------------------------


def test_ordered_fields_adds_editability_hints():
    """Every row gains editable/editor/flag/enum_options/append_only hints."""
    rows = app._ordered_fields(_bead())
    assert rows
    for row in rows:
        for hint in ("editable", "editor", "flag", "enum_options", "append_only"):
            assert hint in row, f"row {row['key']} missing hint {hint}"


def test_ordered_fields_editable_flag_matches_registry():
    rows = _rows_by_key(_bead())
    assert rows["title"]["editable"] is True
    assert rows["title"]["editor"] == "text"
    assert rows["title"]["flag"] == "--title"
    # read-only field
    assert rows["story_points"]["editable"] is False
    assert rows["story_points"]["editor"] is None


def test_ordered_fields_notes_hint_is_append_only():
    rows = _rows_by_key(_bead())
    assert rows["notes"]["editable"] is True
    assert rows["notes"]["append_only"] is True


def test_unknown_bead_field_row_is_readonly():
    """A field bd emits that isn't in the registry still renders read-only."""
    rows = _rows_by_key(_bead(some_new_bd_field="hello"))
    assert rows["some_new_bd_field"]["editable"] is False
    assert rows["some_new_bd_field"]["flag"] is None


def test_ordered_fields_preserves_existing_render_hints():
    """Adding edit hints must not drop the pre-existing kind/short_meta hints."""
    rows = _rows_by_key(_bead())
    assert rows["description"]["kind"] == "markdown"
    assert rows["priority"]["short_meta"] is True
    assert "val" in rows["title"]
