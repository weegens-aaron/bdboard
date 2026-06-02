"""Regression tests for the live-sync self-feedback wedge (bdboard-ywep).

The Board stopped reflecting bd writes made while it was open; only a
relaunch showed new state. This was a RECURRENCE of the bdboard-xbc7 class
but a DIFFERENT root cause than the one originally suspected ("watcher gets
no FS events"). Empirically the watcher DID receive events. The real bug was
a self-feedback loop:

  1. ``Store.refresh()`` runs ``bd list --json``.
  2. Even a READ-ONLY ``bd list`` makes dolt re-touch ``journal.idx`` and
     rewrite ``manifest`` inside the watched ``.dolt/noms/`` dir.
  3. The watcher fired ~1.3s later for that OWN read.
  4. The old ``RefreshScheduler.notify()`` cancelled the in-flight settle on
     EVERY event — including the self-induced one — and because ``bd list``
     on a large ``noms/`` takes LONGER than the self-trigger latency, the
     refresh was cancelled mid-subprocess every time and NEVER completed.
     Net: no broadcast, frozen board, "fixed" only by relaunch.

The fix has two halves, both pinned here:

  * SCHEDULER: ``notify()`` no longer cancels an in-flight refresh; only the
    debounce/cooldown SLEEP is cancellable. A mid-refresh event sets a dirty
    flag and triggers exactly ONE reconcile pass afterwards.
  * STORE/CLIENT: ``BdClient.revision_signature()`` fingerprints the dolt
    manifest root hash (changes IFF committed state changes). ``Store.refresh``
    SKIPS the ``bd list`` subprocess when that signature is unchanged — i.e.
    when the event was just our own read echoing back — so the loop can't spin.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from bdboard.bd import BdClient
from bdboard.store import Store
from bdboard.watcher import RefreshScheduler

_DEBOUNCE = 0.02
_COOLDOWN = 0.08


# --------------------------------------------------------------------------- #
# Layer 1: BdClient.revision_signature() — the cheap content-based oracle.
# --------------------------------------------------------------------------- #


def _make_db(tmp_path: Path, name: str, manifest_bytes: bytes) -> Path:
    noms = tmp_path / ".beads" / "embeddeddolt" / name / ".dolt" / "noms"
    noms.mkdir(parents=True)
    (noms / "manifest").write_bytes(manifest_bytes)
    (noms / "journal.idx").write_text("journal")
    return noms


def test_revision_signature_empty_without_eddolt(tmp_path):
    """A JSONL-only / brand-new workspace has no dolt manifest, so the
    signature is empty — which Store treats as "no signal, never skip"."""
    (tmp_path / ".beads").mkdir()
    assert BdClient(workspace=tmp_path).revision_signature() == frozenset()


def test_revision_signature_includes_each_db_manifest(tmp_path):
    _make_db(tmp_path, "bdboard", b"root-hash-A")
    _make_db(tmp_path, "beads", b"root-hash-B")
    sig = BdClient(workspace=tmp_path).revision_signature()
    contents = {payload for (_path, payload) in sig}
    assert contents == {b"root-hash-A", b"root-hash-B"}


def test_revision_signature_changes_when_manifest_content_changes(tmp_path):
    """A REAL bd write rewrites the manifest root hash → signature changes
    → Store.refresh must NOT skip → the change is picked up."""
    noms = _make_db(tmp_path, "bdboard", b"root-hash-before")
    client = BdClient(workspace=tmp_path)
    before = client.revision_signature()
    (noms / "manifest").write_bytes(b"root-hash-after")
    assert client.revision_signature() != before


def test_revision_signature_stable_when_only_noise_changes(tmp_path):
    """A read-only bd list jiggles journal.idx/mtimes but leaves the manifest
    root hash identical — the signature must stay stable so Store can take the
    cheap skip path and break the feedback loop."""
    noms = _make_db(tmp_path, "bdboard", b"root-hash-stable")
    client = BdClient(workspace=tmp_path)
    before = client.revision_signature()
    # Simulate a read-only bd list touching the OTHER files but not the
    # manifest's committed root hash.
    (noms / "journal.idx").write_text("journal grew on a read")
    (noms / "nbs_manifest_123").write_text("transient")
    assert client.revision_signature() == before


# --------------------------------------------------------------------------- #
# Layer 2: Store.refresh() skips bd list when the revision is unchanged.
# --------------------------------------------------------------------------- #


class _FakeBd:
    """Minimal BdClient stand-in recording list_active calls and serving a
    scriptable revision_signature()."""

    def __init__(self) -> None:
        self.list_calls = 0
        self.revision = frozenset({("/m", b"v1")})
        self.active = [{"id": "a-1", "title": "one", "status": "open"}]
        self.closed: list[dict] = []

    def revision_signature(self):
        return self.revision

    async def list_active(self):
        self.list_calls += 1
        return list(self.active)

    async def list_closed(self):
        self.list_calls += 1
        return list(self.closed)

    def invalidate_caches(self):
        pass


def test_store_refresh_skips_bd_list_when_revision_unchanged(tmp_path):
    """The headline loop-breaker: a refresh with an UNCHANGED manifest
    signature must NOT spawn another bd list and must report no change."""

    async def scenario():
        bd = _FakeBd()
        store = Store(bd)  # type: ignore[arg-type]
        first = await store.refresh()  # populates cache, records revision
        calls_after_first = bd.list_calls
        # Watcher fires again for our OWN read — signature identical.
        second = await store.refresh()
        return first, second, calls_after_first, bd.list_calls

    first, second, calls_after_first, calls_after_second = asyncio.run(scenario())
    assert first is True, "initial refresh should report change (cache was empty)"
    assert calls_after_first == 2, "first refresh fetches active+closed once each"
    assert second is False, "unchanged-revision refresh must report no change"
    assert calls_after_second == calls_after_first, "skip path must NOT call bd list again"


def test_store_refresh_runs_bd_list_when_revision_changes(tmp_path):
    """A real write bumps the manifest signature → Store must re-query and
    detect the changed bead list."""

    async def scenario():
        bd = _FakeBd()
        store = Store(bd)  # type: ignore[arg-type]
        await store.refresh()
        calls_after_first = bd.list_calls
        # Real write: new root hash + changed bead data.
        bd.revision = frozenset({("/m", b"v2")})
        bd.active = [{"id": "a-1", "title": "EDITED", "status": "open"}]
        changed = await store.refresh()
        return changed, calls_after_first, bd.list_calls

    changed, calls_after_first, calls_after_second = asyncio.run(scenario())
    assert changed is True
    assert calls_after_second > calls_after_first, "changed revision must re-query bd"


def test_store_refresh_never_skips_without_dolt_signal(tmp_path):
    """An empty signature (legacy JSONL-only workspace) means "no signal";
    Store must NOT take the skip path or live-sync would break there."""

    async def scenario():
        bd = _FakeBd()
        bd.revision = frozenset()  # no embedded dolt
        store = Store(bd)  # type: ignore[arg-type]
        await store.refresh()
        calls_after_first = bd.list_calls
        await store.refresh()  # same empty signature — must STILL query
        return calls_after_first, bd.list_calls

    calls_after_first, calls_after_second = asyncio.run(scenario())
    assert calls_after_second > calls_after_first, "empty signature must never skip"


# --------------------------------------------------------------------------- #
# Layer 3: RefreshScheduler does not cancel an in-flight refresh.
# --------------------------------------------------------------------------- #


def test_inflight_refresh_is_not_cancelled_by_self_event():
    """THE root-cause regression: an event arriving WHILE refresh() runs must
    NOT cancel it. Pre-fix, notify() cancelled the in-flight refresh, so the
    slow `bd list` (slower than the self-trigger latency) never completed and
    the board never broadcast. Post-fix the refresh completes AND a single
    reconcile pass runs for the mid-flight event.
    """

    async def scenario():
        completed = []
        refresh_calls = {"n": 0}
        broadcasts = {"n": 0}
        started = asyncio.Event()

        async def refresh():
            refresh_calls["n"] += 1
            if refresh_calls["n"] == 1:
                started.set()
                # Simulate a SLOW bd list. The self-induced FS event lands
                # during this window and must NOT abort us.
                await asyncio.sleep(_DEBOUNCE * 4)
                completed.append("first")
                return True  # real change → broadcast
            # Reconcile pass for the mid-flight (self) event: nothing new.
            return False

        async def broadcast():
            broadcasts["n"] += 1

        sched = RefreshScheduler(refresh, broadcast, debounce_s=_DEBOUNCE, cooldown_s=_COOLDOWN)
        sched.notify()  # first write
        await started.wait()  # refresh is now mid-flight
        sched.notify()  # self-induced event WHILE refresh runs
        # Give the first refresh + the reconcile pass time to finish.
        await asyncio.sleep(_DEBOUNCE * 8 + _COOLDOWN)
        return completed, refresh_calls["n"], broadcasts["n"]

    completed, n_refresh, n_broadcast = asyncio.run(scenario())
    assert completed == ["first"], "in-flight refresh was cancelled before completing"
    assert n_broadcast == 1, "the real change must broadcast exactly once"
    assert n_refresh >= 2, "the mid-flight event must trigger a reconcile pass"
