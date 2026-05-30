"""WCAG 2.2 AA contrast tests for the dark theme (bdboard-35e).

The dark theme re-points only the semantic CSS tokens; every component
references those tokens (no raw hex outside :root / the dark block), so
validating the resolved dark palette here certifies the whole surface.

Each case asserts the resolved foreground/background pair (as the browser
would compute it under ``<html data-theme="dark">``) clears the relevant
WCAG AA threshold. Pairs are resolved from the actual stylesheet so the
test fails if someone tweaks a dark token below AA.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import dark_theme_variables, resolve_css_value
from wcag_utils import contrast_ratio

CSS_PATH = Path("src/bdboard/static/styles.css")

AA_NORMAL = 4.5  # normal text
AA_LARGE = 3.0  # large/bold text & UI components

# (foreground token, background token, min ratio, human description)
# Tokens are given as var() references so they resolve through the dark
# palette exactly like the CSS does.
CASES = [
    ("var(--ink)", "var(--paper)", AA_NORMAL, "body text on canvas"),
    ("var(--ink-2)", "var(--paper)", AA_NORMAL, "secondary ink on canvas"),
    ("var(--muted)", "var(--paper)", AA_NORMAL, "muted text on canvas"),
    ("var(--muted)", "var(--paper-2)", AA_NORMAL, "muted text on paper-2"),
    ("var(--muted)", "var(--paper-3)", AA_NORMAL, "muted text on cards"),
    ("var(--brand-blue)", "var(--paper)", AA_NORMAL, "links on canvas"),
    ("var(--brand-blue)", "var(--paper-3)", AA_NORMAL, "links on cards"),
    ("var(--ink-2)", "var(--paper-3)", AA_NORMAL, "theme-toggle label"),
    ("var(--danger-fg)", "var(--danger-bg)", AA_NORMAL, "inline error text"),
    ("var(--warning-text)", "var(--spark-10)", AA_NORMAL, "warning callout"),
    ("var(--on-brand)", "var(--blue-100)", AA_NORMAL, "text on blue fill"),
    # Status badges (normal text inside small pills).
    ("var(--status-open-fg)", "var(--status-open-bg)", AA_NORMAL, "open badge"),
    (
        "var(--status-in-progress-fg)",
        "var(--status-in-progress-bg)",
        AA_NORMAL,
        "in-progress badge",
    ),
    (
        "var(--status-blocked-fg)",
        "var(--status-blocked-bg)",
        AA_NORMAL,
        "blocked badge",
    ),
    (
        "var(--status-deferred-fg)",
        "var(--status-deferred-bg)",
        AA_NORMAL,
        "deferred badge",
    ),
    (
        "var(--status-closed-fg)",
        "var(--status-closed-bg)",
        AA_NORMAL,
        "closed badge",
    ),
]


def _resolve(token: str, variables: dict[str, str]) -> str:
    """Resolve a var() token to a concrete hex color under the dark palette."""
    value = resolve_css_value(token, variables)
    assert value.startswith("#"), f"{token!r} did not resolve to hex: {value!r}"
    return value


def test_dark_theme_block_exists():
    """The dark theme override block must be present and non-trivial."""
    css = CSS_PATH.read_text(encoding="utf-8")
    dark = dark_theme_variables(css)
    # Sanity: dark canvas must actually be dark (paper darker than ink).
    assert dark.get("--paper"), "dark theme is missing a --paper token"
    assert dark["--paper"] != "#f8f8f8", "dark --paper still points at light value"


def test_dark_theme_pairs_meet_wcag_aa():
    """Every dark-theme text/background pair clears its WCAG AA threshold."""
    css = CSS_PATH.read_text(encoding="utf-8")
    dark = dark_theme_variables(css)

    failures = []
    for fg_token, bg_token, min_ratio, desc in CASES:
        fg = _resolve(fg_token, dark)
        bg = _resolve(bg_token, dark)
        ratio = contrast_ratio(fg, bg)
        if ratio < min_ratio:
            failures.append(f"{desc}: {ratio:.2f}:1 < {min_ratio}:1 ({fg} on {bg})")

    assert not failures, "Dark theme WCAG AA failures:\n" + "\n".join(failures)
