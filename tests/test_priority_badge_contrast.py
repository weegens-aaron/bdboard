"""WCAG 2.2 AA contrast tests for priority badges (bdboard-rld).

Priority badges (P0-P4) must each clear WCAG AA contrast for their
text-on-background pair in BOTH the light and dark themes. This is the
user's explicit "contrast must be readable" requirement for the distinct
priority palette epic (bdboard-dg6).

The badge tokens live in ``.bead-priority.pN`` rules wired to
``--priority-pN-{bg,fg,border}`` tokens, declared in :root (light) and
re-pointed inside ``:root[data-theme="dark"]`` (dark). We resolve those
tokens straight from the stylesheet so the test fails if anyone retints a
level below AA.

Special case: P4 uses a transparent background, so its text actually sits
on whatever surface the badge is placed over. We assert the worst-case
surface (the lowest-contrast of paper / paper-2 / paper-3) clears AA in
each theme — if the faintest backdrop passes, every placement passes.
"""

from __future__ import annotations

from pathlib import Path

from css_test_utils import (
    dark_theme_variables,
    parse_css_variables,
    resolve_css_value,
)
from wcag_utils import contrast_ratio

CSS_PATH = Path("src/bdboard/static/styles.css")

AA_NORMAL = 4.5  # normal text (badge labels are small pill text)

# Surfaces a transparent-background badge (P4) may sit on. We test the
# worst case across all of them.
SURFACE_TOKENS = ("var(--paper)", "var(--paper-2)", "var(--paper-3)")

# Priority levels rendered as <span class="bead-priority pN">PN</span>.
PRIORITY_LEVELS = (0, 1, 2, 3, 4)


def _resolve(token: str, variables: dict[str, str]) -> str:
    """Resolve a var() token to a concrete value under the given palette."""
    return resolve_css_value(token, variables)


def _effective_pair(level: int, variables: dict[str, str]) -> tuple[str, str, str]:
    """Return (fg, bg, surface_label) for a priority level.

    For transparent backgrounds, picks the surface giving the LOWEST
    contrast (worst case) so a pass guarantees every real placement passes.
    """
    fg = _resolve(f"var(--priority-p{level}-fg)", variables)
    bg = _resolve(f"var(--priority-p{level}-bg)", variables)
    assert fg.startswith("#"), f"P{level} fg did not resolve to hex: {fg!r}"

    if bg == "transparent":
        worst = None
        for surf_token in SURFACE_TOKENS:
            surf = _resolve(surf_token, variables)
            assert surf.startswith("#"), f"{surf_token} did not resolve: {surf!r}"
            ratio = contrast_ratio(fg, surf)
            if worst is None or ratio < worst[1]:
                worst = (surf, ratio, surf_token)
        assert worst is not None
        return fg, worst[0], f"transparent → {worst[2]}"

    assert bg.startswith("#"), f"P{level} bg did not resolve to hex: {bg!r}"
    return fg, bg, "solid"


def test_priority_tokens_exist_in_both_themes():
    """Every priority level declares fg/bg/border in light AND dark blocks."""
    css = CSS_PATH.read_text(encoding="utf-8")
    light = parse_css_variables(css)
    dark = dark_theme_variables(css)
    for level in PRIORITY_LEVELS:
        for part in ("bg", "fg", "border"):
            key = f"--priority-p{level}-{part}"
            assert key in light, f"light theme missing {key}"
            assert key in dark, f"dark theme missing {key}"


def test_priority_badges_meet_wcag_aa_light():
    """All 5 priority badges clear WCAG AA on the light canvas."""
    css = CSS_PATH.read_text(encoding="utf-8")
    light = parse_css_variables(css)

    failures = []
    for level in PRIORITY_LEVELS:
        fg, bg, kind = _effective_pair(level, light)
        ratio = contrast_ratio(fg, bg)
        if ratio < AA_NORMAL:
            failures.append(f"P{level} ({kind}): {ratio:.2f}:1 < {AA_NORMAL}:1 ({fg} on {bg})")
    assert not failures, "Light theme priority-badge AA failures:\n" + "\n".join(failures)


def test_priority_badges_meet_wcag_aa_dark():
    """All 5 priority badges clear WCAG AA on the dark canvas."""
    css = CSS_PATH.read_text(encoding="utf-8")
    dark = dark_theme_variables(css)

    failures = []
    for level in PRIORITY_LEVELS:
        fg, bg, kind = _effective_pair(level, dark)
        ratio = contrast_ratio(fg, bg)
        if ratio < AA_NORMAL:
            failures.append(f"P{level} ({kind}): {ratio:.2f}:1 < {AA_NORMAL}:1 ({fg} on {bg})")
    assert not failures, "Dark theme priority-badge AA failures:\n" + "\n".join(failures)
