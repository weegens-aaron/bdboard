"""Lane / activity / counts derivations from raw bead snapshots.

Pure functions over the snapshot list — no I/O, no caching. The Store handles
freshness; this module just shapes data for the board view.

Lane assignment rules:
    - In-Progress : status == 'in_progress'
    - Blocked     : status == 'blocked' OR (status == 'open' AND has unmet
                    blocking dependency)
    - Gate        : issue_type == 'gate' AND not closed. A gate is a *pending
                    wait*, not claimable work. Its `blocks` edge points
                    OUTWARD to the target it gates, so the gate carries no
                    unmet blocker of its own and would otherwise land in
                    READY as actionable work (audit FB-3). Special-cased into
                    its own lane so it reads as a wait condition, never a task
                    to pick up. The gate→target `blocks` edge is untouched.
    - Ready       : status == 'open' AND no unmet blocking dependencies
    - Pinned      : status == 'pinned' (infra / never-auto-close). Given its
                    OWN lane so it reads as a deliberate operational-axis
                    state, not as intentionally-parked Deferred work.
    - Swarm       : a `mol_type=swarm` molecule (not closed). A swarm has no
                    STORED status — bd computes it live from the children — so
                    it is special-cased into its own lane (audit FB-5) instead
                    of falling through to Deferred. It is the only object
                    carrying a running swarm's existence + coordinator handle.
                    Formula-pour grouping wrappers (also `molecule`-typed but
                    WITHOUT `mol_type=swarm`) stay hidden — Option A unchanged.
    - Deferred    : everything else open-ish (the catch-all for genuinely
                    unknown statuses)
    - Closed      : status in {closed, resolved, done}. Bounded by the
                    board's date window (see BOARD_CLOSED_WINDOW_DAYS) at
                    fetch time and sorted by closed_at desc so the most
                    recent wins are most visible.

Hidden statuses:
    - hooked : bd-internal molecule/formula machinery, not a human-facing
               work state. Hidden from the lanes (like molecule wrappers)
               AND from the masthead counts so the board never shows a
               count without a matching lane (bdboard-m5bm).
"""

from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush
from typing import Any

from bdboard.derive.timeutil import _epoch

# Lane keys are stable identifiers used in template selectors.
# Order here is informational only — the template controls render order.
LANES = (
    "deferred",
    "pinned",
    "gate",
    "swarm",
    "ready",
    "in_progress",
    "blocked",
    "closed",
)

# Statuses that represent closed/completed work
CLOSED_STATUSES = frozenset(["closed", "resolved", "done"])

# bd recognizes TWO blocking edge types, not one (field guide ch2 §2.4 /
# ch6 §VI). `blocks`/`blocked-by` is the direct edge: the waiter is blocked
# while its single target is open. `waits-for` is the FANOUT gate: the waiter
# is blocked while the SPAWNER it points at has open children (default
# `all-children` aggregation), and is *vacuously satisfied* (genuinely ready)
# when the spawner is childless or all its children are closed. Both must gate
# lane derivation or bdboard shows a bd-blocked bead as actionable READY work
# (blocked-shown-as-ready P0; same class as the reversed-dep bdboard-fjk).
# `waits-for` is kept SEPARATE from this set because it resolves against the
# spawner's children, not the edge target itself (see _waits_for_unmet).
DIRECT_BLOCKING_DEP_TYPES = frozenset(["blocks", "blocked-by", "blocked_by"])
WAITS_FOR_DEP_TYPE = "waits-for"

# Statuses that are bd-internal machinery, not human-facing work states.
# `hooked` is the molecule/formula lifecycle marker bd manages on its own;
# surfacing it as a board card (or a masthead count) misrepresents it as
# parked work. We suppress it from BOTH the lanes and counts so the two stay
# in agreement — no count without a lane (bdboard-m5bm). Mirrors the way the
# redundant `molecule` formula-pour wrapper is hidden (see _is_molecule).
HIDDEN_BOARD_STATUSES = frozenset(["hooked"])

# The board is a *recent-activity* surface. Its time-filter strip caps at
# 12h / 1d / 3d (see templates/base.html BOARD_TIME_WINDOWS), so the closed
# set is bounded by the WIDEST of those windows at fetch time rather than by
# a static count cap. This keeps the header CLOSED KPI and the Closed lane
# count consistent (bdboard-p8v): both reflect the same date-bounded set,
# narrowed further client-side to the user's selected window. Anything older
# than this window lives on the History page, not the board.
BOARD_CLOSED_WINDOW_DAYS = 3

# The History page is the long-window retrospective surface (7d/30d/90d/All).
# Unlike the board's date-bounded closed set, History fetches the FULL closed
# record (bd list --limit 0) so the page's range / custom-date / pagination
# controls bound the result set — not a hidden count cap (bdboard-a194). It
# was previously truncated to the 50 newest closures, which made anything
# older unreachable no matter how the filters were set.
_STATUS_META: dict[str, tuple[str, str]] = {
    "open": ("○", "Open"),
    "in_progress": ("▶", "In Progress"),
    "blocked": ("⛔", "Blocked"),
    "deferred": ("⏸", "Deferred"),
    "closed": ("✓", "Closed"),
    "resolved": ("✓", "Resolved"),
    "done": ("✓", "Done"),
}


# ----- Dependency field access helpers -----


def get_dependency_list(bead: dict) -> list[dict]:
    """Extract dependency list from a bead, normalizing field name variations.

    bd beads may store dependencies under 'deps' or 'dependencies'.
    Returns an empty list if neither field is present.
    """
    return bead.get("deps") or bead.get("dependencies") or []


def get_dependency_type(dep: dict) -> str:
    """Extract dependency type, normalizing field name variations.

    Dependency type may be stored as 'type' or 'dependency_type'.
    Returns normalized lowercase string, or empty string if not found.
    """
    return (dep.get("type") or dep.get("dependency_type") or "").lower()


def get_dependency_target_id(dep: dict) -> str | None:
    """Extract target ID from a dependency dict with fallback chain.

    Target ID may be stored under multiple field names:
    - depends_on_id (preferred)
    - target
    - id
    - dependsOnId (legacy camelCase)

    Returns the first non-None value found, or None if all fields are missing.
    """
    return dep.get("depends_on_id") or dep.get("target") or dep.get("id") or dep.get("dependsOnId")


# ----- Lane assignment logic -----


def _is_epic(bead: dict[str, Any]) -> bool:
    return (bead.get("issue_type") or "").lower() == "epic"


def _is_gate(bead: dict[str, Any]) -> bool:
    """True for an async-coordination gate bead (``issue_type == 'gate'``).

    A gate makes its target wait on an external/async condition; it is a
    *pending wait*, not claimable work. Because its `blocks` edge points
    outward to the target, it has no unmet blocker of its own and would fall
    into the READY lane under generic bucketing — the canonical FB-3 P1. The
    lane derivation special-cases it into the `gate` lane instead. Mirrors
    `bdboard.derive.gates.is_gate`; kept local so `lanes` has no cross-import
    cost on the hot path.
    """
    return (bead.get("issue_type") or "").lower() == "gate"


def _is_molecule(bead: dict[str, Any]) -> bool:
    """True for a formula-pour grouping WRAPPER (issue_type == 'molecule').

    `bd mol pour` creates a `molecule`-typed wrapper (the returned
    `new_epic_id`) that parents the whole poured tree, PLUS the formula's own
    `epic`-typed root step. Per the grouping-node display decision (Option A),
    the human-readable `<formula> <id>` name is carried by
    the epic root step (which already surfaces in the epic strip), so the bare
    wrapper is redundant on the board. We hide it from the swim lanes rather
    than render it as a stray ready-lane card. See the grouping-node
    display decision under docs/design/.
    """
    return (bead.get("issue_type") or "").lower() == "molecule"


def _is_swarm_molecule(bead: dict[str, Any]) -> bool:
    """True for a SWARM molecule (``issue_type == 'molecule'`` AND ``mol_type == 'swarm'``).

    `bd swarm create <epic>` mints a `molecule`-typed bead with
    `mol_type=swarm`, linked to the epic by a `relates-to` edge, carrying the
    coordinator as its `assignee` (field guide ch7 §I). Unlike a formula-pour
    grouping wrapper, this molecule is the ONLY object that carries a running
    swarm's existence, its coordinator handle, and the `bd swarm list` rollup.

    The type-only `_is_molecule` filter would sweep it up with the redundant
    pour wrapper and hide it (audit FB-5), making a live swarm invisible on the
    board — reachable only by direct modal URL. This predicate splits the two
    so swarm molecules can be surfaced (their own lane) while pour wrappers
    stay hidden (Option A unchanged). A swarm molecule is necessarily also a
    molecule, so callers that hide pour wrappers must check
    ``_is_molecule(b) and not _is_swarm_molecule(b)``.
    """
    return _is_molecule(bead) and (bead.get("mol_type") or "").lower() == "swarm"


def _is_closed(status: str) -> bool:
    return status in CLOSED_STATUSES


def _is_hidden_status(bead: dict[str, Any]) -> bool:
    """True for beads whose status is bd-internal machinery (e.g. `hooked`).

    These are suppressed from the board entirely — no lane card and no
    masthead count — so they're never misread as parked work. See
    HIDDEN_BOARD_STATUSES.
    """
    return (bead.get("status") or "").lower() in HIDDEN_BOARD_STATUSES


def _children_by_parent(beads: list[dict[str, Any]]) -> dict[str, list[dict]]:
    """Index beads by their `parent` id so a spawner's children are O(1).

    A `waits-for` fanout edge resolves against the SPAWNER's children, not the
    spawner itself (see _waits_for_unmet). bd records the child->parent link on
    each child's `parent` field (verified: `bd show --json` carries
    `"parent": "<id>"`). We invert that into parent->children once per
    derivation pass so the readiness check stays linear.
    """
    index: dict[str, list[dict]] = defaultdict(list)
    for b in beads:
        parent_id = b.get("parent")
        if parent_id:
            index[parent_id].append(b)
    return index


def _waits_for_unmet(
    spawner_id: str | None,
    children_by_parent: dict[str, list[dict]] | None,
) -> bool:
    """True if a `waits-for` fanout edge is unmet (waiter is functionally blocked).

    Semantics (field guide ch6 §VI, default `all-children` aggregation): the
    waiter is blocked while the spawner it points at has any OPEN (non-closed)
    child. A childless spawner — or one whose children are all closed — is
    *vacuously satisfied*, so the waiter stays genuinely Ready (matching bd's
    `bd ready`). bd does not surface the all-children/any-children mode
    (audit D3), so we honor the conservative default: any open child blocks.
    """
    if not spawner_id or children_by_parent is None:
        # No spawner id, or no index available to resolve children against:
        # we can't prove an open child exists, so treat as vacuously satisfied
        # rather than inventing a phantom blocker.
        return False
    for child in children_by_parent.get(spawner_id, ()):  # childless -> vacuous
        if not _is_closed((child.get("status") or "").lower()):
            return True
    return False


def _has_unmet_blocking_dep(
    bead: dict[str, Any],
    by_id: dict[str, dict],
    children_by_parent: dict[str, list[dict]] | None = None,
) -> bool:
    """A bead is functionally blocked if it has an unmet blocking edge.

    Two blocking edge types gate (field guide ch2 §2.4 / ch6 §VI):
      - `blocks`/`blocked-by`: the single target is not yet closed.
      - `waits-for`: the target SPAWNER has an open child (vacuous-satisfy when
        childless — see _waits_for_unmet). Requires `children_by_parent`; when
        absent the waits-for edge degrades to vacuously satisfied.
    """
    deps = get_dependency_list(bead)
    for d in deps:
        dep_type = get_dependency_type(d)
        target_id = get_dependency_target_id(d)
        if dep_type in DIRECT_BLOCKING_DEP_TYPES:
            target = by_id.get(target_id)
            if target is None:
                # unknown target — treat as unmet, conservative
                return True
            if not _is_closed(target.get("status", "")):
                return True
        elif dep_type == WAITS_FOR_DEP_TYPE:
            if _waits_for_unmet(target_id, children_by_parent):
                return True
    return False


def _stable_key(bead: dict[str, Any]) -> tuple[float, str]:
    return (_epoch(bead.get("created_at")), bead.get("id") or "")


def _epic_lane_rank(
    bead: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    children_by_parent: dict[str, list[dict]] | None = None,
) -> int:
    """Priority rank for which epic should lead the strip.

    Lower is better:
      0: actively in progress
      1: next-ready (open with no unmet blocking dependency)
      2: blocked (explicit blocked status or open with unmet blocker)
      3: deferred
      4: anything else
    """
    status = (bead.get("status") or "").lower()
    if status == "in_progress":
        return 0
    if status == "open":
        return 2 if _has_unmet_blocking_dep(bead, by_id, children_by_parent) else 1
    if status == "blocked":
        return 2
    if status == "deferred":
        return 3
    return 4


def _topo_component_order(
    nodes: set[str],
    succ: dict[str, set[str]],
    indegree: dict[str, int],
    by_id: dict[str, dict],
) -> list[dict[str, Any]]:
    """Topologically order a connected dependency component.

    Stable tie-break: created_at asc, then id asc. If a cycle exists, append
    remaining nodes by stable key so rendering stays deterministic.
    """
    local_in = {n: indegree.get(n, 0) for n in nodes}
    heap: list[tuple[float, str, str]] = []
    for n in nodes:
        if local_in[n] == 0:
            b = by_id[n]
            created, bead_id = _stable_key(b)
            heappush(heap, (created, bead_id, n))

    ordered_ids: list[str] = []
    while heap:
        _, _, n = heappop(heap)
        ordered_ids.append(n)
        for m in sorted(succ.get(n, ())):
            if m not in local_in:
                continue
            local_in[m] -= 1
            if local_in[m] == 0:
                b = by_id[m]
                created, bead_id = _stable_key(b)
                heappush(heap, (created, bead_id, m))

    if len(ordered_ids) != len(nodes):
        leftovers = sorted(
            (n for n in nodes if n not in ordered_ids),
            key=lambda n: _stable_key(by_id[n]),
        )
        ordered_ids.extend(leftovers)

    return [by_id[n] for n in ordered_ids]


def epic_lane(
    beads: list[dict[str, Any]],
    known_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build the horizontal epic strip data.

    Rules:
    - Only issue_type=epic
    - Closed epics omitted
    - Wired epics are sequenced predecessor→successor left-to-right
    - Unwired epics appended after wired chains in stable order

    Each emitted epic also carries the graph-hygiene badge fields (audit FB-6);
    see :func:`bdboard.derive.hygiene.with_badges` for ``known_ids`` semantics.
    """
    from bdboard.derive import hygiene

    active_epics = [
        b for b in beads if _is_epic(b) and not _is_closed((b.get("status") or "").lower())
    ]
    if not active_epics:
        return []

    # Build by_id from all beads (not just active epics) so closed dependencies
    # can be correctly identified when checking _has_unmet_blocking_dep.
    by_id = {b.get("id"): b for b in beads if b.get("id")}
    # Cycle membership spans the FULL bead set (a deadlock can cross epics),
    # so an epic on a blocking cycle earns the badge even when its cycle
    # partner isn't an epic.
    cycle_ids = hygiene.cycle_member_ids(beads)
    # Index children across ALL beads so a `waits-for` fanout edge can resolve
    # against its spawner's children (the children may be any type, not just
    # epics).
    children_by_parent = _children_by_parent(beads)
    # Build dependency graph structures only for active epics.
    active_ids = {b.get("id") for b in active_epics if b.get("id")}
    succ: dict[str, set[str]] = {bid: set() for bid in active_ids}
    indegree: dict[str, int] = {bid: 0 for bid in active_ids}

    for b in active_epics:
        dep_list = get_dependency_list(b)
        this_id = b.get("id")
        if not this_id:
            continue
        for dep in dep_list:
            dep_type = get_dependency_type(dep)
            # Both blocking edge types sequence the strip predecessor->successor
            # so a waiter renders after the spawner it depends on. `waits-for`
            # points at the spawner just like `blocks` points at the blocker.
            if dep_type not in DIRECT_BLOCKING_DEP_TYPES and dep_type != WAITS_FOR_DEP_TYPE:
                continue
            predecessor_id = get_dependency_target_id(dep)
            # Only wire up dependencies between active epics. We keep by_id
            # comprehensive for _has_unmet_blocking_dep checks, but the
            # topology graph only includes active epics.
            if predecessor_id not in active_ids:
                continue
            # Current issue depends on predecessor: predecessor -> current.
            if this_id not in succ[predecessor_id]:
                succ[predecessor_id].add(this_id)
                indegree[this_id] += 1

    undirected: dict[str, set[str]] = {bid: set() for bid in active_ids}
    for u, vs in succ.items():
        for v in vs:
            undirected[u].add(v)
            undirected[v].add(u)

    wired_components: list[set[str]] = []
    unwired: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bid in sorted(active_ids, key=lambda k: _stable_key(by_id[k])):
        if bid in seen:
            continue
        stack = [bid]
        comp: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.add(cur)
            stack.extend(undirected[cur] - seen)
        edge_count = sum(len(succ[n]) for n in comp)
        if edge_count == 0:
            unwired.append(by_id[bid])
        else:
            wired_components.append(comp)

    wired_components.sort(key=lambda comp: min(_stable_key(by_id[n]) for n in comp))

    ordered: list[dict[str, Any]] = []
    for comp in wired_components:
        ordered.extend(_topo_component_order(comp, succ, indegree, by_id))

    unwired.sort(key=_stable_key)
    ordered.extend(unwired)

    # Ensure position 0 is the active epic, or the next-ready epic if no
    # epic is currently in progress. Keep relative order stable for all
    # remaining epics.
    if ordered:
        anchor = min(
            ordered,
            key=lambda b: (_epic_lane_rank(b, by_id, children_by_parent), *_stable_key(b)),
        )
        ordered = [anchor] + [b for b in ordered if b is not anchor]

    out: list[dict[str, Any]] = []
    for b in ordered:
        raw_status = (b.get("status") or "unknown").lower()
        # Derive effective status: if status is open (not yet started) but has
        # unmet blocking dependencies, display as blocked. Don't override
        # in_progress — if work is already underway, show it as such.
        if raw_status == "open" and _has_unmet_blocking_dep(b, by_id, children_by_parent):
            status_key = "blocked"
        else:
            status_key = raw_status
        icon, label = _STATUS_META.get(status_key, ("?", status_key.replace("_", " ").title()))
        enriched = hygiene.with_badges(b, present=by_id, cycle_ids=cycle_ids, known_ids=known_ids)
        enriched["status_key"] = status_key
        enriched["status_icon"] = icon
        enriched["status_label"] = label
        out.append(enriched)
    return out


def lanes(
    beads: list[dict[str, Any]],
    known_ids: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Bucket non-epic beads into swim lanes.

    Open lanes sorted by priority asc (P0 first) then updated_at desc.
    Closed lane sorted by closed_at desc (most recent first). The closed
    set is bounded by the board's date window at FETCH time (see
    BOARD_CLOSED_WINDOW_DAYS / bd.list_closed), not by a static count here —
    so the header CLOSED KPI and the lane count agree (bdboard-p8v).

    Every active-lane card is decorated with graph-hygiene badge fields (audit
    FB-6); see :func:`bdboard.derive.hygiene.with_badges` for ``known_ids``.
    Closed cards are left unbadged — hygiene concerns *actionable* work.
    """
    from bdboard.derive import hygiene

    # Exclude epics (they live in the strip), formula-pour molecule WRAPPERS
    # (the redundant grouping node — Option A), AND hidden-status beads
    # (bd-internal machinery like `hooked`). A SWARM molecule
    # (`mol_type=swarm`) is deliberately KEPT: it is the only object carrying a
    # running swarm's existence + coordinator, so it earns its own lane below
    # (audit FB-5) rather than being swept up with pour wrappers. The hidden
    # wrapper / hooked bead still exists in bd; it just doesn't earn a card
    # here (bdboard-m5bm).
    non_epics = [
        b
        for b in beads
        if not _is_epic(b)
        and not (_is_molecule(b) and not _is_swarm_molecule(b))
        and not _is_hidden_status(b)
    ]
    by_id = {b.get("id"): b for b in non_epics if b.get("id")}
    # Index children across ALL beads (epics included) so a `waits-for` fanout
    # edge resolves against its spawner's children even when the spawner is an
    # epic (which is excluded from the non_epics card set above).
    children_by_parent = _children_by_parent(beads)
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in LANES}
    for b in non_epics:
        status = (b.get("status") or "").lower()
        if _is_closed(status):
            buckets["closed"].append(b)
            continue
        # Swarm molecules (mol_type=swarm) have no STORED status — bd computes
        # their state live from the children (field guide ch7 §I), so generic
        # status bucketing would dump them into Deferred. Route any non-closed
        # swarm molecule into its own lane so a running swarm is visible with
        # its coordinator handle (audit FB-5), checked before status bucketing.
        if _is_swarm_molecule(b):
            buckets["swarm"].append(b)
            continue
        # Gate beads are a *pending wait*, never claimable work. A gate's
        # `blocks` edge points OUTWARD to its target, so it has no unmet
        # blocker of its own and would otherwise satisfy "open + no blocker"
        # and land in READY (audit FB-3, the canonical P1). Route any
        # non-closed gate into its own lane so it reads as a wait, not a task
        # to pick up. Checked before status bucketing so an open/blocked/
        # deferred gate is uniformly framed as a wait. The gate→target edge
        # itself is untouched.
        if _is_gate(b):
            buckets["gate"].append(b)
            continue
        if status == "in_progress":
            buckets["in_progress"].append(b)
        elif status == "blocked":
            buckets["blocked"].append(b)
        elif status == "open":
            if _has_unmet_blocking_dep(b, by_id, children_by_parent):
                buckets["blocked"].append(b)
            else:
                buckets["ready"].append(b)
        elif status == "pinned":
            # Infra / never-auto-close. Its own lane keeps it visually
            # distinct from intentionally-parked Deferred work.
            buckets["pinned"].append(b)
        else:
            buckets["deferred"].append(b)

    for k in ("deferred", "pinned", "gate", "swarm", "ready", "in_progress", "blocked"):
        # `priority` may be absent OR explicitly None (swarm molecules carry no
        # priority). Coerce None→99 WITHOUT `or` so a real P0 (priority 0)
        # isn't mis-sorted to the bottom.
        buckets[k].sort(
            key=lambda x: (
                x["priority"] if x.get("priority") is not None else 99,
                -_epoch(x.get("updated_at")),
            )
        )
    buckets["closed"].sort(key=lambda x: -_epoch(x.get("closed_at") or x.get("updated_at")))

    # Graft graph-hygiene badges onto the ACTIVE lane cards (not Closed).
    # Cycle membership and target resolution span the FULL bead set so a
    # cross-epic deadlock flags its members and an edge to an epic isn't
    # mistaken for a dangling one.
    cycle_ids = hygiene.cycle_member_ids(beads)
    present_all = {b.get("id"): b for b in beads if b.get("id")}
    for k in ("deferred", "pinned", "gate", "swarm", "ready", "in_progress", "blocked"):
        buckets[k] = [
            hygiene.with_badges(b, present=present_all, cycle_ids=cycle_ids, known_ids=known_ids)
            for b in buckets[k]
        ]
    # Surface each swarm molecule's coordinator (stored as its `assignee`,
    # field guide ch7 §I) as an explicit `coordinator` field so the swarm lane
    # can badge it without overloading the generic assignee label. with_badges
    # returns copies, so this never mutates the Store's cached snapshot.
    for b in buckets["swarm"]:
        b["coordinator"] = b.get("coordinator") or b.get("assignee")
    return buckets
