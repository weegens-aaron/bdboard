"""WCAG 2.2 contrast calculation utilities.

Provides pure WCAG contrast ratio calculations following the WCAG 2.2
specification for relative luminance and contrast ratio formulas.

Reference: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
"""

from __future__ import annotations


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple.

    Args:
        hex_color: Hex color string (e.g., "#ff0000" or "ff0000")

    Returns:
        RGB tuple with values 0-255

    Raises:
        ValueError: If hex_color is not a valid 6-character hex color

    Examples:
        >>> hex_to_rgb("#ff0000")
        (255, 0, 0)
        >>> hex_to_rgb("00ff00")
        (0, 255, 0)
    """
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Expected 6-character hex color, got: {hex_color!r}")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Calculate relative luminance per WCAG 2.2 formula.

    Args:
        rgb: RGB tuple with values 0-255

    Returns:
        Relative luminance value (0.0 to 1.0)

    The formula is:
        L = 0.2126 * R + 0.7152 * G + 0.0722 * B
    where R, G, B are the linearized sRGB components.

    Examples:
        >>> relative_luminance((255, 255, 255))  # white
        1.0
        >>> relative_luminance((0, 0, 0))  # black
        0.0
    """
    # Normalize to 0-1 range
    r, g, b = (c / 255.0 for c in rgb)

    def _linearize_component(component: float) -> float:
        """Convert sRGB component to linear RGB."""
        if component <= 0.03928:
            return component / 12.92
        return ((component + 0.055) / 1.055) ** 2.4

    # Linearize each component
    r_linear = _linearize_component(r)
    g_linear = _linearize_component(g)
    b_linear = _linearize_component(b)

    # Apply WCAG luminance coefficients
    return 0.2126 * r_linear + 0.7152 * g_linear + 0.0722 * b_linear


def contrast_ratio(
    fg: str | tuple[int, int, int], bg: str | tuple[int, int, int]
) -> float:
    """Calculate WCAG 2.2 contrast ratio between foreground and background.

    Args:
        fg: Foreground color as hex string or RGB tuple
        bg: Background color as hex string or RGB tuple

    Returns:
        Contrast ratio (1.0 to 21.0)

    The WCAG formula is:
        (L1 + 0.05) / (L2 + 0.05)
    where L1 is the lighter luminance and L2 is the darker luminance.

    WCAG AA requirements:
        - Normal text: 4.5:1 minimum
        - Large text (18pt+ or 14pt+ bold): 3:1 minimum

    Examples:
        >>> contrast_ratio("#ffffff", "#000000")  # white on black
        21.0
        >>> contrast_ratio((255, 255, 255), (0, 0, 0))  # same, with tuples
        21.0
        >>> contrast_ratio("#0053e2", "#ffffff")  # Walmart blue on white
        # Should be > 4.5 for WCAG AA compliance
    """
    # Convert to RGB tuples if needed
    fg_rgb = hex_to_rgb(fg) if isinstance(fg, str) else fg
    bg_rgb = hex_to_rgb(bg) if isinstance(bg, str) else bg

    # Calculate luminance for each
    lum_fg = relative_luminance(fg_rgb)
    lum_bg = relative_luminance(bg_rgb)

    # WCAG formula: lighter and darker
    lighter = max(lum_fg, lum_bg)
    darker = min(lum_fg, lum_bg)

    return (lighter + 0.05) / (darker + 0.05)
