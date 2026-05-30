"""Shared CSS parsing utilities for test suite.

Provides reusable functions for extracting CSS properties and resolving CSS
variables. For WCAG contrast calculations, use wcag_utils module.
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


def parse_css_variables_for_block(css: str, selector: str) -> dict[str, str]:
    """Extract custom properties declared inside a specific selector block.

    Unlike :root parsing, this targets an arbitrary selector (e.g. the dark
    theme override block ``:root[data-theme="dark"]``) so tests can validate
    theme-specific token values.

    Args:
        css: CSS content as string
        selector: The selector whose block to read (literal text, will be
            regex-escaped). Example: ':root[data-theme="dark"]'

    Returns:
        Dictionary mapping variable names (with --) to their declared values.
        Empty dict if the selector block is not found.
    """
    pattern = re.escape(selector) + r"\s*\{(?P<body>.*?)\}"
    match = re.search(pattern, css, re.DOTALL)
    if not match:
        return {}

    variables: dict[str, str] = {}
    for name, value in re.findall(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);", match.group("body")):
        variables[name.strip()] = value.strip()
    return variables


def dark_theme_variables(css: str) -> dict[str, str]:
    """Resolve the full token table as seen under the dark theme.

    The dark theme only re-declares the tokens it changes; everything else
    inherits from :root. This layers the ``:root[data-theme="dark"]`` block
    on top of the base :root so callers get the fully-resolved dark palette
    (the single source of truth the browser would compute).

    Args:
        css: CSS content as string

    Returns:
        Merged variable dict (base :root overridden by dark-theme block).
    """
    merged = parse_css_variables(css)
    merged.update(parse_css_variables_for_block(css, ':root[data-theme="dark"]'))
    return merged


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
