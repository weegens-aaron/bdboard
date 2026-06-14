"""Graph-hygiene signals derived from raw bead snapshots (audit FB-6).

bdboard historically surfaced ZERO graph-hygiene signals: a deadlocked
dependency cycle, an edge pointing at a target that isn't in the snapshot, and
a structurally incomplete bead (e.g. a bug with no *Steps to Reproduce*) all
rendered identically to healthy work. This module derives three at-a-glance
badges so those problems stop hiding in plain sight:

1. **cycle / deadlock** — :func:`cycle_member_ids` finds every bead that
   participates in a `blocks`/`blocked-by` dependency cycle. The lane layer
   already *detected* cycles inside ``_topo_component_order`` (the leftover
   nodes after a Kahn topo-sort) but silently discarded the result, so a
   deadlocked pair showed as ordinary Blocked. We compute cycle membership
   precisely (strongly-connected components) so a node merely *downstream* of a
   cycle is not mislabeled as being *in* one.
2. **blocked-by-missing vs blocked-by-open** — :func:`blocked_reason`
   distinguishes a bead blocked by a target that is *absent from the snapshot*
   (a structural orphan edge) from one blocked by a normal still-open target.
   The lane code's conservative "target is None → treat as blocked" branch
   masked the two as the same state.
3. **incomplete template** — :func:`incomplete_sections` derives the
   per-issue-type required sections (a bug needs *Steps to Reproduce*, a
   decision needs *Context / Decision / Consequences*, …) and reports which are
   missing, approximating a `bd lint` completeness signal.

All functions are pure over the snapshot list — no I/O, no caching — mirroring
:mod:`bdboard.derive.lanes`. The lane/epic builders call :func:`with_badges`
to graft the three derived fields onto a *copy* of each bead so the cached
snapshot dicts are never mutated.
"""

from __future__ import annotations

import re
from typing import Any

from bdboard.derive.lanes import (
    DIRECT_BLOCKING_DEP_TYPES,
    _is_closed,
    get_dependency_list,
    get_dependency_target_id,
    get_dependency_type,
)

# ── 1. Dependency cycles (deadlock detection) ──────────────────────────────


def _blocking_succ(beads: list[dict[str, Any]]) -> tuple[dict[str, set[str]], set[str]]:
    """Build the directed *blocking* graph waiter→target over present beads.

    Only `blocks`/`blocked-by` edges (``DIRECT_BLOCKING_DEP_TYPES``) form a
    deadlock: a `waits-for` fanout resolves against a spawner's children, not
    the edge target itself, so it cannot create a two-bead blocks-cycle and is
    intentionally excluded. Edges to targets outside the snapshot are dropped —
    a missing target is a *dangling* edge (handled by :func:`blocked_reason`),
    never a cycle. Returns (successors, node-set).
    """
    present = {b.get("id") for b in beads if b.get("id")}
    succ: dict[str, set[str]] = {n: set() for n in present}
    for b in beads:
        src = b.get("id")
        if not src:
            continue
        for dep in get_dependency_list(b):
            if get_dependency_type(dep) not in DIRECT_BLOCKING_DEP_TYPES:
                continue
            target = get_dependency_target_id(dep)
            if target in present:
                # Self-edges (A blocks A) are kept: a degenerate self-deadlock
                # is still a cycle (handled by the self-loop branch in
                # cycle_member_ids).
                succ[src].add(target)
    return succ, present


def cycle_member_ids(beads: list[dict[str, Any]]) -> set[str]:
    """Return the ids of every bead that participates in a blocking cycle.

    Uses Tarjan's strongly-connected-components algorithm (iterative, so a
    pathological deep chain can't blow the Python recursion limit): any SCC of
    size > 1 is a cycle, and a single node with a self-edge is a (degenerate)
    cycle too. A bead that merely *depends on* a cycle member — but is not
    itself on the cycle — is deliberately NOT included, so the badge means
    "you are deadlocked", not "something upstream is".
    """
    succ, nodes = _blocking_succ(beads)
    members: set[str] = set()

    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []

    for root in nodes:
        if root in indices:
            continue
        # Iterative DFS. Each work item is (node, iterator-position).
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_i = work[-1]
            if child_i == 0:
                indices[node] = index_counter
                lowlink[node] = index_counter
                index_counter += 1
                stack.append(node)
                on_stack.add(node)
            children = sorted(succ.get(node, ()))
            if child_i < len(children):
                work[-1] = (node, child_i + 1)
                child = children[child_i]
                if child not in indices:
                    work.append((child, 0))
                elif child in on_stack:
                    lowlink[node] = min(lowlink[node], indices[child])
                continue
            # All children processed — pop and maybe close an SCC.
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == indices[node]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == node:
                        break
                if len(component) > 1:
                    members.update(component)
                elif node in succ.get(node, ()):  # self-loop
                    members.add(node)
    return members


# ── 2. Blocked-by-missing vs blocked-by-open ───────────────────────────────


def blocked_reason(
    bead: dict[str, Any],
    present: dict[str, dict[str, Any]],
    known_ids: set[str] | None = None,
) -> str | None:
    """Classify *why* a bead's direct blocking edges hold it back.

    Returns:
        ``"missing"`` if any `blocks`/`blocked-by` target is a structural
            orphan — absent from the snapshot AND unknown to ``known_ids``
            (a dangling edge). This dominates because a dangling edge is the
            more serious hygiene defect.
        ``"open"`` if the bead is held only by targets that are present and
            still open (the ordinary Blocked case).
        ``None`` if no direct blocking edge currently holds it (every target
            is closed / satisfied).

    Args:
        present: id → bead for every bead in the current snapshot. A target
            found here is resolved against its real status.
        known_ids: the broader universe of ids known to exist (e.g. active +
            cached-closed). A target absent from ``present`` but in
            ``known_ids`` is a bead that simply isn't in *this* snapshot
            (typically already closed) — NOT an orphan, so it is treated as
            satisfied. When ``None`` the check is snapshot-relative: any target
            absent from ``present`` counts as missing (the conservative
            target-is-None branch the lane code already used).
    """
    universe = known_ids if known_ids is not None else set(present)
    has_missing = False
    has_open = False
    for dep in get_dependency_list(bead):
        if get_dependency_type(dep) not in DIRECT_BLOCKING_DEP_TYPES:
            continue
        target_id = get_dependency_target_id(dep)
        target = present.get(target_id)
        if target is not None:
            if not _is_closed((target.get("status") or "").lower()):
                has_open = True
            # else: target present & closed → satisfied, contributes nothing.
        elif target_id in universe:
            # Known to exist but not in this snapshot (e.g. closed elsewhere) —
            # not a dangling edge, treat as satisfied.
            continue
        else:
            has_missing = True
    if has_missing:
        return "missing"
    if has_open:
        return "open"
    return None


# ── 3. Incomplete-template detection (a bd-lint-style signal) ──────────────

# Per-issue-type required documentation sections. A bead of a type listed here
# is "complete" only when every required section is satisfied — either by a
# matching markdown heading in its description/notes, or (for sections backed
# by a dedicated bd field) by that field being populated. Types absent from
# this map carry no template requirement and are never flagged. Keeping the
# contract data-driven means adding/relaxing a type's template is one edit
# here, not logic sprinkled across the renderer (open/closed principle).
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "bug": ("Steps to Reproduce", "Expected Behavior", "Actual Behavior"),
    "task": ("Acceptance Criteria",),
    "feature": ("Acceptance Criteria",),
    "story": ("Acceptance Criteria",),
    "decision": ("Context", "Decision", "Consequences"),
    "spike": ("Question", "Findings"),
}

# A required section may be satisfied by a first-class bd field instead of a
# prose heading. (bd stores acceptance criteria in its own column, so a bead
# can be complete with a populated `acceptance_criteria` and no in-description
# "## Acceptance Criteria" heading.)
_SECTION_FIELDS: dict[str, str] = {
    "acceptance criteria": "acceptance_criteria",
}

# ATX markdown headings: one-or-more '#', a space, then the heading text.
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _normalize(text: str) -> str:
    """Lowercase + collapse internal whitespace for tolerant heading matches."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _heading_set(*texts: str | None) -> set[str]:
    """Collect normalized ATX headings present across the given prose blocks."""
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _HEADING_RE.finditer(text):
            found.add(_normalize(match.group(1)))
    return found


def incomplete_sections(bead: dict[str, Any]) -> list[str]:
    """Return the required sections a bead is *missing*, in declared order.

    An empty list means the bead is complete (or its type carries no template
    requirement). A section counts as present when a markdown heading in the
    description/notes matches it (substring-tolerant, so "## Steps To
    Reproduce (manual)" satisfies "Steps to Reproduce"), or when a dedicated
    bd field backing that section is populated.
    """
    issue_type = (bead.get("issue_type") or "").lower()
    required = REQUIRED_SECTIONS.get(issue_type)
    if not required:
        return []
    headings = _heading_set(bead.get("description"), bead.get("notes"))
    missing: list[str] = []
    for section in required:
        norm = _normalize(section)
        field = _SECTION_FIELDS.get(norm)
        if field and str(bead.get(field) or "").strip():
            continue
        if any(norm in h for h in headings):
            continue
        missing.append(section)
    return missing


# ── Enrichment glue used by the lane / epic builders ────────────────────────


def with_badges(
    bead: dict[str, Any],
    *,
    present: dict[str, dict[str, Any]],
    cycle_ids: set[str],
    known_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return a shallow copy of ``bead`` decorated with the three hygiene fields.

    A *copy* is returned (never the original) so the Store's cached snapshot
    dicts stay pristine — the badges are a view concern, not bead state.

    Fields added:
        ``hygiene_cycle``           bool — bead is on a blocking cycle.
        ``hygiene_blocked_reason``  ``"missing"`` | ``"open"`` | ``None``.
        ``hygiene_incomplete``      list[str] of missing required sections.
    """
    enriched = dict(bead)
    enriched["hygiene_cycle"] = bead.get("id") in cycle_ids
    enriched["hygiene_blocked_reason"] = blocked_reason(bead, present, known_ids)
    enriched["hygiene_incomplete"] = incomplete_sections(bead)
    return enriched
