"""WCAG 2.2 AA contrast for the 'Beads created' chart bars (bdboard-5t5).

The created bars use ``--violet`` as a non-text UI fill to distinguish the
created strip from the blue closed strip. Non-text UI components must meet a
3:1 contrast ratio against their adjacent background (WCAG 1.4.11).
``--violet`` and ``--paper`` are both theme-aware, so we resolve each from
styles.css and assert 3:1 in BOTH the light and dark theme blocks.
"""

import re
from pathlib import Path

from wcag_utils import contrast_ratio

CSS = (
    Path(__file__).resolve().parent.parent / "src" / "bdboard" / "static" / "styles.css"
).read_text()


def _theme_blocks() -> tuple[str, str]:
    """Split styles.css into (light-root, dark-theme) token regions.

    The light theme lives in the first ``:root`` block; the dark theme is the
    block introduced by the ``[data-theme="dark"]`` (or prefers-color-scheme)
    override. We slice on the second ``--paper:`` declaration to separate the
    two so a token lookup picks the theme-correct value.
    """
    paper_positions = [m.start() for m in re.finditer(r"--paper:", CSS)]
    assert len(paper_positions) >= 2, "expected light + dark --paper declarations"
    split = paper_positions[1]
    return CSS[:split], CSS[split:]


def _resolve(token: str, region: str) -> str:
    """Resolve a CSS custom property to a hex colour within a theme region.

    Follows a single ``var(--other)`` indirection (e.g. light
    ``--paper: var(--gray-5)``) before falling back to a direct hex value.
    """
    m = re.search(rf"{re.escape(token)}:\s*([^;]+);", region)
    assert m, f"{token} not found in region"
    value = m.group(1).strip()
    if value.startswith("#"):
        return value
    ref = re.match(r"var\((--[\w-]+)\)", value)
    assert ref, f"{token} resolves to non-hex non-var value: {value}"
    return _resolve(ref.group(1), region)


def test_created_bar_class_uses_violet_token():
    # The created variant exists and pulls the violet token (not a hard-coded hex).
    m = re.search(r"\.throughput-bar-created\s*\{[^}]*\}", CSS)
    assert m, "throughput-bar-created rule missing"
    assert "var(--violet)" in m.group(0)


def test_created_bar_meets_3to1_in_light_theme():
    light, _ = _theme_blocks()
    violet = _resolve("--violet", light)
    paper = _resolve("--paper", light)
    ratio = contrast_ratio(violet, paper)
    assert ratio >= 3.0, (
        f"created bar {ratio:.2f}:1 fails 3:1 (light): {violet} on {paper}"
    )


def test_created_bar_meets_3to1_in_dark_theme():
    _, dark = _theme_blocks()
    violet = _resolve("--violet", dark)
    paper = _resolve("--paper", dark)
    ratio = contrast_ratio(violet, paper)
    assert ratio >= 3.0, (
        f"created bar {ratio:.2f}:1 fails 3:1 (dark): {violet} on {paper}"
    )
