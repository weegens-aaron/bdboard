"""Regression guard for the lychee broken-link sweep config (bdboard-90w0).

Why this test exists:

`lychee.toml` `exclude_path` entries are REGEXES matched against the whole
path, not literal substrings. The original config used bare names like
``".git"``. Because ``.`` is the regex any-char metachar and the pattern was
unanchored, ``".git"`` also matched the ``-git`` inside
``notes/decisions/0003-beads-sync-via-dolt-git-refs.md`` and silently dropped
that file from the sweep -- a latent coverage hole (any future markdown whose
path contained a matching substring like ``-git`` or ``xvenv`` would vanish
from the link check with no error).

The fix anchored every entry to a path boundary and escaped literal dots,
e.g. ``(^|/)\\.git(/|$)``. This test pins that property in pure Python so the
hole cannot silently reopen -- it does NOT require the `lychee` binary, so it
runs identically on CI runners that don't have lychee installed.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LYCHEE_TOML = REPO_ROOT / "lychee.toml"

# Markdown paths that are LEGITIMATE content and must never be excluded.
# The first is the exact file the original bug dropped; the others are
# synthetic adversarial paths that an unanchored substring rule would catch.
LEGITIMATE_MARKDOWN = [
    "notes/decisions/0003-beads-sync-via-dolt-git-refs.md",
    "docs/some-git-workflow.md",
    "docs/microvenv-notes.md",
    "src/node_modules_explained.md",
    "README.md",
]

# Real noise paths each exclude entry is *meant* to match, so we don't
# over-anchor the patterns into uselessness.
NOISE_PATHS_THAT_MUST_STILL_MATCH = [
    ".venv/lib/python3.11/site-packages/foo.md",
    "node_modules/pkg/readme.md",
    ".pytest_cache/v/cache/x.md",
    ".ruff_cache/0.1.0/y.md",
    ".git/COMMIT_EDITMSG",
    "subdir/.venv/nested.md",
]


def _exclude_path_patterns() -> list[str]:
    data = tomllib.loads(LYCHEE_TOML.read_text(encoding="utf-8"))
    patterns = data.get("exclude_path", [])
    assert patterns, "lychee.toml is missing exclude_path entries"
    return patterns


def test_lychee_toml_exists() -> None:
    assert LYCHEE_TOML.is_file(), f"expected lychee config at {LYCHEE_TOML}"


@pytest.mark.parametrize("good_path", LEGITIMATE_MARKDOWN)
def test_exclude_patterns_never_match_legitimate_markdown(good_path: str) -> None:
    """No exclude_path regex may match a real content file.

    This is the direct regression assertion for bdboard-90w0: the original
    unanchored ``".git"`` matched ``...dolt-git-refs.md`` and dropped it from
    the sweep. With anchored patterns, none of these should match.
    """
    offenders = [p for p in _exclude_path_patterns() if re.search(p, good_path)]
    assert not offenders, (
        f"exclude_path pattern(s) {offenders!r} wrongly match legitimate "
        f"markdown {good_path!r} -- this silently drops it from the link sweep "
        f"(the bdboard-90w0 coverage hole). Anchor the pattern to a path "
        f"boundary, e.g. (^|/)NAME(/|$), and escape literal dots."
    )


@pytest.mark.parametrize("noise_path", NOISE_PATHS_THAT_MUST_STILL_MATCH)
def test_exclude_patterns_still_match_real_noise_dirs(noise_path: str) -> None:
    """Anchoring must not over-correct: real noise dirs stay excluded."""
    matched = any(re.search(p, noise_path) for p in _exclude_path_patterns())
    assert matched, (
        f"no exclude_path pattern matches noise path {noise_path!r} -- the "
        f"sweep would crawl deps/caches/VCS internals. Patterns: "
        f"{_exclude_path_patterns()!r}"
    )


def test_every_exclude_pattern_is_anchored() -> None:
    """Each entry must be anchored to a path boundary, not a bare substring.

    A bare name like ``".git"`` matches mid-token (``-git``); the convention is
    ``(^|/)...(/|$)``. We assert each pattern contains an explicit boundary
    anchor so future edits keep the property that caused bdboard-90w0.
    """
    unanchored = [
        p
        for p in _exclude_path_patterns()
        if not (("(^|/)" in p or p.startswith("^")) and ("(/|$)" in p or p.endswith("$")))
    ]
    assert not unanchored, (
        f"exclude_path entries are not anchored to path boundaries: "
        f"{unanchored!r}. Use (^|/)NAME(/|$) so a name can't match mid-token "
        f"(the bdboard-90w0 failure mode)."
    )


def test_literal_dots_are_escaped_in_dotdirs() -> None:
    """Dot-prefixed dir names must escape the leading dot.

    An unescaped ``.`` is the any-char metachar, so ``.venv`` would also match
    ``xvenv``. Real dot-dirs must appear as ``\\.`` in the pattern.
    """
    dotdirs = (".venv", ".git", ".pytest_cache", ".ruff_cache")
    patterns = _exclude_path_patterns()
    for dotdir in dotdirs:
        bare = dotdir[1:]  # e.g. "venv"
        # Find the pattern intended for this dir (mentions the bare name).
        owning = [p for p in patterns if bare in p]
        if not owning:
            continue
        for p in owning:
            assert f"\\.{bare}" in p, (
                f"pattern {p!r} for {dotdir} does not escape the leading dot; "
                f"an unescaped '.' is the any-char metachar (bdboard-90w0)."
            )
