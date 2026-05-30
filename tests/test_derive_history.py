"""Tests for the History page derivations (bdboard-eia / design bdboard-rrc §4).

Covers history_window, throughput, lead_time_stats and their helpers. All
functions are pure over a snapshot list, so we inject a fixed ``now`` for
deterministic range math and never touch bd.
"""

from datetime import datetime, timedelta, timezone

from bdboard.derive import (
    DEFAULT_HISTORY_RANGE,
    _day_bucket,
    _parse_dt,
    _percentile,
    _range_to_cutoff,
    history_window,
    humanize_hours,
    lead_time_stats,
    throughput,
)

NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


def _bead(
    bead_id,
    *,
    status="closed",
    created_at=None,
    started_at=None,
    closed_at=None,
):
    """Build a minimal bead dict with only the fields history cares about."""
    b = {"id": bead_id, "status": status}
    if created_at is not None:
        b["created_at"] = created_at
    if started_at is not None:
        b["started_at"] = started_at
    if closed_at is not None:
        b["closed_at"] = closed_at
    return b


def _iso(days_ago, hour=12):
    """ISO timestamp `days_ago` days before NOW at a given UTC hour."""
    dt = NOW.replace(hour=hour, minute=0, second=0) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ----- _range_to_cutoff -----


def test_range_to_cutoff_known_presets():
    assert _range_to_cutoff("7d", now=NOW) == NOW - timedelta(days=7)
    assert _range_to_cutoff("30d", now=NOW) == NOW - timedelta(days=30)
    assert _range_to_cutoff("90d", now=NOW) == NOW - timedelta(days=90)


def test_range_to_cutoff_all_is_unbounded():
    assert _range_to_cutoff("all", now=NOW) is None


def test_range_to_cutoff_unknown_falls_back_to_default():
    # Unknown key behaves like the default (30d), not an error.
    assert _range_to_cutoff("bogus", now=NOW) == _range_to_cutoff(
        DEFAULT_HISTORY_RANGE, now=NOW
    )
    assert _range_to_cutoff("", now=NOW) == _range_to_cutoff(
        DEFAULT_HISTORY_RANGE, now=NOW
    )


def test_range_to_cutoff_case_insensitive():
    assert _range_to_cutoff("7D", now=NOW) == _range_to_cutoff("7d", now=NOW)


# ----- _parse_dt / _day_bucket -----


def test_parse_dt_handles_z_and_naive():
    assert _parse_dt("2026-05-30T12:00:00Z").tzinfo is not None
    naive = _parse_dt("2026-05-30T12:00:00")
    assert naive.tzinfo is not None  # assumed UTC


def test_parse_dt_invalid_returns_none():
    assert _parse_dt(None) is None
    assert _parse_dt("") is None
    assert _parse_dt("not-a-date") is None


def test_day_bucket_format_and_miss():
    assert _day_bucket("2026-05-30T12:00:00Z") == "2026-05-30"
    assert _day_bucket(None) is None
    assert _day_bucket("garbage") is None


# ----- history_window -----


def test_history_window_filters_to_closed_in_range():
    beads = [
        _bead("a", closed_at=_iso(1)),  # in 7d
        _bead("b", closed_at=_iso(10)),  # outside 7d, in 30d
        _bead("c", status="open", created_at=_iso(1)),  # not closed
        _bead("d", closed_at=_iso(100)),  # outside 30d
    ]
    res = history_window(beads, "7d", now=NOW)
    ids = [b["id"] for b in res["items"]]
    assert ids == ["a"]
    assert res["total"] == 1
    assert res["has_more"] is False


def test_history_window_all_includes_everything_closed():
    beads = [
        _bead("a", closed_at=_iso(1)),
        _bead("b", closed_at=_iso(500)),
        _bead("c", status="open", created_at=_iso(1)),
    ]
    res = history_window(beads, "all", now=NOW)
    assert res["total"] == 2
    assert {b["id"] for b in res["items"]} == {"a", "b"}


def test_history_window_sorted_newest_closed_first():
    beads = [
        _bead("old", closed_at=_iso(5)),
        _bead("new", closed_at=_iso(1)),
        _bead("mid", closed_at=_iso(3)),
    ]
    res = history_window(beads, "30d", now=NOW)
    assert [b["id"] for b in res["items"]] == ["new", "mid", "old"]


def test_history_window_pagination():
    beads = [_bead(f"b{i}", closed_at=_iso(i + 1)) for i in range(5)]
    page1 = history_window(beads, "all", page=1, page_size=2, now=NOW)
    page2 = history_window(beads, "all", page=2, page_size=2, now=NOW)
    page3 = history_window(beads, "all", page=3, page_size=2, now=NOW)
    assert len(page1["items"]) == 2
    assert page1["has_more"] is True
    assert page1["total"] == 5
    assert len(page2["items"]) == 2
    assert page2["has_more"] is True
    assert len(page3["items"]) == 1
    assert page3["has_more"] is False
    # No overlap, full coverage.
    seen = (
        [b["id"] for b in page1["items"]]
        + [b["id"] for b in page2["items"]]
        + [b["id"] for b in page3["items"]]
    )
    assert len(set(seen)) == 5


def test_history_window_out_of_range_page_is_empty():
    beads = [_bead("a", closed_at=_iso(1))]
    res = history_window(beads, "all", page=99, page_size=10, now=NOW)
    assert res["items"] == []
    assert res["has_more"] is False
    assert res["total"] == 1


def test_history_window_excludes_closed_without_closed_at():
    beads = [_bead("a", status="closed")]  # no closed_at
    res = history_window(beads, "all", now=NOW)
    assert res["items"] == []
    assert res["total"] == 0


def test_history_window_empty_input():
    res = history_window([], "30d", now=NOW)
    assert res["items"] == []
    assert res["total"] == 0
    assert res["has_more"] is False


def test_history_window_clamps_bad_page_and_size():
    beads = [_bead("a", closed_at=_iso(1)), _bead("b", closed_at=_iso(2))]
    res = history_window(beads, "all", page=0, page_size=0, now=NOW)
    # page<1 clamps to 1, size<1 clamps to 1 → first item only.
    assert len(res["items"]) == 1
    assert res["page"] == 1
    assert res["page_size"] == 1


# ----- throughput -----


def test_throughput_buckets_by_day_gap_filled():
    # Two closes on day -1, one on day -3; day -2 has none → filled with 0.
    beads = [
        _bead("a", closed_at=_iso(1, hour=9)),
        _bead("b", closed_at=_iso(1, hour=15)),
        _bead("c", closed_at=_iso(3, hour=10)),
    ]
    series = throughput(beads, "7d", now=NOW)
    # Series spans first close (-3) through last close (-1): 3 days.
    assert len(series) == 3
    counts = {row["day"]: row["count"] for row in series}
    total = sum(r["count"] for r in series)
    assert total == 3
    # Continuous ascending days, includes a zero-fill day.
    assert 0 in counts.values()


def test_throughput_empty_when_nothing_closed():
    beads = [_bead("a", status="open", created_at=_iso(1))]
    assert throughput(beads, "30d", now=NOW) == []


def test_throughput_respects_range():
    beads = [
        _bead("recent", closed_at=_iso(2)),
        _bead("ancient", closed_at=_iso(200)),
    ]
    series = throughput(beads, "7d", now=NOW)
    total = sum(r["count"] for r in series)
    assert total == 1  # only the recent one


def test_throughput_series_is_ascending_and_continuous():
    beads = [
        _bead("a", closed_at=_iso(1)),
        _bead("b", closed_at=_iso(4)),
    ]
    series = throughput(beads, "30d", now=NOW)
    days = [row["day"] for row in series]
    assert days == sorted(days)
    # No gaps: consecutive calendar days.
    parsed = [datetime.strptime(d, "%Y-%m-%d") for d in days]
    for earlier, later in zip(parsed, parsed[1:]):
        assert (later - earlier).days == 1


# ----- _percentile -----


def test_percentile_basic():
    assert _percentile([], 50) is None
    assert _percentile([42.0], 50) == 42.0
    assert _percentile([0.0, 10.0], 50) == 5.0
    assert _percentile([0.0, 10.0], 0) == 0.0
    assert _percentile([0.0, 10.0], 100) == 10.0


# ----- lead_time_stats -----


def test_lead_time_stats_computes_hours():
    # created 2 days before close, started 1 day before close.
    beads = [
        _bead(
            "a",
            created_at="2026-05-28T12:00:00Z",
            started_at="2026-05-29T12:00:00Z",
            closed_at="2026-05-30T12:00:00Z",
        ),
    ]
    stats = lead_time_stats(beads, "all", now=NOW)
    assert stats["n"] == 1
    assert stats["median_lead_h"] == 48.0
    assert stats["median_cycle_h"] == 24.0


def test_lead_time_stats_empty():
    stats = lead_time_stats([], "30d", now=NOW)
    assert stats["n"] == 0
    assert stats["median_lead_h"] is None
    assert stats["p90_lead_h"] is None
    assert stats["median_cycle_h"] is None
    assert stats["p90_cycle_h"] is None


def test_lead_time_stats_missing_started_at_skips_cycle_only():
    beads = [
        _bead(
            "a",
            created_at="2026-05-29T12:00:00Z",
            closed_at="2026-05-30T12:00:00Z",
        ),
    ]
    stats = lead_time_stats(beads, "all", now=NOW)
    assert stats["n"] == 1
    assert stats["median_lead_h"] == 24.0
    # No started_at → cycle metrics stay None even though the bead counts.
    assert stats["median_cycle_h"] is None


def test_lead_time_stats_drops_negative_durations():
    # closed_at before created_at (clock skew) → dropped from lead set.
    beads = [
        _bead(
            "skew",
            created_at="2026-05-30T12:00:00Z",
            closed_at="2026-05-29T12:00:00Z",
        ),
    ]
    stats = lead_time_stats(beads, "all", now=NOW)
    assert stats["n"] == 1  # still counted as a closed bead in window
    assert stats["median_lead_h"] is None  # but the bad duration is dropped


def test_lead_time_stats_respects_range():
    beads = [
        _bead(
            "recent",
            created_at=_iso(3),
            closed_at=_iso(2),
        ),
        _bead(
            "ancient",
            created_at=_iso(201),
            closed_at=_iso(200),
        ),
    ]
    stats = lead_time_stats(beads, "7d", now=NOW)
    assert stats["n"] == 1  # only the recent close is in the 7d window


# ----- humanize_hours (History KPI strip, bdboard-ej5) -----


def test_humanize_hours_none_and_negative():
    assert humanize_hours(None) == "\u2014"
    assert humanize_hours(-3.0) == "\u2014"


def test_humanize_hours_sub_hour_renders_minutes():
    assert humanize_hours(0.5) == "30m"
    assert humanize_hours(0.0) == "0m"


def test_humanize_hours_hours_trim_trailing_zero():
    assert humanize_hours(3.0) == "3h"
    assert humanize_hours(2.5) == "2.5h"


def test_humanize_hours_days_past_48h():
    assert humanize_hours(48.0) == "2d"
    assert humanize_hours(36.0) == "36h"
    assert humanize_hours(60.0) == "2.5d"
