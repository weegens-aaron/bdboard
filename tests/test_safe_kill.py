"""Regression tests for the unguarded ``proc.kill()`` race (bdboard-1e5f).

THE BUG
-------
The subprocess helpers in ``bdboard.bd`` (``_run_json``, ``pour_formula``,
``_run_mutate``) wrap ``proc.communicate()`` in ``asyncio.wait_for`` and, on
the cleanup paths (TimeoutError / BaseException), call ``proc.kill()`` followed
by a draining ``communicate()``. When the in-flight refresh is cancelled by the
app.py debounce task, the subprocess has often *already exited*. Under uvloop
``UVProcessTransport._check_proc`` then raises ``ProcessLookupError`` from
``kill()``, which:

1. MASKS the original ``CancelledError`` (breaks cooperative cancellation),
2. SKIPS the follow-up draining ``communicate()`` (fd leak), and
3. being a plain ``Exception``, propagates up through ``list_active`` into
   ``Store.refresh``'s ``except Exception`` -> logs 'bd list failed; keeping
   previous snapshot', returns False, fires NO SSE broadcast -> the board
   stops syncing. This is the user-visible bug.

THE FIX
-------
``bdboard.bd._safe_kill`` swallows ``ProcessLookupError`` (an already-dead
process IS the intended outcome of kill, so it's a successful no-op), and every
cleanup branch routes through it so the draining ``communicate()`` still runs
and the real (cancellation/timeout) error propagates unmasked.

These tests stub ``asyncio.create_subprocess_exec`` with a fake process whose
``kill()`` raises ``ProcessLookupError`` to lock in the regression without
shelling a real bd.
"""

from __future__ import annotations

import asyncio

import pytest

from bdboard import bd as bd_module
from bdboard.bd import BdClient, _safe_kill


class _FakeProc:
    """A minimal stand-in for ``asyncio.subprocess.Process``.

    ``communicate`` behaviour is driven by ``mode``:

    - ``"cancel"``: the first call raises ``CancelledError`` (simulating the
      debounce task cancelling an in-flight refresh mid-read); the second call
      (the drain after kill) returns empty output.
    - ``"timeout"``: the first call hangs forever so ``wait_for`` raises
      ``TimeoutError``; the second call (drain) returns empty output.

    ``kill`` always raises ``ProcessLookupError`` to reproduce the uvloop
    already-exited race. ``kill_calls`` / ``communicate_calls`` record usage so
    tests can assert the drain still runs after a safe-kill.
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.returncode = 0
        self.kill_calls = 0
        self.communicate_calls = 0

    async def communicate(self, input=None):  # noqa: A002 - mirrors stdlib name
        self.communicate_calls += 1
        if self.communicate_calls == 1:
            if self.mode == "cancel":
                raise asyncio.CancelledError()
            if self.mode == "timeout":
                # Hang so the surrounding wait_for times out.
                await asyncio.sleep(3600)
        # Second call == the post-kill drain. Return empty pipes.
        return b"", b""

    def kill(self) -> None:
        # The process already exited; uvloop surfaces this as ProcessLookupError.
        self.kill_calls += 1
        raise ProcessLookupError("[Errno 3] No such process")


def _install_fake_proc(monkeypatch, mode: str) -> _FakeProc:
    proc = _FakeProc(mode)

    async def fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(bd_module.asyncio, "create_subprocess_exec", fake_exec)
    return proc
    return proc


# ----- _safe_kill unit behaviour -----


def test_safe_kill_swallows_process_lookup_error() -> None:
    """An already-dead process must make _safe_kill a no-op, not raise."""

    class _Dead:
        def kill(self) -> None:
            raise ProcessLookupError()

    # Must not raise.
    _safe_kill(_Dead())  # type: ignore[arg-type]


def test_safe_kill_propagates_other_errors() -> None:
    """_safe_kill only swallows ProcessLookupError; other errors bubble up so
    we never hide a genuinely broken kill (e.g. PermissionError)."""

    class _Stubborn:
        def kill(self) -> None:
            raise PermissionError("nope")

    with pytest.raises(PermissionError):
        _safe_kill(_Stubborn())  # type: ignore[arg-type]


def test_safe_kill_calls_kill_on_live_proc() -> None:
    """The happy path: a live process is actually killed."""
    killed = []

    class _Live:
        def kill(self) -> None:
            killed.append(True)

    _safe_kill(_Live())  # type: ignore[arg-type]
    assert killed == [True]


# ----- cancellation race through the real subprocess helpers -----


def test_run_json_cancel_propagates_not_process_lookup(monkeypatch) -> None:
    """The core regression: when communicate() is cancelled and kill() raises
    ProcessLookupError, the ORIGINAL CancelledError must propagate (cooperative
    cancellation preserved) and the draining communicate() must still run."""
    proc = _install_fake_proc(monkeypatch, mode="cancel")
    client = BdClient(bd_bin="bd")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client._run_json(["list"], timeout=5.0))

    assert proc.kill_calls == 1, "cleanup must attempt the kill"
    assert proc.communicate_calls == 2, "the draining communicate() must still run"


def test_list_active_cancel_does_not_surface_process_lookup(monkeypatch) -> None:
    """End-to-end via the public entry point Store.refresh uses: a cancellation
    must NOT surface as ProcessLookupError (a plain Exception), which is what
    used to get swallowed by Store.refresh's 'except Exception' and silently
    stop the board syncing."""
    _install_fake_proc(monkeypatch, mode="cancel")
    client = BdClient(bd_bin="bd")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client.list_active())


def test_run_mutate_cancel_propagates_not_process_lookup(monkeypatch) -> None:
    """_run_mutate (writes) shares the same cleanup race; verify it too."""
    proc = _install_fake_proc(monkeypatch, mode="cancel")
    client = BdClient(bd_bin="bd")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client._run_mutate(["update", "x", "--status", "open"], timeout=5.0))

    assert proc.kill_calls == 1
    assert proc.communicate_calls == 2


def test_pour_formula_cancel_propagates_not_process_lookup(monkeypatch) -> None:
    """pour_formula (hybrid mutate+json) shares the same cleanup race too."""
    proc = _install_fake_proc(monkeypatch, mode="cancel")
    client = BdClient(bd_bin="bd")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client.pour_formula("demo", {"repo": "bdboard"}))

    assert proc.kill_calls == 1
    assert proc.communicate_calls == 2


# ----- timeout path also tolerates an already-exited process -----


def test_run_json_timeout_safe_kill_then_drains(monkeypatch) -> None:
    """On timeout, kill() raising ProcessLookupError must not mask the friendly
    timeout RuntimeError, and the draining communicate() must still run."""
    proc = _install_fake_proc(monkeypatch, mode="timeout")
    client = BdClient(bd_bin="bd")

    with pytest.raises(RuntimeError, match="timed out"):
        asyncio.run(client._run_json(["list"], timeout=0.01))

    assert proc.kill_calls == 1
    assert proc.communicate_calls == 2, "drain must still run after a safe-kill on timeout"
