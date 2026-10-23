"""The benchmark entry point: a model's process, over stdio (PRD-v2 FR-3.4a, FR-3.4c).

This process is deliberately incapable of creating, listing or ending a game. The runner creates
the live session and launches this entry point bound to one seat; the lifecycle tools are never
constructed here, so no request, malformed or otherwise, can reach one.

The session is created here only because a standalone process must have something to serve. In a
scored run the runner supplies the same facade and session id in-process or through the host; the
surface this module builds is identical either way.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

import anyio

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.mcp.server import (
    DEFAULT_DETAIL,
    McpSurface,
    Profile,
    build_server,
    serve_stdio,
)
from lgbg.core.config import AssistLevel, ConfigError, RunConfig
from lgbg.core.game import GamePluginError
from lgbg.host.facade import SessionFacade

DEFAULT_SESSION_ID = "g-0001"


def benchmark_surface(
    game: str,
    *,
    player: int,
    seed: int = 1,
    players: int = 4,
    session_id: str = DEFAULT_SESSION_ID,
    directory: Path | None = None,
    assist: AssistLevel = AssistLevel.L1,
    detail: str = DEFAULT_DETAIL,
) -> McpSurface:
    """Build the benchmark profile over one session, as the runner would hand it to a model."""
    facade = SessionFacade()
    game_id = facade.create_session(
        game,
        RunConfig(
            seed=seed,
            players=players,
            interaction_protocol="decline_only",
            assist=assist,
        ),
        game_id=session_id,
        directory=directory,
    )
    return build_server(
        facade,
        game,
        profile=Profile.BENCHMARK,
        session_id=game_id,
        player=player,
        assist=assist,
        detail=detail,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lgbg.adapters.mcp.benchmark",
        description="Serve the benchmark MCP profile over stdio.",
    )
    parser.add_argument("--game", required=True, help="a registered game name")
    parser.add_argument("--player", required=True, type=int, help="the seat this process serves")
    parser.add_argument("--seed", type=int, default=1, help="the seed the run starts from")
    parser.add_argument("--players", type=int, default=4, help="seats in the run")
    parser.add_argument("--session-id", default=DEFAULT_SESSION_ID, help="the id of the session")
    parser.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="MODULE",
        help="import a module that registers games; repeatable",
    )
    parser.add_argument("--record-dir", default=None, help="the run directory to record into")
    parser.add_argument(
        "--assist",
        choices=[level.value for level in AssistLevel],
        default=AssistLevel.L1.value,
        help="what the resources reveal, fixed for the run",
    )
    parser.add_argument("--detail", default=DEFAULT_DETAIL, help="the renderer's detail level")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for module in args.plugin:
            importlib.import_module(module)
        surface = benchmark_surface(
            args.game,
            player=args.player,
            seed=args.seed,
            players=args.players,
            session_id=args.session_id,
            directory=None if args.record_dir is None else Path(args.record_dir),
            assist=AssistLevel(args.assist),
            detail=args.detail,
        )
    except (ConfigError, GamePluginError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    anyio.run(serve_stdio, surface.server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
