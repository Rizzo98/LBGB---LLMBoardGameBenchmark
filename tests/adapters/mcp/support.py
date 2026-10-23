"""Shared setup for the MCP adapter's tests (PRD-v2 FR-3).

The adapter is a transport, so the tests drive it the way a client would: through the official
SDK's in-memory transport for the unit-level claims, and through a real subprocess for stdio.
Nothing here reaches the network.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from lgbg.adapters.mcp.server import McpSurface, Profile, build_server
from lgbg.core.config import AssistLevel, RunConfig
from lgbg.core.types import GameId
from lgbg.host.facade import SessionFacade

TESTS: Path = Path(__file__).resolve().parents[2]
REPO: Path = TESTS.parent


def run(coroutine: Any) -> Any:
    """Run one client scenario to completion on a fresh event loop."""
    return asyncio.run(coroutine)


def config(*, players: int = 2, seed: int = 1, assist: AssistLevel = AssistLevel.L1) -> RunConfig:
    return RunConfig(seed=seed, players=players, interaction_protocol="decline_only", assist=assist)


def bound_surface(
    directory: Path,
    *,
    game: str = "fixture",
    player: int = 0,
    players: int = 2,
    assist: AssistLevel = AssistLevel.L1,
) -> tuple[McpSurface, SessionFacade, GameId]:
    """A benchmark surface over one live session, which is what the runner gives a model."""
    facade = SessionFacade()
    game_id = facade.create_session(
        game, config(players=players, assist=assist), directory=directory
    )
    surface = build_server(
        facade,
        game,
        profile=Profile.BENCHMARK,
        session_id=game_id,
        player=player,
        assist=assist,
    )
    return surface, facade, game_id


async def listed_tools(surface: McpSurface) -> list[types.Tool]:
    async with create_connected_server_and_client_session(surface.server) as client:
        return list((await client.list_tools()).tools)


async def listed_resources(surface: McpSurface) -> list[types.Resource]:
    async with create_connected_server_and_client_session(surface.server) as client:
        return list((await client.list_resources()).resources)
