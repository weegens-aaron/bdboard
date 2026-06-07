"""Unit tests for derive.swarm (epic rollup + swarm view shaping, FB-10).

Pure-function tests over the exact JSON shapes bd emits for:
  - ``bd mol progress <id>`` -> :func:`derive.epic_rollup`
  - ``bd swarm status <id>`` + ``bd swarm validate <id>`` -> :func:`derive.swarm_view`

No bd subprocess runs; we feed captured payloads directly.
"""

from __future__ import annotations

from bdboard import derive

# ----- epic_rollup -----


def _progress() -> dict:
    """A real `bd mol progress` payload (captured from bdboard-atvy)."""
    return {
        "completed": 10,
        "current_step_id": "bdboard-je14",
        "in_progress": 1,
        "molecule_id": "bdboard-atvy",
        "molecule_title": "Remediate display gaps",
        "percent": 71.42857142857143,
        "schema_version": 1,
        "total": 14,
    }


def test_epic_rollup_shapes_count_and_rounded_percent():
    rollup = derive.epic_rollup(_progress())
    assert rollup == {
        "total": 14,
        "completed": 10,
        "in_progress": 1,
        "percent": 71,  # 71.4285… rounded to a tidy int
    }


def test_epic_rollup_clamps_and_rounds_percent():
    rollup = derive.epic_rollup({"total": 3, "completed": 3, "percent": 100.0})
    assert rollup["percent"] == 100


def test_epic_rollup_none_for_childless_epic():
    """total<=0 means there is nothing to roll up -> no badge."""
    assert derive.epic_rollup({"total": 0, "completed": 0, "percent": 0}) is None


def test_epic_rollup_none_for_missing_or_non_dict():
    assert derive.epic_rollup(None) is None
    assert derive.epic_rollup([1, 2, 3]) is None  # type: ignore[arg-type]


def test_epic_rollup_tolerates_garbage_counts():
    rollup = derive.epic_rollup({"total": 5, "completed": None, "percent": "nope"})
    assert rollup == {"total": 5, "completed": 0, "in_progress": 0, "percent": 0}


# ----- swarm_view -----


def _status() -> dict:
    """A real `bd swarm status` payload (trimmed, captured shape)."""
    return {
        "active": [
            {"assignee": "Aaron", "id": "bdboard-je14", "title": "Rollup"},
        ],
        "active_count": 1,
        "blocked": [],
        "blocked_count": 0,
        "completed": [
            {
                "assignee": "Aaron",
                "closed_at": "2026-06-07 05:32",
                "id": "bdboard-2n6g",
                "title": "Glyphs",
            },
        ],
        "epic_id": "bdboard-atvy",
        "epic_title": "Remediate displagaps",
        "progress_percent": 71.42857142857143,
        "ready": [
            {"id": "bdboard-lwiv", "title": "Dolt sync"},
            {"id": "bdboard-ybbd", "title": "in_progress KPI"},
        ],
        "ready_count": 2,
        "total_issues": 14,
    }


def _validate() -> dict:
    """A real `bd swarm validate` payload (captured shape)."""
    return {
        "closed_issues": 10,
        "epic_id": "bdboard-atvy",
        "epic_title": "Remediate display gaps",
        "errors": None,
        "estimated_sessions": 14,
        "max_parallelism": 3,
        "ready_fronts": [
            {
                "issues": ["bdboard-lwiv", "bdboard-ybbd"],
                "titles": ["Dolt sync", "in_progress KPI"],
                "wave": 0,
            },
            {
                "issues": ["bdboard-olry"],
                "titles": ["Split swarm"],
                "wave": 1,
            },
        ],
        "swarmable": True,
        "total_issues": 14,
        "warnings": None,
    }


def test_swarm_view_surfaces_progress_and_cohort_counts():
    """AC: a swarm surfaces progress % and Completed/Active/Ready/Blocked."""
    view = derive.swarm_view(_status(), _validate())
    assert view["progress_percent"] == 71
    assert view["completed_count"] == 1
    assert view["active_count"] == 1
    assert view["ready_count"] == 2
    assert view["blocked_count"] == 0
    assert view["completed"][0]["id"] == "bdboard-2n6g"
    assert view["active"][0]["assignee"] == "Aaron"


def test_swarm_view_builds_human_numbered_waves():
    """AC: waves (Wave N, max parallelism) are legible for a swarmable epic."""
    view = derive.swarm_view(_status(), _validate())
    assert view["swarmable"] is True
    assert view["max_parallelism"] == 3
    assert view["estimated_sessions"] == 14
    waves = view["waves"]
    assert [w["wave"] for w in waves] == [1, 2]  # bd's 0-based -> human 1-based
    assert waves[0]["size"] == 2
    assert waves[0]["issues"] == [
        {"id": "bdboard-lwiv", "title": "Dolt sync"},
        {"id": "bdboard-ybbd", "title": "in_progress KPI"},
    ]
    assert waves[1]["issues"] == [{"id": "bdboard-olry", "title": "Split swarm"}]


def test_swarm_view_normalises_null_errors_warnings():
    view = derive.swarm_view(_status(), _validate())
    assert view["errors"] == []
    assert view["warnings"] == []


def test_swarm_view_degrades_with_only_status():
    """validate failed -> still render cohorts; no waves/swarmable."""
    view = derive.swarm_view(_status(), None)
    assert view["has_status"] is True
    assert view["has_validate"] is False
    assert view["ready_count"] == 2
    assert view["waves"] == []
    assert view["swarmable"] is False


def test_swarm_view_degrades_with_only_validate():
    """status failed -> still render waves; cohorts empty."""
    view = derive.swarm_view(None, _validate())
    assert view["has_status"] is False
    assert view["has_validate"] is True
    assert len(view["waves"]) == 2
    assert view["completed_count"] == 0
    # epic header still recovered from validate.
    assert view["epic_id"] == "bdboard-atvy"


def test_swarm_view_cohort_count_falls_back_to_list_len():
    """When bd omits *_count, derive falls back to len(list)."""
    status = {"completed": [{"id": "a"}, {"id": "b"}], "progress_percent": 50}
    view = derive.swarm_view(status, None)
    assert view["completed_count"] == 2


def test_swarm_view_skips_mismatched_title_length():
    """Fewer titles than issues -> trailing issues get title=None, no crash."""
    validate = {
        "swarmable": True,
        "ready_fronts": [{"issues": ["a", "b"], "titles": ["only one"], "wave": 0}],
    }
    view = derive.swarm_view(None, validate)
    assert view["waves"][0]["issues"] == [
        {"id": "a", "title": "only one"},
        {"id": "b", "title": None},
    ]
