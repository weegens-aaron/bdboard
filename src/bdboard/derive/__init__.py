"""Derive UI-shaped views from raw bead snapshots.

This package was split from a single ``derive.py`` module once
it crossed the project's 600-line guideline. The public import surface is
preserved verbatim — ``from bdboard import derive`` and
``from bdboard.derive import <name>`` keep working exactly as before — by
re-exporting every symbol (including the underscore-prefixed helpers the
test suite imports directly) from the focused submodules:

- :mod:`bdboard.derive.timeutil` — timestamp parsing / humanization
- :mod:`bdboard.derive.lanes`    — epic_lane / lanes
- :mod:`bdboard.derive.feed`     — activity / counts (masthead + feed)
- :mod:`bdboard.derive.hygiene`  — cycle / dangling-edge / incomplete badges
- :mod:`bdboard.derive.history`  — history_window / throughput / created /
                                   lead_time_stats / status_timeline

The submodule split is purely organizational; all functions remain pure
over the snapshot list with no I/O.
"""

from __future__ import annotations

from bdboard.derive.feed import activity, counts
from bdboard.derive.gates import (
    coordination_count,
    gate_condition,
    is_gate,
    is_merge_slot,
    merge_slot_view,
)
from bdboard.derive.history import (
    DEFAULT_HISTORY_RANGE,
    HISTORY_PAGE_SIZE,
    HISTORY_PAGE_SIZES,
    HISTORY_RANGES,
    _closed_in_window,
    _created_in_window,
    _parse_date,
    _percentile,
    _range_to_cutoff,
    _resolve_bounds,
    clamp_page_size,
    combined,
    created,
    custom_bounds,
    history_window,
    lead_time_stats,
    resolve_history_bounds,
    status_timeline,
    throughput,
)
from bdboard.derive.hygiene import (
    REQUIRED_SECTIONS,
    blocked_reason,
    cycle_member_ids,
    incomplete_sections,
    with_badges,
)
from bdboard.derive.lanes import (
    _STATUS_META,
    BOARD_CLOSED_WINDOW_DAYS,
    CLOSED_STATUSES,
    DIRECT_BLOCKING_DEP_TYPES,
    HIDDEN_BOARD_STATUSES,
    LANES,
    WAITS_FOR_DEP_TYPE,
    _children_by_parent,
    _epic_lane_rank,
    _has_unmet_blocking_dep,
    _is_closed,
    _is_epic,
    _is_gate,
    _is_hidden_status,
    _is_molecule,
    _is_swarm_molecule,
    _stable_key,
    _topo_component_order,
    _waits_for_unmet,
    epic_lane,
    get_dependency_list,
    get_dependency_target_id,
    get_dependency_type,
    lanes,
)
from bdboard.derive.swarm import (
    epic_rollup,
    swarm_view,
)
from bdboard.derive.timeutil import (
    _day_bucket,
    _epoch,
    _parse_dt,
    humanize_hours,
    humanize_ts,
)

__all__ = [
    # constants
    "LANES",
    "CLOSED_STATUSES",
    "HIDDEN_BOARD_STATUSES",
    "BOARD_CLOSED_WINDOW_DAYS",
    "HISTORY_RANGES",
    "DEFAULT_HISTORY_RANGE",
    "HISTORY_PAGE_SIZE",
    "HISTORY_PAGE_SIZES",
    "clamp_page_size",
    "custom_bounds",
    "resolve_history_bounds",
    # dependency helpers
    "get_dependency_list",
    "get_dependency_type",
    "get_dependency_target_id",
    # gate derivations
    "is_gate",
    "gate_condition",
    "is_merge_slot",
    "merge_slot_view",
    "coordination_count",
    # lane derivations
    "epic_lane",
    "lanes",
    "activity",
    "counts",
    # epic rollup + swarm derivations (audit FB-10)
    "epic_rollup",
    "swarm_view",
    # graph-hygiene derivations (audit FB-6)
    "cycle_member_ids",
    "blocked_reason",
    "incomplete_sections",
    "with_badges",
    "REQUIRED_SECTIONS",
    # history derivations
    "history_window",
    "throughput",
    "created",
    "combined",
    "lead_time_stats",
    "status_timeline",
    # time helpers
    "humanize_ts",
    "humanize_hours",
    # internal helpers re-exported for tests / backward compat
    "_epoch",
    "_parse_dt",
    "_day_bucket",
    "_is_epic",
    "_is_molecule",
    "_is_swarm_molecule",
    "_is_gate",
    "_is_hidden_status",
    "_is_closed",
    "_has_unmet_blocking_dep",
    "_children_by_parent",
    "_waits_for_unmet",
    "DIRECT_BLOCKING_DEP_TYPES",
    "WAITS_FOR_DEP_TYPE",
    "_stable_key",
    "_epic_lane_rank",
    "_topo_component_order",
    "_STATUS_META",
    "_range_to_cutoff",
    "_resolve_bounds",
    "_parse_date",
    "_closed_in_window",
    "_created_in_window",
    "_percentile",
]
