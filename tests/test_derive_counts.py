"""Test that status counts always render all statuses to prevent layout jitter.

Note: in_progress is intentionally excluded from masthead counts. bdboard is a
single-flight workflow tool — only one item is in-progress at a time, so
displaying 0 or 1 is noise. The In Progress swim lane already surfaces active work.
"""

from bdboard.derive import counts


def test_counts_returns_fixed_status_set_even_when_empty():
    """Empty bead list should still return all standard statuses with 0 counts."""
    result = counts([])

    # Fixed status order (in_progress intentionally omitted)
    expected_keys = ["open", "blocked", "deferred", "closed"]
    assert list(result.keys()) == expected_keys

    # All values should be 0
    assert all(v == 0 for v in result.values())


def test_counts_excludes_in_progress():
    """in_progress should not appear in standard status keys.

    Single-flight workflow: showing 0 or 1 is noise.
    """
    beads = [{"status": "in_progress"}]
    result = counts(beads)

    # in_progress is counted but appears as a 'custom' status at the end
    # (since it exists in the data but isn't in the standard order)
    assert list(result.keys())[:4] == ["open", "blocked", "deferred", "closed"]
    # The in_progress bead is still counted, but as a non-standard status
    assert result.get("in_progress") == 1


def test_counts_preserves_status_order_with_mixed_data():
    """Status order should be stable regardless of which statuses have counts."""
    beads = [
        {"status": "closed"},
        {"status": "open"},
        {"status": "blocked"},
        {"status": "open"},
    ]
    result = counts(beads)

    # Order should be stable (in_progress intentionally omitted)
    expected_keys = ["open", "blocked", "deferred", "closed"]
    assert list(result.keys()) == expected_keys

    # Verify counts
    assert result["open"] == 2
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

    # Standard statuses come first (4 now, not 5)
    keys = list(result.keys())
    assert keys[:4] == ["open", "blocked", "deferred", "closed"]

    # Custom statuses at the end
    assert "custom_status" in keys[4:]
    assert "another_custom" in keys[4:]

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
