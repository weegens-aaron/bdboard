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


def test_lanes_excludes_molecule_wrapper_from_main_columns():
    """Formula-pour grouping wrappers (issue_type == 'molecule') must NOT
    render as stray ready-lane cards.

    bdboard-ain.2 / Option A (spike bdboard-9n4 §3.3): the human-readable
    `<formula> <id>` name is carried by the formula's epic root step (which
    surfaces in the epic strip); the bare `molecule` wrapper is redundant and
    is hidden from the swim lanes.
    """
    beads = [
        _bead("task-1", issue_type="task", status="open"),
        _bead("wrapper-1", issue_type="molecule", status="open"),
    ]

    buckets = derive.lanes(beads)
    all_ids = [b["id"] for lane in buckets.values() for b in lane]

    assert "task-1" in all_ids
    assert "wrapper-1" not in all_ids


def test_epic_lane_excludes_molecule_wrapper():
    """The molecule wrapper is not an epic, so it must not appear in the epic
    strip either — only the formula's epic root step does (Option A)."""
    beads = [
        _bead("real-epic", issue_type="epic", status="open"),
        _bead("wrapper-1", issue_type="molecule", status="open"),
    ]

    lane = derive.epic_lane(beads)
    ids = [b["id"] for b in lane]

    assert "real-epic" in ids
    assert "wrapper-1" not in ids


def test_is_molecule_helper():
    assert derive._is_molecule({"issue_type": "molecule"}) is True
    assert derive._is_molecule({"issue_type": "Molecule"}) is True
    assert derive._is_molecule({"issue_type": "epic"}) is False
    assert derive._is_molecule({"issue_type": "task"}) is False
    assert derive._is_molecule({}) is False


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


def test_epic_lane_displays_blocked_badge_for_open_epics_with_unmet_blockers():
    """Epics with status=open but unmet blocking dependencies must show Blocked badge.

    Regression test for bdboard-vja: blocked epics were rendering as Open.
    """
    beads = [
        _bead(
            "ready-epic",
            issue_type="epic",
            status="open",
            dependencies=[],
        ),
        _bead(
            "blocked-by-open-epic",
            issue_type="epic",
            status="open",
            dependencies=[{"id": "ready-epic", "dependency_type": "blocks"}],
        ),
        _bead(
            "blocked-by-closed-epic",
            issue_type="epic",
            status="open",
            dependencies=[{"id": "closed-epic", "dependency_type": "blocks"}],
        ),
        _bead(
            "closed-epic",
            issue_type="epic",
            status="closed",
        ),
    ]

    lane = derive.epic_lane(beads)
    status_map = {b["id"]: b["status_key"] for b in lane}
    badge_map = {b["id"]: (b["status_icon"], b["status_label"]) for b in lane}

    # ready-epic has no blockers → should be "open"
    assert status_map["ready-epic"] == "open"
    assert badge_map["ready-epic"] == ("○", "Open")

    # blocked-by-open-epic depends on ready-epic (which is open) → should be "blocked"
    assert status_map["blocked-by-open-epic"] == "blocked"
    assert badge_map["blocked-by-open-epic"] == ("⛔", "Blocked")

    # blocked-by-closed-epic depends on closed-epic (which is closed) → no longer blocked, should be "open"
    assert status_map["blocked-by-closed-epic"] == "open"
    assert badge_map["blocked-by-closed-epic"] == ("○", "Open")
