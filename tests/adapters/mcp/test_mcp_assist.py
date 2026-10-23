"""The assist level gates what the MCP surface shows (PRD-v2 FR-4.1 to FR-4.4).

The level belongs to the process the operator launched. L0 ships the projection and a
category-only refusal; L1 adds the decision surface as action types, costs and parameter domains;
L2 adds the enumeration and the full refusal. The tool list is constant across levels
(PRD-v2 FR-3.3), which is why these tests read resources and rejections rather than tools.

The refusal test uses a real Catan rule refusal whose details carry a list of adjacent vertices.
The minimal tier is asserted as a whole object rather than by absence of one key, so a new detail
that leaked at L0 would fail even if it were not called `touches`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextResourceContents

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.mcp.sandbox import sandbox_surface
from lgbg.adapters.mcp.server import McpSurface
from lgbg.core.config import AssistLevel
from tests.adapters.mcp.support import bound_surface, listed_resources, listed_tools, run
from tests.games.fixture_game import FixtureGame  # noqa: F401


async def read(surface: McpSurface, uri: str) -> str:
    async with create_connected_server_and_client_session(surface.server) as client:
        result = await client.read_resource(uri)  # type: ignore[arg-type]
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    return content.text


async def call(surface: McpSurface, name: str, arguments: dict[str, Any]) -> CallToolResult:
    async with create_connected_server_and_client_session(surface.server) as client:
        return await client.call_tool(name, arguments)


def advertised(surface: McpSurface) -> list[str]:
    return [str(resource.uri) for resource in run(listed_resources(surface))]


def refused(surface: McpSurface, uri: str) -> None:
    """The handler's answer to a read the level does not serve.

    Called directly rather than through the in-memory client: the client wraps a server-side
    `McpError` in the task group that runs the server, so the assertion would be about anyio's
    exception shape rather than about the refusal.
    """
    with pytest.raises(McpError):
        run(surface._read_resource(uri))


def test_l0_advertises_the_projection_and_nothing_else(tmp_path: Path) -> None:
    """PRD-v2 FR-4.1: at the hardest level the agent surface is the observation, full stop."""
    surface, _, game_id = bound_surface(tmp_path / "run", assist=AssistLevel.L0)

    uris = advertised(surface)

    assert uris, "control: a live session still exposes its projection"
    assert all("/state" in uri for uri in uris), uris
    assert not any("/decisions" in uri or "/surface" in uri for uri in uris)
    refused(surface, f"fixture://sessions/{game_id}/decisions")
    refused(surface, f"fixture://sessions/{game_id}/surface?player=0")


def test_l1_adds_the_decision_surface_as_domains_not_a_cross_product(tmp_path: Path) -> None:
    """PRD-v2 FR-4.2: types, costs and permitted values - never every combination of them."""
    surface, facade, game_id = bound_surface(
        tmp_path / "run", game="catan", players=4, assist=AssistLevel.L1
    )

    uris = advertised(surface)
    text = run(read(surface, f"catan://sessions/{game_id}/surface?player=0"))

    assert any("/surface?player=0" in uri for uri in uris), uris
    assert text == facade.decision_surface(game_id, 0), "one renderer, not a second one"
    assert "place_settlement" in text
    assert "vertex=one of" in text
    assert "\n  place_settlement vertex=0" not in text


def test_l2_adds_the_enumerated_legal_actions(tmp_path: Path) -> None:
    """PRD-v2 FR-4.3: the same resource now carries every action, one to a line."""
    at_l1, _, l1_id = bound_surface(tmp_path / "l1", game="catan", players=4, assist=AssistLevel.L1)
    at_l2, _, l2_id = bound_surface(tmp_path / "l2", game="catan", players=4, assist=AssistLevel.L2)

    quiet = run(read(at_l1, f"catan://sessions/{l1_id}/surface?player=0"))
    loud = run(read(at_l2, f"catan://sessions/{l2_id}/surface?player=0"))
    enumerated = [
        line for line in loud.splitlines() if line.startswith("  place_settlement vertex=")
    ]

    assert "vertex=one of" not in loud
    assert len(enumerated) > 1
    assert len(enumerated) > quiet.count("place_settlement")
    assert all(line.rsplit("=", 1)[-1].isdigit() for line in enumerated)


@pytest.mark.parametrize(
    ("assist", "expected_keys"),
    [
        (AssistLevel.L0, {"ok", "error"}),
        (AssistLevel.L1, {"ok", "error", "message", "details"}),
        (AssistLevel.L2, {"ok", "error", "message", "details"}),
    ],
)
def test_a_refusal_explains_itself_at_the_level_the_run_chose(
    tmp_path: Path, assist: AssistLevel, expected_keys: set[str]
) -> None:
    """PRD-v2 FR-4.1 and PRD-v2 FR-4.3: L0 is a category, L1 the facts, L2 the alternatives too.

    A setup settlement at vertex 0 followed by a road at edge 2 is a real rule refusal: edge 2
    does not touch vertex 0, and the refusal records the vertices it does touch. Those are the
    alternatives a minimal tier must not reveal.
    """
    surface, _, _ = bound_surface(tmp_path / "run", game="catan", players=4, assist=assist)
    opening = run(call(surface, "place_settlement", {"vertex": 0}))
    assert opening.structuredContent is not None
    assert opening.structuredContent["ok"] is True

    result = run(call(surface, "place_road", {"edge": 2}))

    assert result.isError is False
    assert result.structuredContent is not None
    payload = result.structuredContent
    assert payload["ok"] is False
    assert payload["error"] == "NOT_CONNECTED"
    assert set(payload) == expected_keys
    if assist is AssistLevel.L0:
        assert "touches" not in str(payload)
    elif assist is AssistLevel.L1:
        assert payload["details"] == {"edge": 2, "must_touch": 0}
    else:
        details = payload["details"]
        assert details["touches"] == [1, 7]
        assert details["edge"] == 2


def test_the_operator_sets_the_level_and_a_request_cannot(tmp_path: Path) -> None:
    """PRD-v2 FR-4.4: neither an argument nor a resource read may move the level."""
    surface = sandbox_surface("fixture", assist=AssistLevel.L0, directory=tmp_path / "run")
    tools = run(listed_tools(surface))
    assert all("assist" not in json.dumps(tool.inputSchema) for tool in tools)

    async def scenario() -> tuple[bool, list[str], str, dict[str, Any]]:
        async with create_connected_server_and_client_session(surface.server) as client:
            promoted = await client.call_tool(
                "create_session", {"seed": 1, "players": 2, "assist": "L2"}
            )
            created = await client.call_tool("create_session", {"seed": 1, "players": 2})
            assert created.structuredContent is not None
            game_id = str(created.structuredContent["session_id"])
            uris = [str(resource.uri) for resource in (await client.list_resources()).resources]
            state = await client.read_resource(
                f"fixture://sessions/{game_id}/state?player=0"  # type: ignore[arg-type]
            )
            content = state.contents[0]
            assert isinstance(content, TextResourceContents)
            refused = await client.call_tool("spend", {"session_id": game_id, "player": 0})
            assert refused.structuredContent is not None
            return promoted.isError, uris, content.text, dict(refused.structuredContent)

    rejected_request, uris, projection, refusal = run(scenario())

    assert rejected_request is True, "the session schema has no assist field to send"
    assert uris, "control: the session was created"
    assert all("/state" in uri for uri in uris), uris
    assert "assist" not in projection
    assert set(refusal) == {"ok", "error"}, "the refusal is still the minimal L0 tier"


def test_a_benchmark_surface_reads_only_its_own_seat_s_decision_surface(tmp_path: Path) -> None:
    """The surface is bound to one seat: another seat's decision is not its to read."""
    surface, facade, game_id = bound_surface(tmp_path / "run", assist=AssistLevel.L1)

    implicit = run(read(surface, f"fixture://sessions/{game_id}/surface"))
    explicit = run(read(surface, f"fixture://sessions/{game_id}/surface?player=0"))

    assert implicit == explicit == facade.decision_surface(game_id, 0)
    refused(surface, f"fixture://sessions/{game_id}/surface?player=1")
