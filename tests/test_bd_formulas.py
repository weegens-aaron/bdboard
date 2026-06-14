"""Unit tests for BdClient formula methods (bdboard-ain.1).

Covers:
  - list_formulas: shells `bd formula list --json`, returns the list, rejects
    non-list payloads.
  - read_formula_variables: PARSES the *.formula.json file (the only reliable
    source — see memory bd-formula-cli-gotchas), marks no-default vars required,
    handles a missing/empty variables block as a no-input pour.
  - pour_formula: builds the `mol pour --var k=v ... --json` argv, surfaces bd
    stderr on non-zero exit, parses JSON on success, invalidates caches.

We stub _run_json / the subprocess so no real bd is spawned, and use tmp files
for the formula-file parsing path.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from bdboard.bd import BdClient

# ----- list_formulas -----


def _client_returning(payload: Any) -> tuple[BdClient, list[list[str]]]:
    client = BdClient()
    calls: list[list[str]] = []

    async def fake_run_json(args: list[str], timeout: float) -> Any:
        calls.append(args)
        return payload

    client._run_json = fake_run_json  # type: ignore[assignment]
    return client, calls


def test_list_formulas_shells_formula_list_and_returns_list() -> None:
    payload = [{"name": "code-health-audit", "source": "/x.formula.json"}]
    client, calls = _client_returning(payload)

    result = asyncio.run(client.list_formulas())

    assert result == payload
    assert calls == [["formula", "list"]]


def test_list_formulas_rejects_non_list_payload() -> None:
    client, _ = _client_returning({"not": "a list"})

    with pytest.raises(RuntimeError, match="non-list"):
        asyncio.run(client.list_formulas())


# ----- read_formula_variables -----


def _write_formula(tmp_path, variables: Any) -> str:
    data: dict[str, Any] = {"formula": "demo", "steps": []}
    if variables is not None:
        data["variables"] = variables
    path = tmp_path / "demo.formula.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_read_formula_variables_parses_defaults_and_required(tmp_path) -> None:
    source = _write_formula(
        tmp_path,
        {
            "repo": {"description": "Repo under audit", "default": "bdboard"},
            "token": {"description": "API token"},  # no default -> required
        },
    )
    client = BdClient()

    result = client.read_formula_variables(source)

    assert result == [
        {
            "name": "repo",
            "description": "Repo under audit",
            "default": "bdboard",
            "required": False,
        },
        {
            "name": "token",
            "description": "API token",
            "default": None,
            "required": True,
        },
    ]


def test_read_formula_variables_no_block_is_empty(tmp_path) -> None:
    source = _write_formula(tmp_path, None)
    client = BdClient()

    assert client.read_formula_variables(source) == []


def test_read_formula_variables_missing_file_raises() -> None:
    client = BdClient()

    with pytest.raises(RuntimeError, match="Could not read formula file"):
        client.read_formula_variables("/no/such/path.formula.json")


def test_read_formula_variables_bad_json_raises(tmp_path) -> None:
    path = tmp_path / "broken.formula.json"
    path.write_text("{not json", encoding="utf-8")
    client = BdClient()

    with pytest.raises(RuntimeError, match="not valid JSON"):
        client.read_formula_variables(str(path))


# ----- read_formula_detail (bdboard-078p) -----


def test_read_formula_detail_returns_description_vars_and_steps(tmp_path) -> None:
    data = {
        "formula": "demo",
        "description": "A long, untruncated description of the demo formula.",
        "variables": {
            "repo": {"description": "Repo under audit", "default": "bdboard"},
        },
        "steps": [
            {
                "id": "root",
                "title": "Umbrella epic",
                "description": "Parents the tree",
                "type": "epic",
                "priority": 2,
            },
            {
                "id": "child",
                "title": "A child task",
                "description": "Does work",
                "type": "task",
                "priority": 1,
            },
        ],
    }
    path = tmp_path / "demo.formula.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    client = BdClient()

    detail = client.read_formula_detail(str(path))

    assert detail["description"] == ("A long, untruncated description of the demo formula.")
    assert detail["variables"] == [
        {
            "name": "repo",
            "description": "Repo under audit",
            "default": "bdboard",
            "required": False,
        }
    ]
    assert detail["steps"] == [
        {
            "id": "root",
            "title": "Umbrella epic",
            "description": "Parents the tree",
            "type": "epic",
            "priority": 2,
        },
        {
            "id": "child",
            "title": "A child task",
            "description": "Does work",
            "type": "task",
            "priority": 1,
        },
    ]


def test_read_formula_detail_no_steps_or_vars_is_empty(tmp_path) -> None:
    path = tmp_path / "bare.formula.json"
    path.write_text(
        json.dumps({"formula": "bare", "description": "Just a desc"}),
        encoding="utf-8",
    )
    client = BdClient()

    detail = client.read_formula_detail(str(path))

    assert detail == {
        "description": "Just a desc",
        "variables": [],
        "steps": [],
    }


def test_read_formula_detail_skips_malformed_steps(tmp_path) -> None:
    path = tmp_path / "messy.formula.json"
    path.write_text(
        json.dumps(
            {
                "formula": "messy",
                "steps": ["not-a-dict", {"id": "ok", "title": "OK"}],
            }
        ),
        encoding="utf-8",
    )
    client = BdClient()

    steps = client.read_formula_detail(str(path))["steps"]

    assert steps == [{"id": "ok", "title": "OK", "description": "", "type": "", "priority": None}]


def test_read_formula_detail_missing_file_raises() -> None:
    client = BdClient()

    with pytest.raises(RuntimeError, match="Could not read formula file"):
        client.read_formula_detail("/no/such/path.formula.json")


# ----- pour_formula -----


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, input: bytes | None = None):
        return self._stdout, self._stderr

    def kill(self) -> None:  # pragma: no cover - only on timeout path
        pass

    async def wait(self) -> None:  # pragma: no cover
        pass


def _patch_subprocess(monkeypatch, proc: _FakeProc) -> list[list[str]]:
    captured: list[list[str]] = []

    async def fake_exec(prog, *args, **kwargs):
        captured.append(list(args))
        return proc

    monkeypatch.setattr(
        "bdboard.bd.asyncio.create_subprocess_exec",
        fake_exec,
    )
    return captured


def test_pour_formula_builds_var_args_and_returns_json(monkeypatch) -> None:
    result_json = {"new_epic_id": "bd-x-mol-u72", "created": 4, "id_mapping": {}}
    proc = _FakeProc(json.dumps(result_json).encode(), b"", 0)
    captured = _patch_subprocess(monkeypatch, proc)
    client = BdClient()
    invalidated = {"called": False}
    client.invalidate_caches = lambda: invalidated.update(called=True)  # type: ignore

    result = asyncio.run(
        client.pour_formula("code-health-audit", {"repo": "bdboard", "quarter": "Q2"})
    )

    assert result == result_json
    assert invalidated["called"] is True
    # argv: mol pour <name> --var repo=bdboard --var quarter=Q2 --json
    args = captured[0]
    assert args[:3] == ["mol", "pour", "code-health-audit"]
    assert "--var" in args
    assert "repo=bdboard" in args
    assert "quarter=Q2" in args
    assert args[-1] == "--json"


def test_pour_formula_surfaces_stderr_on_failure(monkeypatch) -> None:
    proc = _FakeProc(b"", b"tasks can only block other tasks, not epics", 1)
    _patch_subprocess(monkeypatch, proc)
    client = BdClient()

    with pytest.raises(RuntimeError, match="tasks can only block"):
        asyncio.run(client.pour_formula("broken", {}))


def test_pour_formula_rejects_non_object_json(monkeypatch) -> None:
    proc = _FakeProc(b"[1, 2, 3]", b"", 0)
    _patch_subprocess(monkeypatch, proc)
    client = BdClient()

    with pytest.raises(RuntimeError, match="non-object"):
        asyncio.run(client.pour_formula("demo", {}))


def test_pour_formula_captures_vapor_warning_on_success(monkeypatch) -> None:
    """bdboard-6nl8: bd exits 0 but warns on stderr when a phase:'vapor'
    formula is poured as persistent. We must read stderr on the SUCCESS path
    and attach the warning under _wisp_warning without losing the result."""
    result_json = {"new_epic_id": "bd-x-mol-z", "created": 3, "id_mapping": {}}
    warning = '⚠ Formula "demo" recommends vapor phase (ephemeral)'
    proc = _FakeProc(json.dumps(result_json).encode(), warning.encode(), 0)
    _patch_subprocess(monkeypatch, proc)
    client = BdClient()
    client.invalidate_caches = lambda: None  # type: ignore

    result = asyncio.run(client.pour_formula("demo", {}))

    # The pour result is intact AND the wisp warning rides alongside it.
    assert result["new_epic_id"] == "bd-x-mol-z"
    assert result["created"] == 3
    assert "recommends vapor phase" in result["_wisp_warning"]


def test_pour_formula_no_warning_on_plain_success(monkeypatch) -> None:
    """A normal (liquid) pour with empty/irrelevant stderr carries NO
    _wisp_warning key — the warning surfaces only for vapor-phase formulas."""
    result_json = {"new_epic_id": "bd-x-mol-z", "created": 3, "id_mapping": {}}
    proc = _FakeProc(json.dumps(result_json).encode(), b"", 0)
    _patch_subprocess(monkeypatch, proc)
    client = BdClient()
    client.invalidate_caches = lambda: None  # type: ignore

    result = asyncio.run(client.pour_formula("demo", {}))

    assert "_wisp_warning" not in result
