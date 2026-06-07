"""Tests for gate (async-coordination) display fidelity (audit FB-3 / bdboard-wgsy).

A gate is a bead (issue_type == "gate") created by `bd gate create --blocks
<id>` that makes its target WAIT on an external/async condition. Its `blocks`
edge points OUTWARD to the target, so the gate carries no unmet blocker of its
own; under generic bucketing it would satisfy "open + no blocker" and land in
the READY lane as claimable work (the canonical P1).

Two concerns are locked here:

1. Lane / count framing (derive.lanes / derive.counts): an open gate is routed
   into its own `gate` lane (a pending wait), never READY; it is counted under
   `gate`, never inflating the Open KPI; the gate->target `blocks` edge is
   untouched.
2. Await-condition interpretation (derive.gate_condition): the raw await_type /
   await_id / timeout fields are interpreted into a labelled condition: a
   PR/run link (gh:pr / gh:run), an auto-resolve deadline (timer), or a
   manual-only flag (human / bead), with graceful degradation when the repo URL
   or await-id is missing.

Field shapes verified against bd v1.0.5 (ce242a879) in a gt-prefix sandbox:
timer carries a nanosecond `timeout` (NOT await_id); human carries neither;
gh:* carry a string await_id.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bdboard import derive
from bdboard.derive.gates import gate_condition, is_gate


def _gate(
    gate_id: str = "gt-1",
    *,
    await_type: str = "human",
    await_id: str | None = None,
    timeout: int | None = None,
    status: str = "open",
    created_at: str = "2026-06-07T00:00:00Z",
):
    bead: dict = {
        "id": gate_id,
        "title": f"Gate: {await_type}",
        "issue_type": "gate",
        "status": status,
        "await_type": await_type,
        "created_at": created_at,
        "updated_at": created_at,
    }
    if await_id is not None:
        bead["await_id"] = await_id
    if timeout is not None:
        bead["timeout"] = timeout
    return bead


def _task(task_id: str, *, status: str = "open"):
    return {
        "id": task_id,
        "title": f"Task {task_id}",
        "issue_type": "task",
        "status": status,
        "created_at": "2026-06-07T00:00:00Z",
        "updated_at": "2026-06-07T00:00:00Z",
    }


# ----- is_gate -----


def test_is_gate_predicate():
    assert is_gate(_gate())
    assert is_gate({"issue_type": "GATE"})  # case-insensitive
    assert not is_gate(_task("t1"))
    assert not is_gate({})


# ----- lane framing -----


def test_open_gate_lands_in_gate_lane_not_ready():
    """AC1: an open gate is NOT presented as claimable READY work."""
    beads = [_gate("gt-1", await_type="human"), _task("t1")]
    buckets = derive.lanes(beads)

    gate_ids = {b["id"] for b in buckets["gate"]}
    ready_ids = {b["id"] for b in buckets["ready"]}
    assert "gt-1" in gate_ids
    assert "gt-1" not in ready_ids
    # The plain task still lands in READY; gate routing didn't break it.
    assert "t1" in ready_ids


def test_gate_lane_is_first_class_bucket():
    """The `gate` lane is a first-class bucket key."""
    assert "gate" in derive.LANES
    buckets = derive.lanes([])
    assert "gate" in buckets


def test_open_gate_with_outward_edge_does_not_fall_to_ready():
    """A gate's blocks edge points OUTWARD, so it has no unmet blocker; the
    exact condition that previously routed it to READY. Confirm the gate
    special-case fires regardless of (absent) blocking deps."""
    gate = _gate("gt-2", await_type="gh:pr", await_id="42")
    # Outward (dependent) edge to the gated target: still a wait, not ready.
    gate["dependents"] = [{"depends_on_id": "t9", "type": "blocks"}]
    buckets = derive.lanes([gate, _task("t9")])
    assert {b["id"] for b in buckets["gate"]} == {"gt-2"}
    assert all(b["id"] != "gt-2" for b in buckets["ready"])


def test_closed_gate_lands_in_closed_lane():
    """A resolved gate is history; it belongs in the closed lane, not gate."""
    beads = [_gate("gt-1", status="closed")]
    buckets = derive.lanes(beads)
    assert {b["id"] for b in buckets["closed"]} == {"gt-1"}
    assert buckets["gate"] == []


def test_non_open_gate_still_framed_as_wait():
    """A blocked/deferred/in_progress gate is still a wait."""
    for status in ("blocked", "deferred", "in_progress"):
        buckets = derive.lanes([_gate("gt-x", status=status)])
        assert {b["id"] for b in buckets["gate"]} == {"gt-x"}, status


# ----- counts framing -----


def test_open_gate_counted_under_gate_not_open():
    """An open gate must not inflate the Open KPI; it's a wait, counted as
    `gate` so the masthead matches the gate lane (the m5bm invariant)."""
    counts = derive.counts([_gate("gt-1"), _task("t1")])
    assert counts.get("gate") == 1
    assert counts["open"] == 1  # only the plain task, not the gate


def test_closed_gate_counted_as_closed():
    counts = derive.counts([_gate("gt-1", status="closed")])
    assert counts["closed"] == 1
    assert "gate" not in counts


def test_gate_count_matches_gate_lane():
    """No masthead count without a matching lane (bdboard-m5bm), extended to
    gates: the `gate` count equals the gate lane size."""
    beads = [
        _gate("gt-1"),
        _gate("gt-2", await_type="gh:pr", await_id="1"),
        _task("t1"),
    ]
    counts = derive.counts(beads)
    buckets = derive.lanes(beads)
    assert counts["gate"] == len(buckets["gate"]) == 2


# ----- gate_condition: gh:pr / gh:run -----


def test_gate_condition_gh_pr_builds_link():
    """AC2: gh:pr await_id renders as a PR link (host-agnostic base URL)."""
    cond = gate_condition(
        _gate(await_type="gh:pr", await_id="42"),
        repo_url="https://github.com/owner/repo",
    )
    assert cond["await_type"] == "gh:pr"
    assert cond["link"] == "https://github.com/owner/repo/pull/42"
    assert cond["link_text"] == "PR #42"
    assert "42" in cond["summary"]
    assert cond["manual_only"] is False


def test_gate_condition_gh_run_builds_link():
    """AC2: gh:run await_id renders as an Actions-run link."""
    cond = gate_condition(
        _gate(await_type="gh:run", await_id="987654"),
        repo_url="https://github.com/owner/repo",
    )
    assert cond["link"] == "https://github.com/owner/repo/actions/runs/987654"
    assert cond["link_text"] == "Actions run 987654"


def test_gate_condition_gh_link_host_agnostic_for_enterprise():
    """Enterprise GitHub host builds its own link; never hardcoded github.com."""
    cond = gate_condition(
        _gate(await_type="gh:pr", await_id="7"),
        repo_url="https://gecgithub01.walmart.com/team/proj",
    )
    assert cond["link"] == "https://gecgithub01.walmart.com/team/proj/pull/7"


def test_gate_condition_gh_pr_without_repo_url_degrades_gracefully():
    """No repo URL -> no broken link; still a meaningful summary + note."""
    cond = gate_condition(_gate(await_type="gh:pr", await_id="42"), repo_url=None)
    assert cond["link"] is None
    assert "42" in cond["summary"]
    assert cond["note"]  # explains why there's no link


def test_gate_condition_trailing_slash_in_repo_url_is_normalised():
    cond = gate_condition(
        _gate(await_type="gh:pr", await_id="42"),
        repo_url="https://github.com/owner/repo/",
    )
    assert cond["link"] == "https://github.com/owner/repo/pull/42"


# ----- gate_condition: timer -----


def test_gate_condition_timer_shows_deadline():
    """AC2: a timer gate shows a deadline = created_at + timeout (ns)."""
    # 2h timeout = 7_200_000_000_000 ns; created 00:00 -> deadline 02:00.
    now = datetime(2026, 6, 7, 0, 30, tzinfo=UTC)  # 30m in
    cond = gate_condition(
        _gate(
            await_type="timer",
            timeout=7_200_000_000_000,
            created_at="2026-06-07T00:00:00Z",
        ),
        now=now,
    )
    assert cond["deadline"] == "2026-06-07T02:00:00Z"
    assert cond["until"] == "in 1h 30m"
    assert "1h 30m" in cond["summary"]
    assert cond["link"] is None


def test_gate_condition_timer_elapsed():
    now = datetime(2026, 6, 7, 5, 0, tzinfo=UTC)  # past the 2h deadline
    cond = gate_condition(
        _gate(
            await_type="timer",
            timeout=7_200_000_000_000,
            created_at="2026-06-07T00:00:00Z",
        ),
        now=now,
    )
    assert cond["until"] == "elapsed"


def test_gate_condition_timer_missing_timeout_degrades():
    cond = gate_condition(_gate(await_type="timer"))  # no timeout field
    assert cond["deadline"] is None
    assert "timer" in cond["summary"].lower()


# ----- gate_condition: human / bead / unknown -----


def test_gate_condition_human_is_manual_only():
    """AC2: a human gate is flagged manual-only."""
    cond = gate_condition(_gate(await_type="human"))
    assert cond["manual_only"] is True
    assert cond["link"] is None
    assert "gate resolve" in (cond["note"] or "")


def test_gate_condition_bead_is_manual_only_with_ref():
    """A bead gate is manual-only (cross-rig auto-resolution removed in 1.0.4)."""
    cond = gate_condition(_gate(await_type="bead", await_id="otherrig:abc-123"))
    assert cond["manual_only"] is True
    assert cond["link_text"] == "otherrig:abc-123"
    assert cond["link"] is None
    assert "1.0.4" in (cond["note"] or "")


def test_gate_condition_unknown_type_degrades_gracefully():
    """A future/unknown gate type never crashes; degrades to manual + summary."""
    cond = gate_condition(_gate(await_type="quantum", await_id="x1"))
    assert cond["manual_only"] is True
    assert "quantum" in cond["summary"]


def test_gate_condition_returns_none_for_non_gate():
    assert gate_condition(_task("t1")) is None
