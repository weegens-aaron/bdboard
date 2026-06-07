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
    """Genuinely unrecognized statuses should land in the deferred lane.

    This is the catch-all behavior: any status that doesn't match
    open/in_progress/blocked/closed/pinned and isn't a hidden machinery
    status lands in deferred. (pinned/hooked now have explicit handling —
    see test_pinned_* / test_hooked_* below.)
    """
    beads = [
        _bead("unknown-1", status="some_weird_status"),
        _bead("unknown-2", status="custom_status"),
        _bead("known-open", status="open"),
        _bead("known-closed", status="closed"),
    ]

    buckets = derive.lanes(beads)

    # Unknown statuses should be in deferred
    deferred_ids = {b["id"] for b in buckets["deferred"]}
    assert "unknown-1" in deferred_ids
    assert "unknown-2" in deferred_ids

    # Known statuses should be in their proper lanes
    assert "known-open" not in deferred_ids
    assert "known-closed" not in deferred_ids
    ready_ids = {b["id"] for b in buckets["ready"]}
    closed_ids = {b["id"] for b in buckets["closed"]}
    assert "known-open" in ready_ids
    assert "known-closed" in closed_ids


def test_pinned_status_gets_its_own_lane_not_deferred():
    """bdboard-m5bm: `pinned` (infra / never-auto-close) is explicitly bucketed
    into its own lane so it's visually distinct from intentionally-parked
    Deferred work — it must NOT fall through to the deferred catch-all."""
    beads = [
        _bead("pin-1", status="pinned"),
        _bead("defer-1", status="deferred"),
    ]

    buckets = derive.lanes(beads)

    pinned_ids = {b["id"] for b in buckets["pinned"]}
    deferred_ids = {b["id"] for b in buckets["deferred"]}
    assert pinned_ids == {"pin-1"}
    assert deferred_ids == {"defer-1"}
    # A pinned bead is NOT in the deferred lane.
    assert "pin-1" not in deferred_ids


def test_hooked_status_is_hidden_from_all_lanes():
    """bdboard-m5bm: `hooked` is bd-internal molecule/formula machinery, not a
    human work state. It's hidden from EVERY lane (like molecule wrappers),
    never dumped into Deferred."""
    beads = [
        _bead("hook-1", status="hooked"),
        _bead("open-1", status="open"),
    ]

    buckets = derive.lanes(beads)

    all_ids = {b["id"] for lane in buckets.values() for b in lane}
    assert "hook-1" not in all_ids  # hidden from every lane
    assert "open-1" in all_ids


def test_masthead_counts_agree_with_lanes():
    """bdboard-m5bm AC3: no masthead count without a matching lane.

    - `pinned` is surfaced as a count AND has a lane.
    - `hooked` is surfaced in NEITHER (hidden machinery).
    """
    beads = [
        _bead("pin-1", status="pinned"),
        _bead("hook-1", status="hooked"),
        _bead("open-1", status="open"),
    ]

    counts = derive.counts(beads)
    buckets = derive.lanes(beads)

    # pinned: counted AND laned.
    assert counts.get("pinned") == 1
    assert len(buckets["pinned"]) == 1

    # hooked: never counted, never laned.
    assert "hooked" not in counts
    assert all(b["id"] != "hook-1" for lane in buckets.values() for b in lane)


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
