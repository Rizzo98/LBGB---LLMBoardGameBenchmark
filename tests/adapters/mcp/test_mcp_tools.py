"""Tools are the game's declaration, served (PRD-v2 FR-3.1, PRD-v2 FR-3.2, SC-6).

The claim under test is the plugin system's: adding a game adds no transport code. These tests
therefore never name an action of their own; they ask the game what it declares and then check
that the served surface is that answer, exactly, once.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextResourceContents

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.mcp.sandbox import sandbox_surface
from lgbg.adapters.mcp.server import McpSurface
from lgbg.core.config import AssistLevel
from lgbg.core.game import get_game
from lgbg.core.tools import tool_definitions
from tests.adapters.mcp.support import bound_surface, listed_tools, run
from tests.games.fixture_game import TOKENS_UNAVAILABLE, FixtureGame  # noqa: F401

MCP_SOURCES = Path(__file__).resolve().parents[3] / "lgbg" / "adapters" / "mcp"


async def call(surface: McpSurface, name: str, arguments: dict[str, object]) -> CallToolResult:
    async with create_connected_server_and_client_session(surface.server) as client:
        return await client.call_tool(name, arguments)


async def read(surface: McpSurface, uri: str) -> str:
    async with create_connected_server_and_client_session(surface.server) as client:
        result = await client.read_resource(uri)  # type: ignore[arg-type]
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    return content.text


def test_the_served_tools_are_the_v1_generator_s_answer(tmp_path: Path) -> None:
    """PRD-v2 FR-3.2: one definition per declared action type, with the plugin's own schema."""
    surface, _, _ = bound_surface(tmp_path / "run")
    game = get_game("fixture")
    declared = game.action_schema()
    expected = {
        str(definition["name"]): (definition["description"], definition["inputSchema"])
        for definition in tool_definitions(game)
    }

    tools = run(listed_tools(surface))

    assert [tool.name for tool in tools] == sorted(declared)
    assert {tool.name: (tool.description, tool.inputSchema) for tool in tools} == expected


def test_every_declared_action_appears_exactly_once(tmp_path: Path) -> None:
    """A duplicated tool would be two names for one intent, and a client would have to guess."""
    surface, _, _ = bound_surface(tmp_path / "run")

    names = [tool.name for tool in run(listed_tools(surface))]

    assert names == sorted(set(names))
    assert set(names) == set(get_game("fixture").action_schema())


def test_the_action_tool_call_reaches_the_facade_and_returns_acceptance(tmp_path: Path) -> None:
    """PRD-v2 FR-3.1: the tool is a transport; the facade is the authority that moves the game."""
    surface, facade, game_id = bound_surface(tmp_path / "run")

    result = run(call(surface, "take", {}))

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["ok"] is True
    assert facade.projection(game_id, 0)["tokens"] == 1


def test_the_action_tool_call_returns_a_rejection_as_the_engine_s_answer(tmp_path: Path) -> None:
    """FR-1.6: a refusal is an answer, not an exception and not a dropped call."""
    surface, facade, game_id = bound_surface(tmp_path / "run")
    before = facade.projection(game_id, 0)

    result = run(call(surface, "spend", {}))

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["ok"] is False
    assert result.structuredContent["error"] == TOKENS_UNAVAILABLE.code
    assert facade.projection(game_id, 0) == before
    assert facade.pending_decisions(game_id)[0].player == 0


def test_a_catan_surface_carries_the_plugin_s_own_schema_including_its_union(
    tmp_path: Path,
) -> None:
    """PRD-v2 FR-3.2, SC-6: the awkward schema is the one that proves nothing was hand-written."""
    surface, _, _ = bound_surface(tmp_path / "run", game="catan", players=4)

    tools = {tool.name: tool.inputSchema for tool in run(listed_tools(surface))}
    declared = get_game("catan").action_schema()

    assert set(tools) == set(declared)
    assert tools["play_dev_card"] == declared["play_dev_card"]
    assert "oneOf" in tools["play_dev_card"]


def test_the_mcp_adapter_names_no_game_or_mechanic() -> None:
    """SC-6: if the adapter knew a mechanic, a second game would need a second adapter."""
    sources = sorted(MCP_SOURCES.glob("*.py"))
    forbidden = ("catan", "settlement", "vertex", "road", "robber", "dev_card")

    assert sources, "control: the MCP adapter must have sources to scan"
    offenders = [
        f"{path.name}: {word}"
        for path in sources
        for word in forbidden
        if word in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == [], "the MCP adapter must be game-agnostic: " + str(offenders)


@pytest.mark.parametrize("profile", ["benchmark", "sandbox"])
def test_tools_list_is_identical_at_all_three_assist_levels(tmp_path: Path, profile: str) -> None:
    """PRD-v2 FR-3.3: the action vocabulary is not an assist channel.

    The benchmark and sandbox profiles are both checked. The sandbox is the one that could
    plausibly have grown a level-dependent lifecycle schema, and a benchmark surface missing a
    tool at L0 would turn the vocabulary itself into a hint.
    """
    surfaces: list[McpSurface] = []
    for level in AssistLevel:
        if profile == "benchmark":
            surface, _, _ = bound_surface(tmp_path / level.value, assist=level)
        else:
            surface = sandbox_surface("fixture", assist=level)
        surfaces.append(surface)

    served = [run(_served(surface)) for surface in surfaces]

    assert served[0], "control: the surface serves its declared actions"
    assert served[1] == served[0]
    assert served[2] == served[0]


def test_the_projection_and_pending_decisions_do_not_move_with_the_level(
    tmp_path: Path,
) -> None:
    """PRD-v2 FR-3.3: the level adds around a read; it does not change the read itself.

    The projection is identical at all three levels, and the pending decisions are identical at
    the two levels that expose them. What does move - the decision surface and the refusal - is
    the subject of `test_mcp_assist.py`.
    """
    projections: list[str] = []
    decisions: list[str] = []
    for level in AssistLevel:
        surface, _, game_id = bound_surface(tmp_path / level.value, assist=level)
        projections.append(run(read(surface, f"fixture://sessions/{game_id}/state?player=0")))
        if level is not AssistLevel.L0:
            decisions.append(run(read(surface, f"fixture://sessions/{game_id}/decisions")))

    assert len(set(projections)) == 1, "the projection must not move with the level"
    assert len(decisions) == 2, "control: L1 and L2 expose the pending decisions"
    assert decisions[0] == decisions[1], "the pending decisions must not move with the level"


def test_the_sandbox_action_schemas_keep_the_plugin_s_union_intact() -> None:
    """The sandbox envelope is added to each branch, not laid over a closed union."""
    surface = sandbox_surface("catan")
    tools = {tool.name: tool.inputSchema for tool in run(listed_tools(surface))}
    unions = tools["play_dev_card"]["oneOf"]
    assert isinstance(unions, list)
    assert unions

    for branch in unions:
        assert "session_id" in branch["properties"]
        assert "player" in branch["properties"]
        assert "session_id" in branch["required"]
        assert "player" in branch["required"]


def test_a_sandbox_action_acts_on_the_session_and_seat_it_names(tmp_path: Path) -> None:
    """The lifecycle surface acts on the session the client names, and nowhere else."""
    from lgbg.adapters.mcp.sandbox import sandbox_surface

    surface = sandbox_surface("fixture", directory=tmp_path / "run")

    async def scenario() -> tuple[str, bool]:
        async with create_connected_server_and_client_session(surface.server) as client:
            created = await client.call_tool("create_session", {"seed": 1, "players": 2})
            assert created.structuredContent is not None
            game_id = str(created.structuredContent["session_id"])
            taken = await client.call_tool("take", {"session_id": game_id, "player": 0})
            assert taken.structuredContent is not None
            return game_id, bool(taken.structuredContent["ok"])

    game_id, accepted = run(scenario())

    assert game_id.startswith("g-")
    assert accepted is True


async def _served(
    surface: McpSurface,
) -> list[tuple[str, str | None, dict[str, object]]]:
    return [
        (tool.name, tool.description, dict(tool.inputSchema))
        for tool in await listed_tools(surface)
    ]
