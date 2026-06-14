"""Regression guard for Makefile recipe tab-indentation (bdboard-3kv3).

Why this test exists:

In commit fa93b53 (bdboard-8296, the FlowDoc HTML site work) the help recipe
line for the ``links`` target had its leading TAB silently replaced with a
literal ``t``::

    t@echo "  links       - lychee broken-link sweep ... (config: lychee.toml)"

Because that line is no longer tab-indented, GNU make stops treating it as part
of the ``help:`` recipe and tries to parse it as a new rule. The net effect was
that BOTH ``make help`` and ``make links`` broke with::

    No rule to make target lychee.toml)"
    overriding commands for target links

A single dropped tab is an easy regression to reintroduce (editors, sed, merge
conflicts), and it is invisible in most diffs. These tests pin the property so
the breakage cannot silently come back.

The pure-Python checks run everywhere (no ``make`` binary needed); the
subprocess checks are skipped when ``make`` is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"


def _makefile_lines() -> list[str]:
    return MAKEFILE.read_text(encoding="utf-8").splitlines()


def _help_recipe_lines() -> list[str]:
    """Return the raw lines belonging to the ``help:`` recipe block.

    A make recipe runs from the line after the ``help:`` rule header up to the
    first blank line or the next un-indented (rule) line.
    """
    lines = _makefile_lines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.rstrip().startswith("help:")),
        None,
    )
    assert start is not None, "Makefile has no 'help:' target"
    recipe: list[str] = []
    for ln in lines[start + 1 :]:
        if ln.strip() == "":
            break
        # A line that is neither tab-indented nor a comment ends the recipe;
        # capture it anyway so the tab assertion below can flag it loudly.
        recipe.append(ln)
        if not ln.startswith("\t") and not ln.lstrip().startswith("#"):
            break
    return recipe


def test_makefile_exists() -> None:
    assert MAKEFILE.is_file(), f"expected Makefile at {MAKEFILE}"


def test_no_tab_clobbered_echo_lines() -> None:
    """No recipe ``@echo`` line may have had its leading tab clobbered.

    Direct regression for bdboard-3kv3: ``t@echo ...`` (a literal char where a
    tab belongs). An ``@echo "`` is unambiguously a recipe line, so any such
    line that does not begin with a leading tab has had its tab clobbered --
    whether by a space or by a stray character (the literal ``t`` in the bug).
    """
    offenders = [ln for ln in _makefile_lines() if '@echo "' in ln and not ln.startswith("\t")]
    assert not offenders, (
        "Makefile recipe @echo line(s) are not tab-indented -- a leading TAB "
        f"was clobbered (the bdboard-3kv3 failure mode): {offenders!r}. "
        "make will mis-parse the de-indented line as a new rule and break "
        "'make help'/'make links'."
    )


def test_every_help_recipe_line_is_tab_indented() -> None:
    """Every line in the ``help:`` recipe must start with a hard tab."""
    recipe = _help_recipe_lines()
    assert recipe, "'help:' target has an empty recipe"
    not_tabbed = [ln for ln in recipe if not ln.startswith("\t")]
    assert not not_tabbed, (
        "help: recipe contains line(s) not indented with a leading TAB: "
        f"{not_tabbed!r}. make requires recipe lines to be tab-indented; a "
        "space- or char-prefixed line silently ends the recipe (bdboard-3kv3)."
    )


def test_links_help_line_present_and_tabbed() -> None:
    """The specific line that regressed must exist and be tab-indented."""
    matches = [
        ln
        for ln in _makefile_lines()
        if "links" in ln and "lychee" in ln and ln.lstrip().startswith("@echo")
    ]
    assert matches, "help text for the 'links' target is missing"
    assert all(ln.startswith("\t") for ln in matches), (
        f"the 'links' help line lost its leading tab: {matches!r} (bdboard-3kv3)"
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", ["help", "links"])
def test_make_dry_run_parses_without_warnings(target: str) -> None:
    """``make -n <target>`` must succeed with no parse warnings.

    This pins the observable symptom of bdboard-3kv3: the clobbered tab made
    make emit 'No rule to make target ...' and 'overriding commands for target
    links'. A clean dry-run proves the Makefile parses correctly.
    """
    proc = subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert proc.returncode == 0, f"`make -n {target}` exited {proc.returncode}:\n{proc.stderr}"
    for bad in ("no rule to make target", "overriding commands"):
        assert bad not in combined, (
            f"`make -n {target}` emitted a parse warning {bad!r} -- the "
            f"Makefile is mis-parsing (bdboard-3kv3):\n{combined}"
        )
