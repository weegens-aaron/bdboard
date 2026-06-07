"""Tests for `waits-for` fanout edges as blocking edges in lane derivation.

bd recognizes TWO blocking edge types (field guide ch2 §2.4 / ch6 §VI):
`blocks`/`blocked-by` (direct: the single target must close) and `waits-for`
(fanout: the waiter waits on the SPAWNER's children, default `all-children`
aggregation). Before bdboard-zcfc, `_has_unmet_blocking_dep` gated only on the
direct set, so a bead gated *solely* by an unmet `waits-for` edge was computed
`ready` and rendered in the READY lane while bd excludes it from `bd ready` —
the textbook blocked-shown-as-ready P0 (same class as the reversed-dep
bdboard-fjk).

Locked here:

1. A bead with an unmet `waits-for` edge (spawner has an open child) lanes as
   Blocked, not Ready — in both the swim lanes and the epic strip.
2. A `waits-for` bead whose spawner is childless (or all children closed) stays
   Ready (vacuous-satisfy) — matching bd's own `bd ready`.
3. The vacuous edge cases (missing spawner, no children index) degrade to
   Ready rather than inventing a phantom blocker.

Field shapes verified against bd v1.0.5: a `waits-for` edge stores
`dependency_type: "waits-for"`; the child->parent link rides on each child's
`parent` field (`bd show --json` carries `"parent": "<id>"`).
"""

from __future__ import annotations

from bdboard import derive
from bdboard.derive.lanes import _has_unmet_blocking_dep, _waits_for_unmet


def _task(
    task_id: str,
    *,
    status: str = "open",
    issue_type: str = "task",
    parent: str | None = None,
    deps: list[dict] | None = None,
    created_at: str = "2026-06-07T00:00:00Z",
):
    bead: dict = {
        "id": task_id,
        "title": f"Task {task_id}",
        "issue_type": issue_type,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
    }
    if parent is not None:
        bead["parent"] = parent
    if deps is not None:
        bead["dependencies"] = deps
    return bead


def _waits_for(spawner_id: str) -> list[dict]:
    """A single `waits-for` fanout edge pointing at `spawner_id`."""
    return [{"depends_on_id": spawner_id, "type": "waits-for"}]


# ----- _waits_for_unmet (the fanout resolver) -----


def test_waits_for_unmet_when_spawner_has_open_child():
    """Spawner with an open child -> the waiter is functionally blocked."""
    children = {"A": [_task("c1", status="open")]}
    assert _waits_for_unmet("A", children) is True


def test_waits_for_satisfied_when_spawner_childless():
    """Childless spawner -> vacuously satisfied (waiter genuinely ready)."""
    assert _waits_for_unmet("A", {}) is False


def test_waits_for_satisfied_when_all_children_closed():
    """A spawner whose every child is closed is satisfied (vacuous edge)."""
    children = {"A": [_task("c1", status="closed"), _task("c2", status="done")]}
    assert _waits_for_unmet("A", children) is False


def test_waits_for_unmet_with_mixed_children():
    """One open child among closed ones still blocks (all-children default)."""
    children = {"A": [_task("c1", status="closed"), _task("c2", status="open")]}
    assert _waits_for_unmet("A", children) is True


def test_waits_for_satisfied_with_no_spawner_id():
    assert _waits_for_unmet(None, {"A": [_task("c1")]}) is False


def test_waits_for_satisfied_with_no_index():
    """No children index available -> don't invent a phantom blocker."""
    assert _waits_for_unmet("A", None) is False


# ----- _has_unmet_blocking_dep integration -----


def test_has_unmet_blocking_dep_honors_waits_for():
    waiter = _task("B", deps=_waits_for("A"))
    children = {"A": [_task("c1", status="open")]}
    assert _has_unmet_blocking_dep(waiter, {"B": waiter}, children) is True


def test_has_unmet_blocking_dep_waits_for_vacuous():
    waiter = _task("B", deps=_waits_for("A"))
    assert _has_unmet_blocking_dep(waiter, {"B": waiter}, {}) is False


def test_has_unmet_blocking_dep_direct_blocks_still_works():
    """The original `blocks` path is unaffected by the waits-for addition."""
    waiter = _task("B", deps=[{"depends_on_id": "A", "type": "blocks"}])
    by_id = {"B": waiter, "A": _task("A", status="open")}
    assert _has_unmet_blocking_dep(waiter, by_id, {}) is True
    by_id["A"]["status"] = "closed"
    assert _has_unmet_blocking_dep(waiter, by_id, {}) is False


# ----- lanes(): the canonical board-vs-bd disagreement -----


def test_waiter_with_open_spawner_children_lanes_as_blocked():
    """AC1 (repro): waiter on a spawner with open children -> BLOCKED, not READY.

    Mirrors the bead's repro: `bd dep add B A -t waits-for` where A is an open
    spawner with an open child. bd drops B from `bd ready`; the board must too.
    """
    spawner = _task("A", status="in_progress", issue_type="epic")
    child = _task("c1", status="open", parent="A")
    waiter = _task("B", deps=_waits_for("A"))
    buckets = derive.lanes([spawner, child, waiter])

    assert "B" in {b["id"] for b in buckets["blocked"]}
    assert "B" not in {b["id"] for b in buckets["ready"]}


def test_waiter_with_childless_spawner_lanes_as_ready():
    """AC2: childless spawner -> waiter stays READY (vacuous-satisfy)."""
    spawner = _task("A", status="in_progress", issue_type="epic")  # no children
    waiter = _task("B", deps=_waits_for("A"))
    buckets = derive.lanes([spawner, waiter])

    assert "B" in {b["id"] for b in buckets["ready"]}
    assert "B" not in {b["id"] for b in buckets["blocked"]}


def test_waiter_with_all_children_closed_lanes_as_ready():
    """All spawner children closed -> waiter becomes READY (vacuous-satisfy)."""
    spawner = _task("A", status="in_progress", issue_type="epic")
    child = _task("c1", status="closed", parent="A")
    waiter = _task("B", deps=_waits_for("A"))
    buckets = derive.lanes([spawner, child, waiter])

    assert "B" in {b["id"] for b in buckets["ready"]}


def test_spawner_may_be_non_epic():
    """A spawner can be any type; the children index spans all beads."""
    spawner = _task("A", status="open")  # plain task spawner
    child = _task("c1", status="open", parent="A")
    waiter = _task("B", deps=_waits_for("A"))
    buckets = derive.lanes([spawner, child, waiter])
    assert "B" in {b["id"] for b in buckets["blocked"]}


# ----- epic_lane(): the strip must mirror the same readiness -----


def test_epic_strip_waits_for_marks_waiter_blocked():
    """An open epic gated by an unmet waits-for edge shows status_key=blocked."""
    spawner = _task("A", status="in_progress", issue_type="epic")
    child = _task("c1", status="open", parent="A")
    waiter = _task("B", status="open", issue_type="epic", deps=_waits_for("A"))
    strip = derive.epic_lane([spawner, child, waiter])

    by_id = {b["id"]: b for b in strip}
    assert by_id["B"]["status_key"] == "blocked"


def test_epic_strip_waits_for_vacuous_stays_open():
    """A childless spawner leaves the waiter epic READY (status_key=open)."""
    spawner = _task("A", status="in_progress", issue_type="epic")
    waiter = _task("B", status="open", issue_type="epic", deps=_waits_for("A"))
    strip = derive.epic_lane([spawner, waiter])

    by_id = {b["id"]: b for b in strip}
    assert by_id["B"]["status_key"] == "open"
