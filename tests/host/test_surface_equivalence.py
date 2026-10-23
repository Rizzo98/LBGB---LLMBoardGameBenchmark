"""Three surfaces, one hash (PRD-v2 FR-1.4, PRD-v2 FR-2.1, SC-2).

The facade is the only authority, so the same actions must produce the same record whether they
arrive through the MCP server, through the HTTP host, or in-process. This test is the one that
keeps the transports from drifting into three subtly different games: it plays one committed
script with two refusals and a terminal verdict on each surface and compares the god logs byte for
byte.

The HTTP surface is driven through its ASGI interface directly and the MCP surface through the
official SDK's in-memory transport; neither needs a port or a network (NFR-8).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Final

from mcp.shared.memory import create_connected_server_and_client_session

import tests.games.fixture_game  # noqa: F401 - registers the fixture game
from lgbg.adapters.cli.mcp_client import GameClient
from lgbg.adapters.mcp.server import Profile, build_server
from lgbg.core.config import AssistLevel, RunConfig
from lgbg.core.game import Rejected, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from lgbg.core.types import Action
from lgbg.host.facade import SessionFacade
from lgbg.host.http import HttpHost
from tests.host.support import call

FIXTURE: Final[Path] = (
    Path(__file__).resolve().parents[1] / "fixtures" / "v2" / "assist_script.json"
)
SESSION: Final[str] = "g-equiv"
REJECTED: Final[frozenset[int]] = frozenset({0, 1})
"""The two attempts the script deliberately gets wrong, so the refusal path is on every surface."""


def _script() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return raw, list(raw["actions"])


def _config() -> RunConfig:
    return RunConfig(
        seed=7,
        players=2,
        assist=AssistLevel.L1,
        interaction_protocol="decline_only",
    )


def _in_process(directory: Path, actions: list[dict[str, Any]]) -> None:
    facade = SessionFacade()
    game_id = facade.create_session("fixture", _config(), game_id=SESSION, directory=directory)
    for index, entry in enumerate(actions):
        result = facade.submit_action(
            game_id,
            Action(player=int(entry["player"]), type=str(entry["type"]), params={}),
        )
        assert isinstance(result, Rejected) is (index in REJECTED), f"attempt {index} disagreed"


def _http(directory: Path, actions: list[dict[str, Any]]) -> None:
    app = HttpHost(directory=directory)
    created = call(
        app,
        "POST",
        "/sessions",
        json_body={
            "game": "fixture",
            "seed": 7,
            "players": 2,
            "assist": "L1",
            "interaction_protocol": "decline_only",
            "session_id": SESSION,
        },
    )
    assert created.status == 201
    for index, entry in enumerate(actions):
        answer = call(
            app,
            "POST",
            f"/sessions/{SESSION}/actions",
            json_body={
                "player": int(entry["player"]),
                "type": str(entry["type"]),
                "params": {},
            },
        )
        assert answer.status == 200, f"attempt {index}: {answer}"
        assert answer.body["result"]["ok"] is (index not in REJECTED), f"attempt {index}"
    assert call(app, "DELETE", f"/sessions/{SESSION}").status == 200


async def _mcp_scenario(directory: Path, actions: list[dict[str, Any]]) -> None:
    surface = build_server(
        SessionFacade(),
        "fixture",
        profile=Profile.SANDBOX,
        assist=AssistLevel.L1,
        directory=directory,
    )
    async with create_connected_server_and_client_session(surface.server) as session:
        client = GameClient(session)
        await client.discover()
        game_id = await client.create_session(
            seed=7,
            players=2,
            extra={"interaction_protocol": "decline_only", "session_id": SESSION},
        )
        for index, entry in enumerate(actions):
            result = await client.submit(
                game_id,
                action=str(entry["type"]),
                player=int(entry["player"]),
                params={},
            )
            assert not result.isError, f"attempt {index}: {result}"
            payload = result.structuredContent
            assert payload is not None
            assert payload["ok"] is (index not in REJECTED), f"attempt {index}: {payload}"
        await client.end_session(game_id)


def test_one_script_through_mcp_http_and_in_process_is_one_record(tmp_path: Path) -> None:
    """SC-2: the assertion is the bytes, and then the replay of the bytes."""
    _, actions = _script()
    directories = {
        "in-process": tmp_path / "in-process",
        "http": tmp_path / "http",
        "mcp": tmp_path / "mcp",
    }

    _in_process(directories["in-process"], actions)
    _http(directories["http"], actions)
    asyncio.run(asyncio.wait_for(_mcp_scenario(directories["mcp"], actions), timeout=60))

    records = {
        surface: god_log_path(directory, SESSION).read_bytes()
        for surface, directory in directories.items()
    }
    assert records["http"] == records["in-process"], "HTTP moved the game"
    assert records["mcp"] == records["in-process"], "MCP moved the game"

    game = get_game("fixture")
    for surface, directory in directories.items():
        log = GameLogReader(god_log_path(directory, SESSION)).read()
        report = verify(log, game)
        assert log.terminal is not None, f"{surface} did not finish"
        assert report.actions == len(actions)
        assert report.rejections == len(REJECTED)
        assert len(replay(log, game).states) == len(actions) + 1
