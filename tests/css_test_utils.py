"""Shared CSS parsing and WCAG contrast test utilities.

Provides reusable functions for extracting CSS properties, resolving CSS
variables, and computing WCAG 2.2 contrast ratios.
"""

from __future__ import annotations

import re


def parse_css_variables(css: str) -> dict[str, str]:
    """Extract :root custom properties from CSS.

    Args:
        css: CSS content as string

    Returns:
        Dictionary mapping variable names (with --) to their values
    """
    pattern = r":root\s*\{(?P<body>.*?)\}"
    match = re.search(pattern, css, re.DOTALL)
    if not match:
        return {}

    variables: dict[str, str] = {}
    root_block = match.group("body")
    for name, value in re.findall(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);", root_block):
        variables[name.strip()] = value.strip()
    return variables


def resolve_css_value(value: str, variables: dict[str, str]) -> str:
    """Resolve CSS value, including var() references recursively.

    Args:
        value: CSS value (may contain var() references)
        variables: Dictionary of CSS variable names to values

    Returns:
        Resolved value with all var() references expanded
    """
    value = value.strip()

    # If it's already a literal value (hex color, etc.), return it
    if not value.startswith("var("):
        return value

    # Parse var() syntax: var(--name) or var(--name, fallback)
    var_pattern = r"var\((--[a-zA-Z0-9_-]+)(?:\s*,\s*([^\)]+))?\)"
    var_match = re.fullmatch(var_pattern, value)
    if not var_match:
        return value  # Not a valid var() reference

    var_name, fallback = var_match.groups()

    # Try to resolve the variable
    if var_name in variables:
        resolved = variables[var_name]
        # Recursively resolve in case the variable value is itself a var()
        return resolve_css_value(resolved, variables)

    # Use fallback if variable not found
    if fallback:
        return resolve_css_value(fallback, variables)

    # No variable and no fallback - return original
    return value


def extract_style_property(
    css: str, selector: str, property: str, variables: dict[str, str] | None = None
) -> str | None:
    """Extract and resolve a CSS property value from a selector.

    Args:
        css: CSS content as string
        selector: CSS selector (e.g., ".filter-badge", ".epic-status.status-open")
        property: CSS property name (e.g., "color", "background")
        variables: Optional pre-parsed CSS variables; if None, will parse from css

    Returns:
        Resolved property value, or None if selector or property not found
    """
    # Find the selector block
    # Escape special regex chars in selector, but preserve spaces ano-selectors
    escaped_selector = re.escape(selector).replace(r"\ ", r"\s+")
    pattern = escaped_selector + r"\s*\{([^}]+)\}"
    match = re.search(pattern, css)
    if not match:
        return None

    block = match.group(1)

    # Find the property
    prop_pattern = re.escape(property) + r"\s*:\s*([^;]+);"
    prop_match = re.search(prop_pattern, block)
    if not prop_match:
        return None

    value = prop_match.group(1).strip()

    # Resolve CSS variables if present
    if value.startswith("var("):
        if variables is None:
            variables = parse_css_variables(css)
        value = resolve_css_value(value, variables)

    return value


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Convert #rrggbb hex color to (r, g, b) tuple.

    Args:
        color: Hex color string (e.g., "#ff0000" or "ff0000")

    Returns:
        RGB tuple with values 0-255
    """
    color = color.strip().lstrip("#")
    if len(color) != 6:
        raise ValueError(f"Expected #RRGGBB color, got: {color!r}")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def relative_luminance(color: str) -> float:
    """Compute relative luminance per WCAG definition.

    Args:
        color: Hex color string (e.g., "#ff0000")

    Returns:
        Relative luminance value (0.0 to 1.0)
    """
    r, g, b = (c / 255.0 for c in hex_to_rgb(color))

    def _linearize(channel: float) -> float:
        if channel <= 0.03928:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    r_lin = _linearize(r)
    g_lin = _linearize(g)
    b_lin = _linearize(b)

    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(foreground: str, background: str) -> float:
    """Compute WCAG contrast ratio between foreground and background colors.

    Args:
        foreground: Hex color string for text/foreground
        background: Hex color string for background

    Returns:
        Contrast ratio (1.0 to 21.0)
    """
    l1 = relative_luminance(foreground)
    l2 = relative_luminance(background)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)
