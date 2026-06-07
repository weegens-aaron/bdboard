"""Tests for merge-slot mutex display fidelity (audit FB-9 / bdboard-50v5).

A merge-slot is bd's exclusive-access primitive: a single bead per rig
(``<prefix>-merge-slot``) carrying the magic label ``gt:slot``. Its state is
``status=open`` (available) / ``status=in_progress`` (held), with
``metadata.holder`` and a priority-ordered ``metadata.waiters`` queue.

These lock the pure derivations that turn that raw bead into a held/available +
waiter-queue view instead of the raw ``metadata`` JSON blob bdboard dumped
before (``field_row.html`` json branch).
"""

from __future__ import annotations

from bdboard import derive
from bdboard.derive.gates import is_merge_slot, merge_slot_view


def _slot(
    *,
    status: str = "open",
    holder: str | None = None,
    waiters: list | None = None,
    slot_id: str = "x-merge-slot",
    labels: list | None = None,
):
    metadata: dict = {}
    if holder is not None:
        metadata["holder"] = holder
    if waiters is not None:
        metadata["waiters"] = waiters
    return {
        "id": slot_id,
        "title": "merge slot",
        "status": status,
        "labels": labels if labels is not None else ["gt:slot"],
        "metadata": metadata,
    }


# ----- is_merge_slot -----


def test_is_merge_slot_matches_gt_slot_label():
    assert is_merge_slot(_slot())
    assert is_merge_slot(_slot(labels=["foo", "gt:slot", "bar"]))


def test_is_merge_slot_false_without_label():
    assert not is_merge_slot(_slot(labels=["foo"]))
    assert not is_merge_slot({})
    # Defensive: a non-list labels value must not crash.
    assert not is_merge_slot({"labels": "gt:slot"})


# ----- merge_slot_view: available -----


def test_view_none_for_non_slot():
    assert merge_slot_view({"labels": ["task"]}) is None


def test_view_available_open_slot():
    view = merge_slot_view(_slot(status="open"))
    assert view is not None
    assert view["state"] == "available"
    assert view["held"] is False
    assert view["holder"] is None
    assert view["waiters"] == []
    assert view["waiter_count"] == 0


def test_view_available_ignores_stale_holder():
    """An available slot reports no holder even if metadata lingers one."""
    view = merge_slot_view(_slot(status="open", holder="ghost"))
    assert view["state"] == "available"
    assert view["holder"] is None


# ----- merge_slot_view: held -----


def test_view_held_slot_with_holder():
    view = merge_slot_view(_slot(status="in_progress", holder="agent-7"))
    assert view["state"] == "held"
    assert view["held"] is True
    assert view["holder"] == "agent-7"


def test_view_held_without_holder_is_unknown_none():
    view = merge_slot_view(_slot(status="in_progress"))
    assert view["held"] is True
    assert view["holder"] is None


# ----- waiter queue normalisation -----


def test_view_waiters_string_queue_preserves_order():
    view = merge_slot_view(_slot(waiters=["agent-3", "agent-9", "agent-1"]))
    assert view["waiters"] == ["agent-3", "agent-9", "agent-1"]
    assert view["waiter_count"] == 3


def test_view_waiters_dict_queue_labels():
    view = merge_slot_view(_slot(waiters=[{"actor": "a1"}, {"holder": "a2"}, {"id": "a3"}]))
    assert view["waiters"] == ["a1", "a2", "a3"]


def test_view_waiters_non_list_degrades_to_empty():
    view = merge_slot_view(_slot(waiters={"not": "a list"}))
    assert view["waiters"] == []


def test_view_metadata_as_json_string_is_parsed():
    """Defensive: bd usually emits metadata as a dict, but a stringified
    payload must still render rather than crash."""
    bead = _slot(status="in_progress")
    bead["metadata"] = '{"holder": "agent-2", "waiters": ["agent-5"]}'
    view = merge_slot_view(bead)
    assert view["holder"] == "agent-2"
    assert view["waiters"] == ["agent-5"]


# ----- re-export surface -----


def test_merge_slot_helpers_reexported_from_derive():
    assert derive.is_merge_slot(_slot())
    assert derive.merge_slot_view(_slot()) is not None
