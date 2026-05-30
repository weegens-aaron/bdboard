"""Derive UI-shaped views from raw bead snapshots.

This package was split from a single ``derive.py`` module (bdboard-2ic) once
it crossed the project's 600-line guideline. The public import surface is
preserved verbatim — ``from bdboard import derive`` and
``from bdboard.derive import <name>`` keep working exactly as before — by
re-exporting every symbol (including the underscore-prefixed helpers the
test suite imports directly) from the focused submodules:

- :mod:`bdboard.derive.timeutil` — timestamp parsing / humanization
- :mod:`bdboard.derive.lanes`    — epic_lane / lanes / activity / counts
- :mod:`bdboard.derive.history`  — history_window / throughput / created /
                                   status_timeline

The submodule split is purely organizational; all functions remain pure
over the snapshot list with no I/O.
"""

from __future__ import annotations

from bdboard.derive.history import (
    DEFAULT_HISTORY_RANGE,
    HISTORY_PAGE_SIZE,
    HISTORY_PAGE_SIZES,
    HISTORY_RANGES,
    _closed_in_window,
    _created_in_window,
    _range_to_cutoff,
    clamp_page_size,
    created,
    history_window,
    status_timeline,
    throughput,
)
from bdboard.derive.lanes import (
    CLOSED_LANE_LIMIT,
    CLOSED_STATUSES,
    LANES,
    _STATUS_META,
    _epic_lane_rank,
    _has_unmet_blocking_dep,
    _is_closed,
    _is_epic,
    _stable_key,
    _topo_component_order,
    activity,
    counts,
    epic_lane,
    get_dependency_list,
    get_dependency_target_id,
    get_dependency_type,
    lanes,
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
    "CLOSED_LANE_LIMIT",
    "HISTORY_RANGES",
    "DEFAULT_HISTORY_RANGE",
    "HISTORY_PAGE_SIZE",
    "HISTORY_PAGE_SIZES",
    "clamp_page_size",
    # dependency helpers
    "get_dependency_list",
    "get_dependency_type",
    "get_dependency_target_id",
    # lane derivations
    "epic_lane",
    "lanes",
    "activity",
    "counts",
    # history derivations
    "history_window",
    "throughput",
    "created",
    "status_timeline",
    # time helpers
    "humanize_ts",
    "humanize_hours",
    # internal helpers re-exported for tests / backward compat
    "_epoch",
    "_parse_dt",
    "_day_bucket",
    "_is_epic",
    "_is_closed",
    "_has_unmet_blocking_dep",
    "_stable_key",
    "_epic_lane_rank",
    "_topo_component_order",
    "_STATUS_META",
    "_range_to_cutoff",
    "_closed_in_window",
    "_created_in_window",
]
