"""CLI entry point. Sets env, picks a free port, starts uvicorn, optionally opens browser."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import typer
import uvicorn

# How many consecutive ports we'll try before giving up. With the default
# start port 7332, this means 7332..7351 are searched — plenty of room for
# many concurrent bdboard instances, but bounded so we don't probe forever.
PORT_SEARCH_RANGE = 20


def _run(
    addr: str = typer.Option("127.0.0.1:7332", help="HTTP listen address"),
    no_browser: bool = typer.Option(False, "--no-browser", help="don't auto-launch"),
    bd_bin: str = typer.Option("bd", "--bd", help="path to bd binary"),
    workspace: Path = typer.Option(
        None, "--dir", help="workspace dir (default: cwd)"
    ),
    strict_port: bool = typer.Option(
        False,
        "--strict-port",
        help="fail if the requested port is taken instead of auto-incrementing",
    ),
) -> None:
    """Start the bdboard HTTP server."""
    ws = _resolve_workspace(workspace)
    os.environ["BDBOARD_WORKSPACE"] = str(ws)
    os.environ["BDBOARD_BD_BIN"] = bd_bin

    host, _, port_s = addr.partition(":")
    requested_port = int(port_s or "7332")

    port = _pick_port(host, requested_port, strict=strict_port)
    if port != requested_port:
        typer.echo(
            f"port {requested_port} busy — using {port} instead "
            f"(another bdboard running?)"
        )

    if not no_browser:
        # Defer the browser open until uvicorn is actually listening.
        threading.Thread(
            target=_open_when_ready, args=(host, port), daemon=True
        ).start()

    uvicorn.run("bdboard.app:app", host=host, port=port, log_level="info")


def _resolve_workspace(explicit: Path | None) -> Path:
    """Figure out which directory bdboard should treat as the workspace.

    Order of preference:
      1. `--dir` if the user passed it (always wins, never second-guessed)
      2. `Path.cwd()` — normal case for a shell session in a project dir
      3. `$PWD` env var — fallback when getcwd() is blocked by macOS TCC
         (iCloud Drive, Desktop, Documents and similar sandboxed paths
         deny getcwd to unsigned binaries, but the shell still knows its
         own cwd and passes it through PWD). Catches the common case
         of running bdboard inside an iCloud-synced repo.
      4. Friendly error + exit 1. Beats a raw PermissionError traceback.
    """
    if explicit:
        return explicit.resolve()
    try:
        return Path.cwd().resolve()
    except (PermissionError, OSError):
        pass
    pwd = os.environ.get("PWD")
    if pwd:
        try:
            return Path(pwd).resolve()
        except (PermissionError, OSError):
            pass
    typer.echo(
        "bdboard: can't determine the current directory (macOS sandboxing "
        "often blocks this in iCloud / Documents / Desktop folders).\n"
        "Pass --dir /path/to/workspace explicitly to work around it.",
        err=True,
    )
    raise SystemExit(1)


def _pick_port(host: str, start_port: int, strict: bool) -> int:
    """Return the first bindable port at or after start_port.

    Probes by attempting a real bind on the given host (not just localhost),
    so we honor whatever interface the user asked for. If `strict` is True,
    only the requested port is tried — useful for scripts/CI that need a
    specific port and would rather fail than silently move.

    Raises SystemExit with a friendly message if no port in the search
    range is available, so the user gets a one-line error instead of a
    uvicorn traceback.
    """
    end = start_port + 1 if strict else start_port + PORT_SEARCH_RANGE
    for port in range(start_port, end):
        if _port_is_free(host, port):
            return port
    if strict:
        typer.echo(
            f"port {start_port} is already in use (use without --strict-port "
            "to auto-pick the next free port)",
            err=True,
        )
    else:
        typer.echo(
            f"no free port in range {start_port}..{end - 1} — "
            "is something hoarding ports? try `lsof -iTCP -sTCP:LISTEN`",
            err=True,
        )
    raise SystemExit(1)


def _port_is_free(host: str, port: int) -> bool:
    """Check if (host, port) is bindable RIGHT NOW. Uses SO_REUSEADDR off
    so we don't false-positive on TIME_WAIT sockets — we want a port we
    can actually serve from, not one that's almost free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _open_when_ready(host: str, port: int) -> None:
    """Poll until the server accepts connections, then open a browser tab.
    Beats sleeping a fixed duration — works fine even on slow imports."""
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    webbrowser.open(f"http://{host}:{port}/")


def main() -> None:
    """Entry point referenced by pyproject `[project.scripts]`."""
    typer.run(_run)
