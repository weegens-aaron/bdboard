from __future__ import annotations

import re
from pathlib import Path

CSS_PATH = Path("src/bdboard/static/styles.css")
EPIC_STATUS_KEYS = ("open", "in_progress", "blocked", "deferred")
AA_NORMAL_TEXT_MIN_RATIO = 4.5


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    color = color.strip().lstrip("#")
    if len(color) != 6:
        raise ValueError(f"Expected #RRGGBB color, got: {color!r}")
    return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(color: str) -> float:
    r, g, b = _hex_to_rgb(color)
    rl, gl, bl = (_srgb_to_linear(v) for v in (r, g, b))
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl


def _contrast_ratio(foreground: str, background: str) -> float:
    l1 = _relative_luminance(foreground)
    l2 = _relative_luminance(background)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_css_variables(css: str) -> dict[str, str]:
    root_match = re.search(r":root\s*{(?P<body>.*?)}", css, re.DOTALL)
    if not root_match:
        raise AssertionError("Missing :root CSS variable block")

    variables: dict[str, str] = {}
    for name, value in re.findall(
        r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);", root_match.group("body")
    ):
        variables[name.strip()] = value.strip()
    return variables


def _resolve_css_color(value: str, variables: dict[str, str]) -> str:
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value

    var_match = re.fullmatch(r"var\((--[a-zA-Z0-9_-]+)(?:\s*,\s*([^\)]+))?\)", value)
    if not var_match:
        raise AssertionError(f"Unsupported color format: {value!r}")

    var_name, fallback = var_match.groups()
    if var_name in variables:
        return _resolve_css_color(variables[var_name], variables)
    if fallback:
        return _resolve_css_color(fallback, variables)
    raise AssertionError(f"Undefined CSS variable with no fallback: {var_name}")


def _extract_epic_status_colors(
    css: str, status_key: str, variables: dict[str, str]
) -> tuple[str, str]:
    pattern = re.compile(
        rf"\.epic-status\.status-{re.escape(status_key)}\s*{{(?P<body>.*?)}}",
        re.DOTALL,
    )
    match = pattern.search(css)
    if not match:
        raise AssertionError(f"Missing .epic-status.status-{status_key} rule")

    body = match.group("body")
    bg_match = re.search(r"background:\s*([^;]+);", body)
    fg_match = re.search(r"color:\s*([^;]+);", body)

    if not bg_match or not fg_match:
        raise AssertionError(
            f"Expected background/color for status {status_key}, got: {body!r}"
        )

    foreground = _resolve_css_color(fg_match.group(1), variables)
    background = _resolve_css_color(bg_match.group(1), variables)
    return foreground, background


def test_epic_status_badges_meet_wcag_aa_contrast_for_normal_text():
    css = CSS_PATH.read_text(encoding="utf-8")
    variables = _parse_css_variables(css)

    for status_key in EPIC_STATUS_KEYS:
        foreground, background = _extract_epic_status_colors(css, status_key, variables)
        ratio = _contrast_ratio(foreground, background)
        assert ratio >= AA_NORMAL_TEXT_MIN_RATIO, (
            f".epic-status.status-{status_key} contrast {ratio:.2f}:1 is below "
            f"WCAG AA {AA_NORMAL_TEXT_MIN_RATIO}:1"
        )
