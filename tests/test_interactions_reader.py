"""Unit tests for the swarm interaction-log reader (bdboard.interactions).

Covers bead bdboard-bghy's reader contract:
  - parses JSONL newest-first
  - missing file degrades to [] (no crash)
  - malformed lines are skipped, not fatal
  - kind filter + per-kind counts
  - kind-specific one-line summaries (llm_call / tool_call / label / field_change)
  - the extra payload is preserved + flattened into display detail pairs

These are pure-function tests over a tmp .beads dir — no bd binary, no app.
"""

from __future__ import annotations

import json

from bdboard import interactions


def _write_log(beads_dir, rows) -> None:
    beads_dir.mkdir(parents=True, exist_ok=True)
    path = beads_dir / "interactions.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_missing_file_returns_empty(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    # Note: dir doesn't even exist — must not raise.
    assert interactions.read_interactions(beads_dir) == []
    assert interactions.log_path(beads_dir).exists() is False


def test_parses_newest_first(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    _write_log(
        beads_dir,
        [
            {"id": "int-1", "kind": "tool_call", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "int-2", "kind": "llm_call", "created_at": "2026-03-01T00:00:00Z"},
            {"id": "int-3", "kind": "label", "created_at": "2026-02-01T00:00:00Z"},
        ],
    )
    entries = interactions.read_interactions(beads_dir)
    assert [e["id"] for e in entries] == ["int-2", "int-3", "int-1"]


def test_malformed_lines_are_skipped(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir(parents=True)
    (beads_dir / "interactions.jsonl").write_text(
        '{"id":"int-ok","kind":"label","created_at":"2026-01-01T00:00:00Z"}\n'
        "this is not json {{{\n"
        "\n"  # blank line tolerated
        '{"id":"int-ok2","kind":"llm_call","created_at":"2026-02-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    entries = interactions.read_interactions(beads_dir)
    assert {e["id"] for e in entries} == {"int-ok", "int-ok2"}


def test_filter_by_kind(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    _write_log(
        beads_dir,
        [
            {"id": "a", "kind": "tool_call", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "kind": "llm_call", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "c", "kind": "tool_call", "created_at": "2026-01-03T00:00:00Z"},
        ],
    )
    entries = interactions.read_interactions(beads_dir)
    tool = interactions.filter_by_kind(entries, "tool_call")
    assert {e["id"] for e in tool} == {"a", "c"}
    # Case-insensitive + whitespace-tolerant.
    assert len(interactions.filter_by_kind(entries, "  TOOL_CALL ")) == 2
    # "all" / falsy is a pass-through.
    assert interactions.filter_by_kind(entries, "all") == entries
    assert interactions.filter_by_kind(entries, "") == entries
    assert interactions.filter_by_kind(entries, None) == entries


def test_kind_counts_ordering(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    _write_log(
        beads_dir,
        [
            {"id": "1", "kind": "field_change", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "2", "kind": "llm_call", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "3", "kind": "zebra_kind", "created_at": "2026-01-03T00:00:00Z"},
            {"id": "4", "kind": "tool_call", "created_at": "2026-01-04T00:00:00Z"},
            {"id": "5", "kind": "tool_call", "created_at": "2026-01-05T00:00:00Z"},
        ],
    )
    entries = interactions.read_interactions(beads_dir)
    counts = interactions.kind_counts(entries)
    # Known kinds in documented order first, then unknowns alphabetically.
    assert list(counts.keys()) == [
        "llm_call",
        "tool_call",
        "field_change",
        "zebra_kind",
    ]
    assert counts["tool_call"] == 2
    assert counts["zebra_kind"] == 1


def test_field_change_summary(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    _write_log(
        beads_dir,
        [
            {
                "id": "int-x",
                "kind": "field_change",
                "created_at": "2026-01-01T00:00:00Z",
                "issue_id": "bdboard-5tj",
                "extra": {
                    "field": "status",
                    "old_value": "in_progress",
                    "new_value": "closed",
                    "reason": "Closed",
                },
            }
        ],
    )
    e = interactions.read_interactions(beads_dir)[0]
    assert e["summary"] == "status: in_progress \u2192 closed (Closed)"
    assert e["issue_id"] == "bdboard-5tj"
    # Empty old_value renders the EMPTY SET glyph, not a blank.
    assert "\u2192" in e["summary"]


def test_empty_value_uses_empty_set_glyph(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    _write_log(
        beads_dir,
        [
            {
                "id": "int-y",
                "kind": "field_change",
                "created_at": "2026-01-01T00:00:00Z",
                "extra": {"field": "assignee", "old_value": "Aaron", "new_value": ""},
            }
        ],
    )
    e = interactions.read_interactions(beads_dir)[0]
    assert e["summary"] == "assignee: Aaron \u2192 \u2205"


def test_swarm_kind_summaries_flat_and_nested(tmp_path) -> None:
    """llm_call/tool_call/label summaries work whether payload is flat or nested."""
    beads_dir = tmp_path / ".beads"
    _write_log(
        beads_dir,
        [
            # tool_call with flat top-level payload
            {
                "id": "t",
                "kind": "tool_call",
                "created_at": "2026-01-03T00:00:00Z",
                "tool_name": "grep",
                "exit_code": 0,
            },
            # llm_call with nested extra payload
            {
                "id": "l",
                "kind": "llm_call",
                "created_at": "2026-01-02T00:00:00Z",
                "extra": {"model": "claude-x", "prompt": "do thing"},
            },
            # label with reward + parent
            {
                "id": "b",
                "kind": "label",
                "created_at": "2026-01-01T00:00:00Z",
                "extra": {"reward": 1.0, "parent_id": "int-t"},
            },
        ],
    )
    by_id = {e["id"]: e for e in interactions.read_interactions(beads_dir)}
    assert by_id["t"]["summary"] == "grep (exit 0)"
    # flat top-level payload got folded into extra -> detail pairs
    assert ("tool_name", "grep") in by_id["t"]["details"]
    assert by_id["l"]["summary"] == "model claude-x"
    assert ("prompt", "do thing") in by_id["l"]["details"]
    assert "reward 1.0" in by_id["b"]["summary"]
    assert "on int-t" in by_id["b"]["summary"]


def test_details_serialize_nested_structures(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    _write_log(
        beads_dir,
        [
            {
                "id": "n",
                "kind": "llm_call",
                "created_at": "2026-01-01T00:00:00Z",
                "extra": {"messages": [{"role": "user"}], "n": 3},
            }
        ],
    )
    e = interactions.read_interactions(beads_dir)[0]
    details = dict(e["details"])
    assert details["n"] == "3"
    # list/dict payloads are JSON-dumped, not str(dict)'d
    assert details["messages"] == '[{"role": "user"}]'
