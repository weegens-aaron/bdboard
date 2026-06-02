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


# --- watch_signature: stale-watch-target detection (bdboard-xbc7 #2) ---------
#
# awatch enumerates its paths ONCE on entry. On macOS the kqueue backend
# watches the INODE, not the path, so a noms/ dir replaced atomically (dolt
# rename-over) or a brand-new db created after startup goes unobserved.
# watch_signature() fingerprints (path, st_dev, st_ino) so the watcher's
# rescan poller can detect the drift and re-enumerate.


def test_signature_changes_when_new_db_appears(tmp_path):
    """A db created AFTER the first signature snapshot must change it, so the
    watcher knows to re-enumerate and start observing the new noms/ dir."""
    ws = _make_workspace(tmp_path, ["bdboard"])
    client = BdClient(workspace=ws)

    before = client.watch_signature()

    # Simulate `bd` creating a second dolt db after startup.
    new_noms = ws / ".beads" / "embeddeddolt" / "second" / ".dolt" / "noms"
    new_noms.mkdir(parents=True)
    (new_noms / "manifest").write_text("x")

    after = client.watch_signature()

    assert after != before
    # The new noms/ dir's path is represented in the post-creation signature.
    assert any(str(new_noms) == path for (path, _dev, _ino) in after)


def test_signature_changes_when_noms_inode_replaced(tmp_path):
    """dolt atomically replacing a noms/ dir (same path, NEW inode) must change
    the signature — this is the macOS dead-inode case the kqueue watch can't
    see on its own."""
    ws = _make_workspace(tmp_path, ["bdboard"])
    client = BdClient(workspace=ws)
    noms = ws / ".beads" / "embeddeddolt" / "bdboard" / ".dolt" / "noms"

    before = client.watch_signature()
    before_ino = {ino for (path, _dev, ino) in before if path == str(noms)}
    assert before_ino, "noms/ should be in the baseline signature"

    # Atomically replace noms/ with a fresh directory at the SAME path — new
    # inode, identical path. (rename-over is how dolt swaps object stores;
    # macOS os.replace can't overwrite a non-empty dir, so we drop the old
    # one first — the inode-change is what matters for the signature.)
    import shutil

    replacement = ws / ".beads" / "embeddeddolt" / "bdboard" / ".dolt" / "noms_new"
    replacement.mkdir()
    (replacement / "manifest").write_text("x")
    shutil.rmtree(noms)
    replacement.replace(noms)  # rename to the original path — new inode

    after = client.watch_signature()
    after_ino = {ino for (path, _dev, ino) in after if path == str(noms)}

    assert after != before, "inode swap must change the signature"
    assert after_ino and after_ino != before_ino, "st_ino should differ post-swap"


def test_signature_stable_when_only_file_contents_change(tmp_path):
    """Plain bd writes mutate files INSIDE noms/ (manifest, journal.idx) but
    leave the watched dir inodes intact — the signature must stay stable so
    the rescan poller does NOT needlessly tear down and rebuild the watch.
    (awatch itself still fires on those content changes; signature is only
    for structural drift.)"""
    ws = _make_workspace(tmp_path, ["bdboard"])
    client = BdClient(workspace=ws)
    noms = ws / ".beads" / "embeddeddolt" / "bdboard" / ".dolt" / "noms"

    before = client.watch_signature()
    # Mutate file contents the way a bd write does — dir inodes unchanged.
    (noms / "manifest").write_text("new-manifest-bytes")
    (noms / "journal.idx").write_text("new-journal-bytes")
    after = client.watch_signature()

    assert after == before
