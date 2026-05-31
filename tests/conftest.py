"""Shared pytest fixtures for the bdboard test suite.

Why this file exists (bdboard-e4l):

The full-page route handlers (`index`, `page_memory`, `page_history` in
`bdboard.app`) call `_validate_or_warn()` -> `bd.validate()`, which checks that
the workspace has a `.beads/` directory AND that the `bd` binary is on PATH. If
either is missing, the route renders `error.html` with `status_code=500` — by
design, so a genuinely broken workspace fails visibly rather than painting an
empty board.

That behavior is correct in production, but it made the happy-path route tests
environment-dependent: they pass locally (where bd is installed and a .beads/
workspace is checked out) yet returned 500 on GitHub-hosted runners, which have
neither. The tests' own docstrings wrongly assumed the routes "shell no bd
subprocess", overlooking that workspace validation still runs.

Rather than repeat the same stub in every route-test module (DRY), this autouse
fixture neutralizes workspace validation by default so the happy-path tests
assert on rendering alone, regardless of whether bd is present. Tests that
specifically exercise the *error* path (e.g. ``test_*_surfaces_workspace_error``)
simply re-stub `_validate_or_warn` to return an error string; their explicit
``monkeypatch.setattr`` runs after this fixture and wins.

We patch `app._validate_or_warn` (not `bd.validate`) so the dedicated
`bd.validate()` unit tests keep exercising the real implementation.
"""

from __future__ import annotations

import pytest

from bdboard import app as app_module


@pytest.fixture(autouse=True)
def _stub_workspace_validation(monkeypatch):
    """Treat the workspace as valid by default for every test.

    Keeps route tests independent of whether the `bd` binary / a `.beads/`
    workspace exist in the runner environment (bdboard-e4l). Error-path tests
    override this with their own ``monkeypatch.setattr`` after the fixture runs.
    """
    monkeypatch.setattr(app_module, "_validate_or_warn", lambda: None)
