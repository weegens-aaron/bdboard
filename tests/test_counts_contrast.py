"""Test WCAG 2.2 AA contrast compliance for status count de-emphasis."""

from wcag_utils import contrast_ratio


def test_zero_count_value_meets_wcag_aa_for_large_text():
    """
    Zero-count values use --muted (#74767c) on white background.

    WCAG 2.2 AA requires:
    - Large text (18pt+ or 14pt+ bold): 3:1 contrast ratio

    The count value is 24px (18pt), qualifying as large text.
    """
    value_color = "#74767c"  # var(--muted) = var(--gray-100)
    bg_color = "#ffffff"  # white background

    ratio = contrast_ratio(value_color, bg_color)

    # Should meet 3:1 for large text
    assert ratio >= 3.0, (
        f"Zero-count value contrast {ratio:.2f}:1 fails WCAG AA large text (3:1). "
        f"Color: {value_color} on {bg_color}"
    )


def test_zero_count_label_meets_wcag_aa_for_small_text():
    """
    Zero-count labels use --muted (#74767c) on white background.

    WCAG 2.2 AA requires:
    - Small text (under 18pt / under 14pt bold): 4.5:1 contrast ratio

    The count label is 10px small text, so it must meet the 4.5:1 threshold.
    """
    label_color = "#74767c"  # var(--muted) = var(--gray-100)
    bg_color = "#ffffff"  # white background

    ratio = contrast_ratio(label_color, bg_color)

    # Must meet 4.5:1 for small text
    assert ratio >= 4.5, (
        f"Zero-count label contrast {ratio:.2f}:1 fails WCAG AA small text (4.5:1). "
        f"Color: {label_color} on {bg_color}"
    )


def test_populated_count_value_high_contrast():
    """
    Populated counts use --ink (#2e2f32) which should have excellent contrast.
    """
    ink_color = "#2e2f32"  # var(--ink) = var(--gray-160)
    bg_color = "#ffffff"

    ratio = contrast_ratio(ink_color, bg_color)

    # Should far exceed WCAG AAA (7:1) for normal text
    assert ratio >= 7.0, (
        f"Populated count contrast {ratio:.2f}:1 should exceed AAA threshold. "
        f"Color: {ink_color} on {bg_color}"
    )
