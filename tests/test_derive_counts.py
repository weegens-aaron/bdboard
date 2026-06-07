"""Test that status counts always render all statuses to prevent layout jitter.

in_progress is a first-class fixed masthead KPI: bdboard is a general-purpose
multi-WIP board, so any number of beads may be in progress concurrently. The
cell is always present (0, 1, or many) and matches the skeleton so the masthead
never reflows on hydration.
"""

from bdboard.derive import counts


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
