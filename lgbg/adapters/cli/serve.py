"""serve: start a surface for an operator (PRD-v2 FR-14.1).

The command starts one of the two things a process can be:

- the **HTTP host**, an ASGI application served by uvicorn, which exposes sessions over JSON;
- an **MCP server**, in the sandbox profile (an operator may create and end games) or the
  benchmark profile (bound to one seat of one game, and incapable of creating one), over stdio.

A process serves one surface. A stdio MCP server owns stdin and stdout for its whole life, so the
two are not started together: an operator who wants both starts the host, then points a client at
it. That is stated rather than left for the operator to discover when one of them stops answering.

The profile is fixed when the server is constructed - it is an argument of this command, not a
request value - and the session a benchmark surface serves is created here, by the operator's
process, exactly as the runner creates one before handing the surface to a model.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import anyio
import uvicorn

from lgbg.adapters.mcp.benchmark import benchmark_surface
from lgbg.adapters.mcp.sandbox import sandbox_surface
from lgbg.adapters.mcp.server import McpSurface, Profile, serve_stdio
from lgbg.core.config import AssistLevel, ConfigError
from lgbg.host.http import HttpHost


def serve(
    *,
    game: str | None,
    http: str | None,
    mcp: str | None,
    player: int | None,
    seed: int,
    players: int,
    session_id: str,
    protocol: str,
    record_dir: Path | None,
    assist: AssistLevel,
    detail: str,
    game_options: Mapping[str, Any],
) -> int:
    """Start the surface the operator chose. Returns a process exit code."""
    if http is None and mcp is None:
        raise ConfigError("serve needs --http HOST:PORT, --mcp sandbox, or --mcp benchmark")
    if http is not None and mcp is not None:
        raise ConfigError(
            "serve starts one surface per process: an MCP stdio server owns stdin and stdout, "
            "so run the HTTP host in another process"
        )
    if http is not None:
        if game_options:
            raise ConfigError(
                "game options apply to a benchmark session; the HTTP host's clients declare them"
            )
        host, port = _address(http)
        run_http(HttpHost(directory=record_dir), host, port)
        return 0
    if mcp is None:
        raise ConfigError("serve needs --http HOST:PORT, --mcp sandbox, or --mcp benchmark")
    if game is None:
        raise ConfigError("an MCP surface serves one game, so --game is required")
    surface = _surface(
        game=game,
        profile=_profile(mcp),
        player=player,
        seed=seed,
        players=players,
        session_id=session_id,
        protocol=protocol,
        record_dir=record_dir,
        assist=assist,
        detail=detail,
        game_options=game_options,
    )
    run_stdio(surface)
    return 0


def _surface(
    *,
    game: str,
    profile: Profile,
    player: int | None,
    seed: int,
    players: int,
    session_id: str,
    protocol: str,
    record_dir: Path | None,
    assist: AssistLevel,
    detail: str,
    game_options: Mapping[str, Any],
) -> McpSurface:
    if profile is Profile.SANDBOX:
        if game_options:
            raise ConfigError(
                "game options apply to a benchmark session; the sandbox's clients declare them in "
                "create_session"
            )
        return sandbox_surface(game, directory=record_dir, assist=assist, detail=detail)
    if player is None:
        raise ConfigError("the benchmark profile serves one seat, so --player is required")
    return benchmark_surface(
        game,
        player=player,
        seed=seed,
        players=players,
        session_id=session_id,
        directory=record_dir,
        assist=assist,
        detail=detail,
        protocol=protocol,
        game_config=game_options,
    )


def _profile(value: str) -> Profile:
    try:
        return Profile(value)
    except ValueError:
        accepted = [profile.value for profile in Profile]
        raise ConfigError(f"profile {value!r} is not one of {accepted}") from None


def _address(value: str) -> tuple[str, int]:
    """'HOST:PORT' as an address, refusing anything that is not one."""
    host, separator, port_text = value.rpartition(":")
    if not separator or not host:
        raise ConfigError(f"--http takes host:port, got {value!r}")
    try:
        port = int(port_text)
    except ValueError:
        raise ConfigError(f"--http port must be an integer, got {port_text!r}") from None
    if not 1 <= port <= 65535:
        raise ConfigError(f"--http port must be between 1 and 65535, got {port}")
    return host, port


def run_http(app: Any, host: str, port: int) -> None:
    """Serve one ASGI application. Separated so a test can see what would be served."""
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_stdio(surface: McpSurface) -> None:
    """Serve one MCP surface over stdin/stdout, one client per process (FR-3.5)."""
    anyio.run(serve_stdio, surface.server)


__all__: Final[list[str]] = [
    "run_http",
    "run_stdio",
    "serve",
]
