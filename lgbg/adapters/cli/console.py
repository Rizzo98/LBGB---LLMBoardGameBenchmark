"""The `lgbg console` launcher (PRD-v3 FR-8.1 to FR-8.6, SC-9).

This module is the only place that knows where the built browser client lives and how a server is
started. The console itself is an ASGI application that reads records; uvicorn is the transport,
exactly as it is for the v2 HTTP host.

**Loopback only.** A benchmark console that a colleague can reach is a different security model,
and v3 is explicitly a local instrument. A public address is refused before a socket is opened.

**A missing build is an operator error, not a blank page.** The build is a separate, Node-only
step; the command names it rather than starting a server that can only serve 503s.
"""

from __future__ import annotations

import ipaddress
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import uvicorn

from lgbg.console.app import ConsoleApp
from lgbg.console.records import ConsoleError, LogStore

WEB_DIST: Final[Path] = Path(__file__).resolve().parents[3] / "web" / "dist"
"""Where Vite writes the browser client, relative to the checkout."""

BUILD_COMMAND: Final[str] = "pnpm --dir web build"


def run_console(
    *,
    roots: Sequence[Path],
    host: str,
    port: int,
    no_browser: bool,
    dist: Path | None = None,
) -> int:
    """Validate what was asked, print the URL, and serve until interrupted."""
    store = LogStore(roots)
    _ensure_loopback(host)
    _ensure_port(port)
    build = (dist if dist is not None else WEB_DIST).resolve()
    if not (build / "index.html").is_file():
        raise ConsoleError(
            f"the frontend build is missing at {build}; run `{BUILD_COMMAND}` and try again"
        )

    url = f"http://{host}:{port}/"
    print(url)
    if not no_browser:
        webbrowser.open(url)
    run_server(ConsoleApp(store, build), host, port)
    return 0


def run_server(app: ConsoleApp, host: str, port: int) -> None:
    """The one blocking call, kept separate so the launcher can be tested without a socket."""
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _ensure_loopback(host: str) -> None:
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ConsoleError(f"{host!r} is not an address the console can bind") from None
    if not address.is_loopback:
        raise ConsoleError(f"{host} is not a loopback address; the console is local only")


def _ensure_port(port: int) -> None:
    if not 0 < port < 65536:
        raise ConsoleError(f"port {port} is outside the range 1..65535")


__all__ = ["BUILD_COMMAND", "WEB_DIST", "run_console", "run_server"]
