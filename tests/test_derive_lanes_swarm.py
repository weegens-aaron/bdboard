"""Swarm molecules surface in their own lane while pour wrappers stay hidden.

Audit FB-5 / bdboard-olry: the type-only ``_is_molecule`` filter hid ALL
``molecule``-typed beads to suppress the redundant formula-pour grouping
wrapper (Option A) — but it also swept up ``mol_type=swarm`` molecules, the
only object carrying a running swarm's existence + coordinator handle. These
tests pin the split: swarm molecules earn a Swarm-lane card (with coordinator),
pour wrappers remain hidden, and ordinary beads are untouched.
"""

from bdboard import derive


def _bead(
    bead_id: str,
    *,
    issue_type: str = "task",
    status: str = "open",
    mol_type: str | None = None,
    assignee: str | None = None,
    coordinator: str | None = None,
    created_at: str = "2026-05-28T10:00:00Z",
):
    bead = {
        "id": bead_id,
        "title": f"Title {bead_id}",
        "issue_type": issue_type,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "dependencies": None,
    }
    if mol_type is not None:
        bead["mol_type"] = mol_type
    if assignee is not None:
        bead["assignee"] = assignee
    if coordinator is not None:
        bead["coordinator"] = coordinator
    return bead


def test_is_swarm_molecule_helper():
    assert derive._is_swarm_molecule({"issue_type": "molecule", "mol_type": "swarm"}) is True
    assert derive._is_swarm_molecule({"issue_type": "Molecule", "mol_type": "Swarm"}) is True
    # A plain pour wrapper is a molecule but NOT a swarm.
    assert derive._is_swarm_molecule({"issue_type": "molecule"}) is False
    assert derive._is_swarm_molecule({"issue_type": "molecule", "mol_type": "patrol"}) is False
    # mol_type=swarm on a non-molecule type doesn't count.
    assert derive._is_swarm_molecule({"issue_type": "epic", "mol_type": "swarm"}) is False
    assert derive._is_swarm_molecule({}) is False


def test_swarm_molecule_earns_a_card_with_coordinator():
    """A mol_type=swarm molecule lands in the Swarm lane carrying its
    coordinator (the molecule's assignee, field guide ch7 §I)."""
    beads = [
        _bead("task-1", issue_type="task", status="open"),
        _bead(
            "swarm-1",
            issue_type="molecule",
            mol_type="swarm",
            status="",  # swarms carry no stored status
            assignee="agent-coordinator",
        ),
    ]

    buckets = derive.lanes(beads)
    swarm_ids = [b["id"] for b in buckets["swarm"]]

    assert "swarm-1" in swarm_ids
    card = next(b for b in buckets["swarm"] if b["id"] == "swarm-1")
    assert card["coordinator"] == "agent-coordinator"
    # The swarm must NOT silently fall into the catch-all Deferred lane.
    assert "swarm-1" not in [b["id"] for b in buckets["deferred"]]


def test_swarm_molecule_coordinator_field_preferred_over_assignee():
    beads = [
        _bead(
            "swarm-2",
            issue_type="molecule",
            mol_type="swarm",
            status="",
            assignee="fallback-agent",
            coordinator="explicit-coordinator",
        ),
    ]

    buckets = derive.lanes(beads)
    card = next(b for b in buckets["swarm"] if b["id"] == "swarm-2")
    assert card["coordinator"] == "explicit-coordinator"


def test_pour_wrapper_stays_hidden_no_regression_to_option_a():
    """A molecule WITHOUT mol_type=swarm (a formula-pour grouping wrapper) is
    still hidden from every lane — Option A is unchanged."""
    beads = [
        _bead("task-1", issue_type="task", status="open"),
        _bead("wrapper-1", issue_type="molecule", status="open"),
        _bead("wrapper-2", issue_type="molecule", mol_type="patrol", status="open"),
    ]

    buckets = derive.lanes(beads)
    all_ids = [b["id"] for lane in buckets.values() for b in lane]

    assert "task-1" in all_ids
    assert "wrapper-1" not in all_ids
    assert "wrapper-2" not in all_ids


def test_non_swarm_beads_carry_no_coordinator_field():
    """An ordinary bead's card is unchanged — no coordinator decoration leaks
    onto it, so its assignee still renders the normal way."""
    beads = [_bead("task-1", issue_type="task", status="open", assignee="alice")]

    buckets = derive.lanes(beads)
    card = next(b for b in buckets["ready"] if b["id"] == "task-1")
    assert "coordinator" not in card
    assert card["assignee"] == "alice"


def test_swarm_lane_is_a_declared_lane_key():
    assert "swarm" in derive.LANES
