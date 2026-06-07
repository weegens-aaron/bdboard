"""Reader for the swarm interaction log (``.beads/interactions.jsonl``).

This is the cross-run audit trail that ``bd audit record`` / ``bd audit label``
append to: one JSON object per line, each an ``int-xxxx`` entry whose ``kind``
is one of ``llm_call`` / ``tool_call`` / ``label`` (the SFT/RL "why did the
agent do that" reward signal) plus the historical ``field_change`` kind that
bd emits for ordinary status/assignee edits.

It is **deliberately distinct** from per-bead ``bd history`` (Dolt snapshots
of a single bead). ``bd history`` answers "how did THIS bead change?";
this log answers "what did the swarm DO across the whole run?". bdboard's
modal Audit/Lifecycle views read the former and never touched the latter —
this module closes that gap.

Pure, dependency-light, and fault-tolerant by design:

* a **missing** file degrades to an empty result (no crash) — a fresh
  workspace simply has no interaction trail yet;
* a **malformed** line is skipped rather than aborting the whole read, so one
  truncated tail write (the file is append-only and may be read mid-write)
  never blanks the viewer.

No I/O caching here — the route reads on demand and the watcher's SSE pulse
drives refreshes, mirroring how the History page reads bd snapshots.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The kinds the swarm audit log is documented to carry, in a sensible display
# order (the reward-bearing ones first, then the legacy field_change). Used to
# order the filter chips deterministically; any *unknown* kind found in the
# file is appended after these alphabetically, so a future bd kind shows up
# without a code change (never silently dropped).
KNOWN_KINDS: tuple[str, ...] = ("llm_call", "tool_call", "label", "field_change")

# Safety cap on how many entries we render at once. The log is append-only and
# unbounded; a multi-thousand-line render would bloat the DOM for no benefit
# since the newest entries are the interesting ones. The route surfaces a
# "showing the most recent N" note when this clamps.
DEFAULT_LIMIT = 500


def log_path(beads_dir: Path) -> Path:
    """Return the path to the interaction log inside a ``.beads/`` directory."""
    return beads_dir / "interactions.jsonl"


def read_interactions(beads_dir: Path) -> list[dict[str, Any]]:
    """Parse every entry from ``interactions.jsonl``, newest-first.

    Args:
        beads_dir: the workspace's ``.beads/`` directory.

    Returns:
        A list of normalized entry dicts (see ``_normalize``), ordered newest
        first by ``created_at``. An empty list when the file is absent or
        contains no parseable entries — callers treat "missing" and "empty"
        identically except for the empty-state copy (use ``log_path().exists()``
        to tell them apart).
    """
    path = log_path(beads_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return []
    except OSError:
        # Permission / transient FS error — degrade rather than 500 the page.
        return []

    entries: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            # One bad/half-written line shouldn't blank the whole viewer.
            continue
        if isinstance(obj, dict):
            entries.append(_normalize(obj))

    # Newest first. created_at is ISO-8601 so a string sort is chronological;
    # entries lacking a timestamp sort to the bottom (empty string).
    entries.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return entries


def filter_by_kind(entries: list[dict[str, Any]], kind: str | None) -> list[dict[str, Any]]:
    """Return only entries whose ``kind`` matches ``kind``.

    A falsy / ``"all"`` ``kind`` is the no-op pass-through (show everything).
    Matching is case-insensitive and whitespace-trimmed so a chip value never
    misses on incidental casing.
    """
    if not kind:
        return entries
    key = kind.strip().lower()
    if key in ("", "all"):
        return entries
    return [e for e in entries if (e.get("kind") or "").lower() == key]


def kind_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count entries per kind for the filter-chip badges.

    Returns an insertion-ordered dict: the ``KNOWN_KINDS`` present (in their
    documented order) first, then any unknown kinds alphabetically — so the
    chip row is deterministic and future-proof.
    """
    raw: dict[str, int] = {}
    for e in entries:
        k = e.get("kind") or "unknown"
        raw[k] = raw.get(k, 0) + 1

    ordered: dict[str, int] = {}
    for k in KNOWN_KINDS:
        if k in raw:
            ordered[k] = raw[k]
    for k in sorted(raw):
        if k not in ordered:
            ordered[k] = raw[k]
    return ordered


def _normalize(obj: dict[str, Any]) -> dict[str, Any]:
    """Coerce a raw log object into a stable shape for the template.

    Keeps the well-known top-level fields, folds everything else into
    ``extra`` (so kind-specific payloads like ``model``/``tool_name``/
    ``reward`` are preserved whether bd nested them under ``extra`` or wrote
    them flat), and precomputes a one-line ``summary`` + the ``details``
    key/value pairs the row's expandable view renders.
    """
    standard = {"id", "kind", "created_at", "actor", "issue_id", "extra"}
    extra: dict[str, Any] = {}
    # bd nests payloads under "extra"; merge any that are there.
    nested = obj.get("extra")
    if isinstance(nested, dict):
        extra.update(nested)
    # Tolerate flat schemas too: any non-standard top-level key joins extra.
    for k, v in obj.items():
        if k not in standard:
            extra[k] = v

    return {
        "id": obj.get("id") or "",
        "kind": obj.get("kind") or "unknown",
        "created_at": obj.get("created_at") or "",
        "actor": obj.get("actor") or "",
        "issue_id": obj.get("issue_id") or "",
        "extra": extra,
        "summary": _summarize(obj.get("kind") or "", extra),
        "details": _details(extra),
    }


def _summarize(kind: str, extra: dict[str, Any]) -> str:
    """Build a compact, human one-liner for a row, by kind.

    Falls back to "" (the template then just shows the kind + timestamp) for
    any kind/payload we don't have a bespoke phrasing for, so an unrecognized
    entry still renders cleanly.
    """
    k = (kind or "").lower()
    if k == "field_change":
        field = extra.get("field") or "field"
        old = _short(extra.get("old_value"))
        new = _short(extra.get("new_value"))
        base = f"{field}: {old} \u2192 {new}"
        reason = extra.get("reason")
        return f"{base} ({reason})" if reason else base
    if k == "llm_call":
        model = extra.get("model")
        return f"model {model}" if model else "LLM call"
    if k == "tool_call":
        tool = extra.get("tool_name") or extra.get("tool")
        code = extra.get("exit_code")
        if tool and code is not None:
            return f"{tool} (exit {code})"
        if tool:
            return str(tool)
        return "tool call"
    if k == "label":
        reward = extra.get("reward")
        parent = extra.get("parent_id")
        bits = []
        if reward is not None:
            bits.append(f"reward {reward}")
        if parent:
            bits.append(f"on {parent}")
        return " ".join(bits) if bits else "label"
    return ""


def _details(extra: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten the ``extra`` payload into ordered (key, value) display pairs.

    Values are stringified; nested structures are JSON-dumped compactly so the
    expandable detail view never chokes on a dict/list payload.
    """
    pairs: list[tuple[str, str]] = []
    for key in sorted(extra):
        val = extra[key]
        if isinstance(val, (dict, list)):
            try:
                rendered = json.dumps(val, ensure_ascii=False, sort_keys=True)
            except (TypeError, ValueError):
                rendered = str(val)
        else:
            rendered = "" if val is None else str(val)
        pairs.append((key, rendered))
    return pairs


def _short(val: Any, limit: int = 60) -> str:
    """Stringify a value for a one-liner, mapping empty/None to the ∅ glyph."""
    if val is None or val == "":
        return "\u2205"  # EMPTY SET — reads as "nothing" in the summary
    s = str(val)
    if len(s) > limit:
        return s[: limit - 1] + "\u2026"
    return s
