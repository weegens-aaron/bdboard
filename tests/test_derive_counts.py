"""Test that status counts always render all statuses to prevent layout jitter.

in_progress is a first-class fixed masthead KPI: bdboard is a general-purpose
multi-WIP board, so any number of beads may be in progress concurrently. The
cell is always present (0, 1, or many) and matches the skeleton so the masthead
never reflows on hydration.
"""

from bdboard.derive import counts, lanes


def test_counts_returns_fixed_status_set_even_when_empty():
    """Empty bead list should still return all standard statuses with 0 counts."""
    result = counts([])

    # Fixed status order (in_progress is a first-class fixed cell)
    expected_keys = ["open", "in_progress", "blocked", "deferred", "closed"]
    assert list(result.keys()) == expected_keys

    # All values should be 0
    assert all(v == 0 for v in result.values())


def test_counts_includes_in_progress_as_fixed_cell():
    """in_progress is a fixed cell, present even when zero (no hydration jitter)."""
    # Zero in_progress: cell still present.
    result = counts([{"status": "open"}])
    assert "in_progress" in result
    assert result["in_progress"] == 0

    # Many in_progress: multi-WIP is first-class.
    beads = [{"status": "in_progress"} for _ in range(3)]
    result = counts(beads)
    assert result["in_progress"] == 3
    # Order is stable and in_progress is in the fixed set (not appended).
    assert list(result.keys()) == ["open", "in_progress", "blocked", "deferred", "closed"]


def test_counts_preserves_status_order_with_mixed_data():
    """Status order should be stable regardless of which statuses have counts."""
    beads = [
        {"status": "closed"},
        {"status": "open"},
        {"status": "blocked"},
        {"status": "open"},
    ]
    result = counts(beads)

    # Order should be stable (in_progress is a fixed cell)
    expected_keys = ["open", "in_progress", "blocked", "deferred", "closed"]
    assert list(result.keys()) == expected_keys

    # Verify counts
    assert result["open"] == 2
    assert result["in_progress"] == 0  # Zero, but still present
    assert result["blocked"] == 1
    assert result["deferred"] == 0  # Zero, but still present
    assert result["closed"] == 1


def test_counts_includes_custom_statuses_at_end():
    """Custom statuses should be appended after standard ones."""
    beads = [
        {"status": "open"},
        {"status": "custom_status"},
        {"status": "another_custom"},
    ]
    result = counts(beads)

    # Standard statuses come first (5 fixed cells)
    keys = list(result.keys())
    assert keys[:5] == ["open", "in_progress", "blocked", "deferred", "closed"]

    # Custom statuses at the end
    assert "custom_status" in keys[5:]
    assert "another_custom" in keys[5:]

    # Verify counts
    assert result["open"] == 1
    assert result["custom_status"] == 1
    assert result["another_custom"] == 1


def test_counts_case_insensitive():
    """Status matching should be case-insensitive."""
    beads = [
        {"status": "OPEN"},
        {"status": "CLOSED"},
        {"status": "BLOCKED"},
    ]
    result = counts(beads)

    assert result["open"] == 1
    assert result["closed"] == 1
    assert result["blocked"] == 1


# --- Epic exclusion (bdboard-6cov) -------------------------------------------
# Epics are containers, not WIP. lanes.py buckets only non-epics (epics live in
# the epic strip), so counts() must skip epics too or a KPI exceeds its lane.


def test_in_progress_epic_not_counted_in_in_progress_kpi():
    """An in_progress epic must NOT increment the in_progress masthead KPI.

    Regression for bdboard-6cov: feed.counts() tallied ALL beads with no epic
    filter while lanes.lanes() excludes epics, so an in_progress epic inflated
    the KPI above the In Progress lane card count.
    """
    beads = [
        {"id": "e1", "issue_type": "epic", "status": "in_progress"},
        {"id": "t1", "issue_type": "task", "status": "in_progress"},
    ]
    result = counts(beads)
    # Only the non-epic task is WIP; the epic is a container.
    assert result["in_progress"] == 1


def test_in_progress_kpi_equals_in_progress_lane_for_same_snapshot():
    """The in_progress KPI must equal the In Progress lane card count.

    This is the headline acceptance criterion for bdboard-6cov: KPI and lane
    are derived from the same snapshot and must agree.
    """
    beads = [
        {"id": "e1", "issue_type": "epic", "status": "in_progress"},
        {"id": "e2", "issue_type": "epic", "status": "in_progress"},
        {"id": "t1", "issue_type": "task", "status": "in_progress"},
        {"id": "t2", "issue_type": "bug", "status": "in_progress"},
        {"id": "t3", "issue_type": "task", "status": "open"},
    ]
    kpi = counts(beads)["in_progress"]
    lane_count = len(lanes(beads)["in_progress"])
    assert kpi == lane_count == 2


def test_epics_excluded_from_all_status_kpis_matches_lanes():
    """Mirroring the non_epics filter keeps EVERY KPI consistent with its lane.

    Not just in_progress: a closed epic isn't in the closed lane, an open epic
    isn't in ready, etc. So every overlapping status KPI must equal its lane.
    """
    beads = [
        {"id": "e1", "issue_type": "epic", "status": "in_progress"},
        {"id": "e2", "issue_type": "epic", "status": "closed"},
        {"id": "e3", "issue_type": "epic", "status": "open"},
        {"id": "t1", "issue_type": "task", "status": "in_progress"},
        {"id": "t2", "issue_type": "task", "status": "closed"},
        {"id": "t3", "issue_type": "task", "status": "open"},
        {"id": "t4", "issue_type": "task", "status": "blocked"},
    ]
    kpi = counts(beads)
    bucket = lanes(beads)
    assert kpi["in_progress"] == len(bucket["in_progress"]) == 1
    assert kpi["closed"] == len(bucket["closed"]) == 1
    assert kpi["open"] == len(bucket["ready"]) == 1
    assert kpi["blocked"] == len(bucket["blocked"]) == 1


def test_epic_exclusion_preserves_fixed_5_cell_geometry():
    """Excluding epics changes the tally only, never the fixed cell skeleton."""
    beads = [{"id": "e1", "issue_type": "epic", "status": "in_progress"}]
    result = counts(beads)
    assert list(result.keys())[:5] == [
        "open",
        "in_progress",
        "blocked",
        "deferred",
        "closed",
    ]
    # Epic dropped from the tally -> in_progress cell present but zero.
    assert result["in_progress"] == 0
