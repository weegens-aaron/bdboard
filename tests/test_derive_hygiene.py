"""Tests for graph-hygiene badges (audit FB-6 / bdboard-dzu2).

bdboard surfaced zero graph-hygiene signals: a deadlocked dependency cycle, a
`blocks` edge pointing at a target absent from the snapshot, and a structurally
incomplete bead (e.g. a bug with no *Steps to Reproduce*) all rendered exactly
like healthy work. These tests lock the three derived badges:

1. cycle / deadlock      -> ``cycle_member_ids`` / ``hygiene_cycle``
2. blocked-by-missing    -> ``blocked_reason`` / ``hygiene_blocked_reason``
   (distinct from blocked-by-open)
3. incomplete template   -> ``incomplete_sections`` / ``hygiene_incomplete``
"""

from __future__ import annotations

from bdboard import derive
from bdboard.derive import hygiene


def _bead(
    bead_id: str,
    *,
    status: str = "open",
    issue_type: str = "task",
    deps: list[dict] | None = None,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    notes: str | None = None,
    created_at: str = "2026-06-07T00:00:00Z",
):
    b: dict = {
        "id": bead_id,
        "title": f"Bead {bead_id}",
        "issue_type": issue_type,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
    }
    if deps is not None:
        b["dependencies"] = deps
    if description is not None:
        b["description"] = description
    if acceptance_criteria is not None:
        b["acceptance_criteria"] = acceptance_criteria
    if notes is not None:
        b["notes"] = notes
    return b


def _blocks(target_id: str) -> dict:
    return {"depends_on_id": target_id, "type": "blocks"}


# ── 1. cycle detection ─────────────────────────────────────────────────────


def test_two_bead_blocking_cycle_flags_both():
    a = _bead("A", deps=[_blocks("B")])
    b = _bead("B", deps=[_blocks("A")])
    assert hygiene.cycle_member_ids([a, b]) == {"A", "B"}


def test_three_bead_cycle_flags_all():
    a = _bead("A", deps=[_blocks("B")])
    b = _bead("B", deps=[_blocks("C")])
    c = _bead("C", deps=[_blocks("A")])
    assert hygiene.cycle_member_ids([a, b, c]) == {"A", "B", "C"}


def test_acyclic_chain_has_no_cycle_members():
    a = _bead("A", deps=[_blocks("B")])
    b = _bead("B", deps=[_blocks("C")])
    c = _bead("C")
    assert hygiene.cycle_member_ids([a, b, c]) == set()


def test_node_downstream_of_cycle_is_not_flagged():
    """A bead depending on a cycle member is NOT itself on the cycle."""
    a = _bead("A", deps=[_blocks("B")])
    b = _bead("B", deps=[_blocks("A")])
    d = _bead("D", deps=[_blocks("A")])  # downstream, not on the cycle
    members = hygiene.cycle_member_ids([a, b, d])
    assert members == {"A", "B"}
    assert "D" not in members


def test_self_loop_is_a_cycle():
    a = _bead("A", deps=[_blocks("A")])
    assert hygiene.cycle_member_ids([a]) == {"A"}


def test_waits_for_edges_do_not_form_a_cycle():
    """A `waits-for` fanout resolves against children, never a 2-bead cycle."""
    a = _bead("A", deps=[{"depends_on_id": "B", "type": "waits-for"}])
    b = _bead("B", deps=[{"depends_on_id": "A", "type": "waits-for"}])
    assert hygiene.cycle_member_ids([a, b]) == set()


def test_edge_to_absent_target_is_not_a_cycle():
    a = _bead("A", deps=[_blocks("ghost")])
    assert hygiene.cycle_member_ids([a]) == set()


# ── 2. blocked-by-missing vs blocked-by-open ───────────────────────────────


def test_blocked_by_open_target():
    a = _bead("A", deps=[_blocks("B")])
    b = _bead("B", status="open")
    present = {"A": a, "B": b}
    assert hygiene.blocked_reason(a, present) == "open"


def test_blocked_by_missing_target():
    a = _bead("A", deps=[_blocks("ghost")])
    present = {"A": a}
    assert hygiene.blocked_reason(a, present) == "missing"


def test_satisfied_when_target_closed():
    a = _bead("A", deps=[_blocks("B")])
    b = _bead("B", status="closed")
    present = {"A": a, "B": b}
    assert hygiene.blocked_reason(a, present) is None


def test_missing_dominates_open():
    """A dangling edge is the more serious defect and wins the classification."""
    a = _bead("A", deps=[_blocks("B"), _blocks("ghost")])
    b = _bead("B", status="open")
    present = {"A": a, "B": b}
    assert hygiene.blocked_reason(a, present) == "missing"


def test_known_ids_keeps_closed_unfetched_target_from_reading_as_dangling():
    """A target absent from the snapshot but in known_ids is not an orphan."""
    a = _bead("A", deps=[_blocks("closed-elsewhere")])
    present = {"A": a}  # target not in this snapshot
    # Without known_ids -> snapshot-relative -> reads as missing.
    assert hygiene.blocked_reason(a, present) == "missing"
    # With the target in the broader universe -> treated as satisfied.
    assert hygiene.blocked_reason(a, present, known_ids={"A", "closed-elsewhere"}) is None


# ── 3. incomplete template ─────────────────────────────────────────────────


def test_bug_missing_repro_section_is_incomplete():
    bug = _bead("A", issue_type="bug", description="Something is broken.")
    missing = hygiene.incomplete_sections(bug)
    assert "Steps to Reproduce" in missing


def test_complete_bug_has_no_missing_sections():
    body = (
        "## Steps to Reproduce\n1. do x\n\n"
        "## Expected Behavior\nworks\n\n"
        "## Actual Behavior\nbreaks\n"
    )
    bug = _bead("A", issue_type="bug", description=body)
    assert hygiene.incomplete_sections(bug) == []


def test_acceptance_criteria_field_satisfies_section():
    """A populated `acceptance_criteria` field counts even with no heading."""
    task = _bead("A", issue_type="task", description="do the thing", acceptance_criteria="it works")
    assert hygiene.incomplete_sections(task) == []


def test_task_without_acceptance_is_incomplete():
    task = _bead("A", issue_type="task", description="do the thing")
    assert hygiene.incomplete_sections(task) == ["Acceptance Criteria"]


def test_heading_match_is_substring_tolerant():
    body = "## Steps To Reproduce (manual)\n...\n## Expected Behavior\n.\n## Actual Behavior\n."
    bug = _bead("A", issue_type="bug", description=body)
    assert hygiene.incomplete_sections(bug) == []


def test_section_can_live_in_notes():
    task = _bead("A", issue_type="task", description="x", notes="## Acceptance Criteria\nok")
    assert hygiene.incomplete_sections(task) == []


def test_type_without_template_requirement_is_never_incomplete():
    chore = _bead("A", issue_type="chore", description="")
    assert hygiene.incomplete_sections(chore) == []


# ── with_badges + lane/epic integration ────────────────────────────────────


def test_with_badges_grafts_all_three_fields_on_a_copy():
    a = _bead("A", issue_type="bug", deps=[_blocks("ghost")], description="x")
    out = hygiene.with_badges(a, present={"A": a}, cycle_ids=set())
    assert out is not a  # never mutate the cached snapshot dict
    assert "hygiene_cycle" not in a
    assert out["hygiene_cycle"] is False
    assert out["hygiene_blocked_reason"] == "missing"
    assert out["hygiene_incomplete"] == [
        "Steps to Reproduce",
        "Expected Behavior",
        "Actual Behavior",
    ]


def test_lanes_decorate_cards_with_cycle_badge():
    a = _bead("A", status="blocked", deps=[_blocks("B")])
    b = _bead("B", status="blocked", deps=[_blocks("A")])
    buckets = derive.lanes([a, b])
    blocked = {x["id"]: x for x in buckets["blocked"]}
    assert blocked["A"]["hygiene_cycle"] is True
    assert blocked["B"]["hygiene_cycle"] is True


def test_lanes_distinguish_missing_from_open_blocker():
    open_blocked = _bead("A", status="open", deps=[_blocks("B")])
    b = _bead("B", status="open")
    dangling = _bead("C", status="open", deps=[_blocks("ghost")])
    buckets = derive.lanes([open_blocked, b, dangling])
    by_id = {x["id"]: x for x in buckets["blocked"]}
    assert by_id["A"]["hygiene_blocked_reason"] == "open"
    assert by_id["C"]["hygiene_blocked_reason"] == "missing"


def test_epic_lane_carries_hygiene_fields():
    a = _bead("A", issue_type="epic", status="open", deps=[_blocks("B")])
    b = _bead("B", issue_type="epic", status="open", deps=[_blocks("A")])
    strip = derive.epic_lane([a, b])
    by_id = {e["id"]: e for e in strip}
    assert by_id["A"]["hygiene_cycle"] is True
    assert "hygiene_blocked_reason" in by_id["A"]


def test_known_ids_threads_through_lanes():
    """A blocks-target outside the snapshot but in known_ids isn't dangling."""
    a = _bead("A", status="open", deps=[_blocks("done-long-ago")])
    buckets = derive.lanes([a], known_ids={"A", "done-long-ago"})
    by_id = {x["id"]: x for x in buckets["blocked"] + buckets["ready"]}
    # known_ids resolves the target as satisfied -> no dangling badge (the lane
    # bucketing itself stays conservative without known_ids, so A may still sit
    # in Blocked; the point is the hygiene reason is not "missing").
    assert by_id["A"]["hygiene_blocked_reason"] is None
