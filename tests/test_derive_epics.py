from bdboard import derive


def _bead(
    bead_id: str,
    *,
    issue_type: str = "task",
    status: str = "open",
    created_at: str = "2026-05-28T10:00:00Z",
    dependencies: list[dict] | None = None,
):
    return {
        "id": bead_id,
        "title": f"Title {bead_id}",
        "issue_type": issue_type,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "dependencies": dependencies,
    }


def test_lanes_excludes_epics_from_main_columns():
    beads = [
        _bead("task-1", issue_type="task", status="open"),
        _bead("epic-1", issue_type="epic", status="open"),
        _bead("epic-2", issue_type="epic", status="closed"),
    ]

    buckets = derive.lanes(beads)
    all_ids = [b["id"] for lane in buckets.values() for b in lane]

    assert "task-1" in all_ids
    assert "epic-1" not in all_ids
    assert "epic-2" not in all_ids


def test_epic_lane_promotes_active_or_next_ready_to_front_and_omits_closed():
    beads = [
        _bead(
            "single",
            issue_type="epic",
            status="open",
            created_at="2026-05-28T10:00:04Z",
        ),
        _bead(
            "pair-a",
            issue_type="epic",
            status="deferred",
            created_at="2026-05-28T10:00:01Z",
        ),
        _bead(
            "pair-b",
            issue_type="epic",
            status="in_progress",
            created_at="2026-05-28T10:00:02Z",
            dependencies=[{"id": "pair-a", "dependency_type": "blocks"}],
        ),
        _bead(
            "chain-a",
            issue_type="epic",
            status="open",
            created_at="2026-05-28T10:00:03Z",
        ),
        _bead(
            "chain-b",
            issue_type="epic",
            status="blocked",
            created_at="2026-05-28T10:00:05Z",
            dependencies=[{"id": "chain-a", "dependency_type": "blocks"}],
        ),
        _bead(
            "chain-c",
            issue_type="epic",
            status="deferred",
            created_at="2026-05-28T10:00:06Z",
            dependencies=[{"id": "chain-b", "dependency_type": "blocks"}],
        ),
        _bead(
            "unwired",
            issue_type="epic",
            status="open",
            created_at="2026-05-28T10:00:07Z",
        ),
        _bead(
            "closed-epic",
            issue_type="epic",
            status="closed",
            created_at="2026-05-28T10:00:00Z",
        ),
    ]

    lane = derive.epic_lane(beads)
    ids = [b["id"] for b in lane]

    assert ids == [
        "pair-b",
        "pair-a",
        "chain-a",
        "chain-b",
        "chain-c",
        "single",
        "unwired",
    ]
    assert "closed-epic" not in ids

    status = {b["id"]: (b["status_icon"], b["status_label"]) for b in lane}
    assert status["pair-b"] == ("▶", "In Progress")
    assert status["chain-b"] == ("⛔", "Blocked")
    assert status["chain-c"] == ("⏸", "Deferred")


def test_epic_lane_promotes_ready_when_no_active_epic():
    beads = [
        _bead(
            "blocked-epic",
            issue_type="epic",
            status="open",
            created_at="2026-05-28T10:00:01Z",
            dependencies=[{"id": "missing", "dependency_type": "blocks"}],
        ),
        _bead(
            "ready-epic",
            issue_type="epic",
            status="open",
            created_at="2026-05-28T10:00:03Z",
            dependencies=[],
        ),
        _bead(
            "deferred-epic",
            issue_type="epic",
            status="deferred",
            created_at="2026-05-28T10:00:02Z",
        ),
    ]

    lane = derive.epic_lane(beads)
    assert lane[0]["id"] == "ready-epic"
