"""Profiles, absence, and the stdio entry points (PRD-v2 FR-3.4 to PRD-v2 FR-3.5).

The benchmark process must not hold a lifecycle capability at all: absence is testable, intent is
not. The sandbox process holds the lifecycle tools and serves a live session over real stdio,
which is the transport a client actually launches.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextResourceContents

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.mcp.benchmark import benchmark_surface
from lgbg.adapters.mcp.sandbox import sandbox_surface
from lgbg.adapters.mcp.server import LIFECYCLE_TOOLS, McpSurface, Profile
from tests.adapters.mcp.support import REPO, run
from tests.games.fixture_game import FixtureGame  # noqa: F401

LIFECYCLE = frozenset({"create_session", "list_sessions", "end_session"})


async def names(surface: McpSurface) -> set[str]:
    async with create_connected_server_and_client_session(surface.server) as client:
        return {tool.name for tool in (await client.list_tools()).tools}


def test_the_benchmark_profile_serves_no_lifecycle_tool() -> None:
    """PRD-v2 FR-3.4b: the benchmark entry point's served tool list contains no lifecycle tool."""
    surface = benchmark_surface("fixture", player=0, seed=1, players=2)
    served = run(names(surface))

    assert served, "control: a benchmark surface still serves the action tools"
    assert served.isdisjoint(LIFECYCLE_TOOLS)
    assert served.isdisjoint(LIFECYCLE)


def test_the_sandbox_profile_serves_the_lifecycle_tools() -> None:
    """PRD-v2 FR-3.4: the sandbox is the operator surface, so it may create and end sessions."""
    surface = sandbox_surface("fixture")

    assert run(names(surface)) >= LIFECYCLE


def test_the_profile_is_fixed_when_the_server_is_constructed() -> None:
    """PRD-v2 FR-3.4: neither a request nor a configuration value can move a benchmark process."""
    surface = benchmark_surface("fixture", player=0, seed=1, players=2)

    assert surface.profile is Profile.BENCHMARK
    assert not hasattr(surface, "set_profile")
    with pytest.raises(AttributeError):
        surface.profile = Profile.SANDBOX  # type: ignore[misc]
    tools = run(names(surface))
    for lifecycle in LIFECYCLE:
        assert lifecycle not in tools


def test_a_sandbox_session_can_be_created_listed_and_ended(tmp_path: Path) -> None:
    """The lifecycle tools are the facade's own operations, not a second session registry."""
    surface = sandbox_surface("fixture", directory=tmp_path)

    async def scenario() -> tuple[str, list[str], list[str]]:
        async with create_connected_server_and_client_session(surface.server) as client:
            created = await client.call_tool("create_session", {"seed": 4, "players": 2})
            assert created.structuredContent is not None
            game_id = str(created.structuredContent["session_id"])
            listed = await client.call_tool("list_sessions", {})
            await client.call_tool("end_session", {"session_id": game_id})
            after = await client.call_tool("list_sessions", {})
        assert listed.structuredContent is not None
        assert after.structuredContent is not None
        return (
            game_id,
            list(listed.structuredContent["sessions"]),
            list(after.structuredContent["sessions"]),
        )

    game_id, listed, after = run(scenario())

    assert game_id.startswith("g-")
    assert listed == [game_id]
    assert after == []


def test_the_benchmark_entry_point_over_stdio_serves_a_live_session(tmp_path: Path) -> None:
    """PRD-v2 FR-3.5: stdio is one server per client, and the served tools act on a real session."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "lgbg.adapters.mcp.benchmark",
            "--game",
            "fixture",
            "--player",
            "0",
            "--seed",
            "1",
            "--players",
            "2",
            "--session-id",
            "g-0001",
            "--plugin",
            "tests.games.fixture_game",
            "--record-dir",
            str(tmp_path),
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )

    async def scenario() -> tuple[set[str], bool, str]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = {tool.name for tool in (await client.list_tools()).tools}
            taken = await client.call_tool("take", {})
            state = await client.read_resource(
                "fixture://sessions/g-0001/state?player=0"  # type: ignore[arg-type]
            )
            content = state.contents[0]
            assert isinstance(content, TextResourceContents)
            text = content.text
            assert taken.structuredContent is not None
            return tools, bool(taken.structuredContent["ok"]), text

    tools, accepted, projection = asyncio.run(asyncio.wait_for(scenario(), timeout=30))

    assert LIFECYCLE.isdisjoint(tools)
    assert "take" in tools
    assert accepted is True
    assert '"tokens":1' in projection


def test_the_sandbox_entry_point_over_stdio_creates_a_session(tmp_path: Path) -> None:
    """SC-14's transport half: the human-facing process can open a game and read it."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "lgbg.adapters.mcp.sandbox",
            "--game",
            "fixture",
            "--plugin",
            "tests.games.fixture_game",
            "--record-dir",
            str(tmp_path),
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )

    async def scenario() -> tuple[set[str], str, str]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = {tool.name for tool in (await client.list_tools()).tools}
            created = await client.call_tool("create_session", {"seed": 1, "players": 2})
            assert created.structuredContent is not None
            game_id = str(created.structuredContent["session_id"])
            state = await client.read_resource(
                f"fixture://sessions/{game_id}/state?player=0"  # type: ignore[arg-type]
            )
            content = state.contents[0]
            assert isinstance(content, TextResourceContents)
            text = content.text
            return tools, game_id, text

    tools, game_id, projection = asyncio.run(asyncio.wait_for(scenario(), timeout=30))

    assert tools >= LIFECYCLE
    assert game_id.startswith("g-")
    assert '"rounds":0' in projection
