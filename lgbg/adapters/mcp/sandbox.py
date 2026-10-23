"""The sandbox entry point: the operator's process, over stdio (PRD-v2 FR-3.4a, SC-14).

The sandbox is the only profile that can create a session, list the open ones and end them. It is
constructed once with that capability; a benchmark process constructs none of it, which is what
makes the absence a fact rather than a branch.
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
from lgbg.core.config import AssistLevel, ConfigError
from lgbg.core.game import GamePluginError
from lgbg.host.facade import SessionFacade


def sandbox_surface(
    game: str,
    *,
    directory: Path | None = None,
    assist: AssistLevel = AssistLevel.L1,
    detail: str = DEFAULT_DETAIL,
) -> McpSurface:
    """Build the sandbox profile: lifecycle tools plus the generated action tools."""
    return build_server(
        SessionFacade(),
        game,
        profile=Profile.SANDBOX,
        assist=assist,
        detail=detail,
        directory=directory,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lgbg.adapters.mcp.sandbox",
        description="Serve the sandbox MCP profile over stdio.",
    )
    parser.add_argument("--game", required=True, help="a registered game name")
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
        help="what the resources reveal, fixed for the process",
    )
    parser.add_argument("--detail", default=DEFAULT_DETAIL, help="the renderer's detail level")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for module in args.plugin:
            importlib.import_module(module)
        surface = sandbox_surface(
            args.game,
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
