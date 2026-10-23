"""A client that knows nothing about the game it is playing (PRD-v2 SC-6, FR-3.2).

The client is deliberately not given the game name wherever it can avoid it: it asks the server
what tools exist, asks the resources what is happening, and turns the first open decision into a
tool call. Every action name and every parameter value in this test comes from the server, not
from a table in the client.

The sandbox profile is the only profile that can create a session, which is exactly what a human
or a client needs before it starts asking the game questions.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.cli.mcp_client import GameClient
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify
from tests.adapters.mcp.support import REPO

CLIENT_SOURCE = REPO / "lgbg" / "adapters" / "cli" / "mcp_client.py"


def test_a_client_can_open_catan_and_place_its_first_piece(tmp_path: Path) -> None:
    """SC-6: tools/list and the resources are enough to reach one legal opening placement."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "lgbg.adapters.mcp.sandbox",
            "--game",
            "catan",
            "--record-dir",
            str(tmp_path),
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )

    async def scenario() -> tuple[str, str, dict[str, Any], bool]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            client = GameClient(session)
            await client.discover()

            game_id = await client.create_session(seed=1, players=4)
            projection = await client.read_projection(game_id, player=0)
            decision = await client.next_decision(game_id)
            assert decision is not None, "the opening decision must be a resource"
            result = await client.act(game_id, decision)
            assert result.structuredContent is not None
            return game_id, projection, dict(decision), bool(result.structuredContent["ok"])

    game_id, projection, decision, accepted = asyncio.run(asyncio.wait_for(scenario(), timeout=30))

    assert accepted is True
    assert "catan" in projection, "the projection is the game's own rendering"
    log = GameLogReader(god_log_path(tmp_path, game_id)).read()
    assert len(log.actions) == 1, "one decision, one tool call, one action"
    assert log.actions[0].action.type == decision["schema_ref"]
    assert log.actions[0].result["ok"] is True
    assert verify(log, get_game("catan")).actions == 1


def test_the_client_contains_no_game_specific_code() -> None:
    """SC-6: if the client names a piece, a move, or a game, the surface has not delivered."""
    source = CLIENT_SOURCE.read_text(encoding="utf-8").lower()
    forbidden = ("catan", "settlement", "vertex", "road", "robber", "dev_card", "decision_surface")

    assert CLIENT_SOURCE.exists(), "control: the client must have a source to scan"
    assert [word for word in forbidden if word in source] == []
    assert [action for action in get_game("catan").action_schema() if action in source] == []
