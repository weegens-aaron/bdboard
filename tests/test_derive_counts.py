"""Test that status counts always render all statuses to prevent layout jitter."""

from bdboard.derive import counts


def test_counts_returns_fixed_status_set_even_when_empty():
    """Empty bead list should still return all standard statuses with 0 counts."""
    result = counts([])

    # Fixed status order
    expected_keys = ["open", "in_progress", "blocked", "deferred", "closed"]
    assert list(result.keys()) == expected_keys

    # All values should be 0
    assert all(v == 0 for v in result.values())


def test_counts_preserves_status_order_with_mixed_data():
    """Status order should be stable regardless of which statuses have counts."""
    beads = [
        {"status": "closed"},
        {"status": "open"},
        {"status": "blocked"},
        {"status": "open"},
    ]
    result = counts(beads)

    # Order should be stable
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

    # Standard statuses come first
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
        {"status": "In_Progress"},
        {"status": "CLOSED"},
    ]
    result = counts(beads)

    assert result["open"] == 1
    assert result["in_progress"] == 1
    assert result["closed"] == 1
