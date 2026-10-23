"""A complete four-player game driven through the MCP surface (PRD-v2 FR-1.4, SC-14).

The scripted path is deliberately the same fixture v1 used: it asks the server for the same
session, sends the same actions through the generated tools, and compares the resulting god log
byte for byte with the committed one. If the MCP layer had changed a decision, a hash or a
recording, this would fail before a model was ever involved.

The replay asserts every intermediate state, not only the final hash: a record that reaches the
right verdict while taking a different path is still a different game.
"""

from __future__ import annotations

import asyncio
import json
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
from lgbg.core.replay import replay, verify
from tests.adapters.mcp.support import REPO

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "catan" / "full_game.json"
GOLDEN = Path(__file__).resolve().parents[2] / "golden" / "catan" / "full_game.god.jsonl"
SESSION_ID = "g-0003"


def test_a_scripted_client_plays_the_full_game_over_stdio(tmp_path: Path) -> None:
    """PRD-v2 FR-1.4: the MCP path produces the v1 record byte for byte, and every state replays."""
    script: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actions: list[dict[str, Any]] = script["actions"]
    config: dict[str, Any] = script["config"]
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

    async def scenario() -> int:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            client = GameClient(session)
            await client.discover()
            game_id = await client.create_session(
                seed=int(config["seed"]),
                players=int(config["players"]),
                extra={
                    "interaction_protocol": str(config["interaction_protocol"]),
                    "game_config": {"board": str(config["board"])},
                    "session_id": SESSION_ID,
                },
            )
            accepted = 0
            for index, entry in enumerate(actions):
                result = await client.submit(
                    game_id,
                    action=str(entry["type"]),
                    player=int(entry["player"]),
                    params=entry.get("params", {}),
                )
                payload = result.structuredContent
                assert not result.isError, f"action {index} did not reach the engine: {payload}"
                assert payload is not None
                assert payload["ok"] is True, f"action {index} was rejected: {payload}"
                accepted += 1
            await client.end_session(game_id)
            return accepted

    accepted = asyncio.run(asyncio.wait_for(scenario(), timeout=120))

    record = god_log_path(tmp_path, SESSION_ID)
    assert accepted == len(actions)
    assert record.read_bytes() == GOLDEN.read_bytes()
    log = GameLogReader(record).read()
    game = get_game("catan")
    report = verify(log, game)
    replayed = replay(log, game)
    assert report.actions == len(actions)
    assert report.rejections == 0
    assert len(replayed.states) == len(actions) + 1, "every intermediate state is present"
    assert log.terminal is not None, "the final action ends the game"
