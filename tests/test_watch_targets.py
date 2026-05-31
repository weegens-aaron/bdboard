"""Tests for BdClient.watch_targets (bdboard-3sf).

Regression guard for the file-descriptor exhaustion bug: the watcher used to
call ``awatch(.beads/, recursive=True)`` over the WHOLE .beads/ tree. On macOS
(kqueue backend) recursive watching opens one fd per watched directory/file,
and dolt's churning ``.beads/embeddeddolt/<db>/.dolt/noms/`` object store has a
large, constantly-changing file set — so the process blew past its
RLIMIT_NOFILE soft limit (often 256). Once fds ran out, every new fd-needing
operation failed, most visibly ``asyncio.create_subprocess_exec`` (so
``bd list --json`` snapshot refresh AND ``bd show`` bead-detail both crashed
with ``OSError [Errno 24] Too many open files``).

The fix: watch a SMALL, fixed set of directories NON-recursively — the per-db
dolt ``noms/`` dirs (where manifest/journal.idx mutate on every bd write) plus
``.beads/`` itself. These tests pin that contract.
"""

from __future__ import annotations

from pathlib import Path

from bdboard.bd import BdClient


def _make_workspace(tmp_path: Path, db_names: list[str]) -> Path:
    """Build a fake bd workspace with dolt noms/ dirs for each db name."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    embedded = beads / "embeddeddolt"
    embedded.mkdir()
    for name in db_names:
        noms = embedded / name / ".dolt" / "noms"
        noms.mkdir(parents=True)
        # Simulate dolt's churn — files that the OLD recursive watcher would
        # each have eaten an fd for.
        (noms / "manifest").write_text("x")
        (noms / "journal.idx").write_text("y")
        oldgen = noms / "oldgen"
        oldgen.mkdir()
        (oldgen / "junk").write_text("z")
    return tmp_path


def test_targets_include_each_noms_dir(tmp_path):
    ws = _make_workspace(tmp_path, ["bdboard", "beads"])
    client = BdClient(workspace=ws)

    targets = client.watch_targets()

    beads = ws / ".beads"
    expected_noms = {
        beads / "embeddeddolt" / "bdboard" / ".dolt" / "noms",
        beads / "embeddeddolt" / "beads" / ".dolt" / "noms",
    }
    assert expected_noms.issubset(set(targets))
    # .beads/ itself is included as a cheap catch-all for new dbs.
    assert beads in targets


def test_targets_are_directories_not_recursive_tree(tmp_path):
    """Every target must be an existing directory — awatch(non-recursive)
    only opens fds for the dirs we hand it, NOT their churning subtrees."""
    ws = _make_workspace(tmp_path, ["bdboard"])
    client = BdClient(workspace=ws)

    targets = client.watch_targets()

    assert targets, "expected at least one watch target"
    for t in targets:
        assert t.is_dir(), f"{t} is not a directory"


def test_targets_bounded_not_whole_tree(tmp_path):
    """The whole bug was watching hundreds of dirs. The target count must be
    bounded to (#dbs + 1), regardless of how much junk lives under noms/."""
    ws = _make_workspace(tmp_path, ["bdboard", "beads"])
    # Pile extra churn into a noms/ subtree to mimic real-world fd pressure.
    deep = ws / ".beads" / "embeddeddolt" / "bdboard" / ".dolt" / "noms" / "oldgen"
    for i in range(50):
        (deep / f"obj{i}").write_text("data")

    targets = BdClient(workspace=ws).watch_targets()

    # 2 dbs -> 2 noms dirs + .beads/ itself == 3. NOT 50+.
    assert len(targets) == 3


def test_no_embeddeddolt_falls_back_to_beads_dir(tmp_path):
    """A brand-new / JSONL-only workspace has no embeddeddolt yet; we should
    still watch .beads/ so the workspace is observed once dolt appears."""
    beads = tmp_path / ".beads"
    beads.mkdir()
    client = BdClient(workspace=tmp_path)

    targets = client.watch_targets()

    assert targets == [beads]


def test_no_beads_dir_yields_no_targets(tmp_path):
    """No .beads/ at all -> empty target list (watcher sleeps + retries)."""
    client = BdClient(workspace=tmp_path)

    assert client.watch_targets() == []


def test_skips_db_dir_without_noms(tmp_path):
    """A db dir lacking a .dolt/noms/ must not produce a phantom target."""
    ws = _make_workspace(tmp_path, ["bdboard"])
    # Stray dir under embeddeddolt with no .dolt/noms — e.g. a temp/backup.
    (ws / ".beads" / "embeddeddolt" / "strays").mkdir()

    targets = BdClient(workspace=ws).watch_targets()

    beads = ws / ".beads"
    assert (beads / "embeddeddolt" / "bdboard" / ".dolt" / "noms") in targets
    assert (beads / "embeddeddolt" / "strays") not in targets
