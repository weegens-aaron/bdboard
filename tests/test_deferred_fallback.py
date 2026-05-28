"""Test that the Deferred lane serves as a catch-all for unknown statuses.

Regression test for bdboard-yed: after renaming backlog → deferred, the
Deferred lane must still catch any status that doesn't match the known
categories (open, in_progress, blocked, closed).
"""

from bdboard import derive


def _bead(
    bead_id: str,
    *,
    status: str = "open",
    issue_type: str = "task",
):
    return {
        "id": bead_id,
        "title": f"Title {bead_id}",
        "issue_type": issue_type,
        "status": status,
        "created_at": "2026-05-28T10:00:00Z",
        "updated_at": "2026-05-28T10:00:00Z",
    }


def test_deferred_status_lands_in_deferred_lane():
    """Beads with status='deferred' should land in the deferred lane."""
    beads = [
        _bead("deferred-1", status="deferred"),
        _bead("deferred-2", status="deferred"),
    ]

    buckets = derive.lanes(beads)

    assert len(buckets["deferred"]) == 2
    assert buckets["deferred"][0]["id"] == "deferred-1"
    assert buckets["deferred"][1]["id"] == "deferred-2"


def test_unknown_status_falls_back_to_deferred_lane():
    """Beads with unrecognized statuses should land in the deferred lane.

    This is the catch-all behavior: any status that doesn't match
    open/in_progress/blocked/closed lands in deferred.
    """
    beads = [
        _bead("unknown-1", status="some_weird_status"),
        _bead("unknown-2", status="custom_status"),
        _bead("unknown-3", status="hooked"),  # bd built-in but not yet handled
        _bead("unknown-4", status="pinned"),  # bd built-in but not yet handled
        _bead("known-open", status="open"),
        _bead("known-closed", status="closed"),
    ]

    buckets = derive.lanes(beads)

    # Unknown statuses should be in deferred
    deferred_ids = {b["id"] for b in buckets["deferred"]}
    assert "unknown-1" in deferred_ids
    assert "unknown-2" in deferred_ids
    assert "unknown-3" in deferred_ids
    assert "unknown-4" in deferred_ids

    # Known statuses should be in their proper lanes
    assert "known-open" not in deferred_ids
    assert "known-closed" not in deferred_ids
    ready_ids = {b["id"] for b in buckets["ready"]}
    closed_ids = {b["id"] for b in buckets["closed"]}
    assert "known-open" in ready_ids
    assert "known-closed" in closed_ids


def test_mixed_statuses_bucket_correctly():
    """Comprehensive test with all known statuses plus unknowns."""
    beads = [
        _bead("open-1", status="open"),
        _bead("in-progress-1", status="in_progress"),
        _bead("blocked-1", status="blocked"),
        _bead("deferred-1", status="deferred"),
        _bead("closed-1", status="closed"),
        _bead("resolved-1", status="resolved"),
        _bead("done-1", status="done"),
        _bead("unknown-1", status="unknown_status"),
    ]

    buckets = derive.lanes(beads)

    # Verify each lane has the correct beads
    ready_ids = {b["id"] for b in buckets["ready"]}
    in_progress_ids = {b["id"] for b in buckets["in_progress"]}
    blocked_ids = {b["id"] for b in buckets["blocked"]}
    deferred_ids = {b["id"] for b in buckets["deferred"]}
    closed_ids = {b["id"] for b in buckets["closed"]}

    assert "open-1" in ready_ids
    assert "in-progress-1" in in_progress_ids
    assert "blocked-1" in blocked_ids
    assert "deferred-1" in deferred_ids
    assert "unknown-1" in deferred_ids
    assert "closed-1" in closed_ids
    assert "resolved-1" in closed_ids
    assert "done-1" in closed_ids

    # Verify totals
    total_beads = (
        len(buckets["ready"])
        + len(buckets["in_progress"])
        + len(buckets["blocked"])
        + len(buckets["deferred"])
        + len(buckets["closed"])
    )
    assert total_beads == 8
