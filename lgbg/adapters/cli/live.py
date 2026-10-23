"""play-live: a human at the MCP sandbox surface (PRD-v2 FR-14.4, SC-14).

The command starts the sandbox entry point over stdio, opens one session, and then reads actions
from standard input. Every read and every action goes through the MCP client; the CLI never
touches the facade or the engine directly. That is the point of the command: a person can check
that the published tools and resources are sufficient before a model is pointed at them.

The loop prints the projection when asked, prints the open decisions when the level exposes them,
and accepts one JSON action per line. `state`, `decisions` and `quit` are the only commands
beyond JSON. At L0 there is no decisions resource, so `--player` names the seat whose projection
is shown. A record is written by the server exactly as it would be for any other client.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from lgbg.adapters.cli.mcp_client import DECISIONS_RESOURCE, ClientError, GameClient
from lgbg.core.config import AssistLevel
from lgbg.core.log import god_log_path

ROOT = Path(__file__).resolve().parents[3]
"""The checkout, so the sandbox subprocess imports this tree even when the caller is elsewhere."""


def play_live(
    *,
    game: str,
    seed: int,
    players: int,
    protocol: str,
    session_id: str,
    out: Path,
    assist: AssistLevel,
    detail: str,
    plugins: Sequence[str],
    game_options: Mapping[str, Any],
    player: int = 0,
) -> int:
    """Run one interactive session to completion. Returns a process exit code."""
    return asyncio.run(
        _play_live(
            game=game,
            seed=seed,
            players=players,
            protocol=protocol,
            session_id=session_id,
            out=out,
            assist=assist,
            detail=detail,
            plugins=plugins,
            game_options=game_options,
            player=player,
        )
    )


async def _play_live(
    *,
    game: str,
    seed: int,
    players: int,
    protocol: str,
    session_id: str,
    out: Path,
    assist: AssistLevel,
    detail: str,
    plugins: Sequence[str],
    game_options: Mapping[str, Any],
    player: int,
) -> int:
    server_args = [
        "-m",
        "lgbg.adapters.mcp.sandbox",
        "--game",
        game,
        "--record-dir",
        str(out),
        "--assist",
        assist.value,
        "--detail",
        detail,
    ]
    for plugin in plugins:
        server_args.extend(["--plugin", plugin])
    params = StdioServerParameters(
        command=sys.executable,
        args=server_args,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )

    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        client = GameClient(session)
        await client.discover()
        game_id = await client.create_session(
            seed=seed,
            players=players,
            extra={
                "interaction_protocol": protocol,
                "game_config": dict(game_options),
                "session_id": session_id,
            },
        )
        print(f"game: {game} ({game_id})")
        print(f"record: {god_log_path(out, game_id)}")

        decisions = await _open_decisions(client, game_id)
        seat = int(decisions[0]["player"]) if decisions else player
        await _show_projection(client, game_id, seat)
        _print_decisions(decisions, exposed=client.has_resource(game_id, DECISIONS_RESOURCE))

        while decisions or assist is AssistLevel.L0:
            print("action> ", end="", flush=True)
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            command = line.strip()
            if not command:
                continue
            if command in {"quit", "exit"}:
                break
            if command in {"state", "s"}:
                await _show_projection(client, game_id, seat)
                continue
            if command in {"decisions", "d"}:
                _print_decisions(
                    decisions, exposed=client.has_resource(game_id, DECISIONS_RESOURCE)
                )
                continue
            try:
                payload = json.loads(command)
            except json.JSONDecodeError as error:
                print(f"error: not JSON: {error}", file=sys.stderr)
                continue
            if not isinstance(payload, Mapping):
                print("error: an action must be a JSON object", file=sys.stderr)
                continue
            try:
                acted_by = _player(payload, decisions, default=seat)
                action = str(payload["type"])
                params = payload.get("params", {})
                if not isinstance(params, Mapping):
                    raise ClientError("'params' must be an object")
                result = await client.submit(game_id, action=action, player=acted_by, params=params)
            except (ClientError, KeyError, TypeError, ValueError) as error:
                print(f"error: {error}", file=sys.stderr)
                continue
            _print_result(action, acted_by, result)
            decisions = await _open_decisions(client, game_id)
            if decisions:
                seat = int(decisions[0]["player"])

        _print_decisions(decisions, exposed=client.has_resource(game_id, DECISIONS_RESOURCE))
        await _end(client, game_id)
    return 0


async def _show_projection(client: GameClient, game_id: str, player: int) -> None:
    print(await client.read_projection(game_id, player=player))


def _print_decisions(decisions: Sequence[Mapping[str, Any]], *, exposed: bool = True) -> None:
    if not exposed:
        print("open decisions: not exposed at this assist level")
        return
    if not decisions:
        print("open decisions: none")
        return
    print(f"open decisions: {len(decisions)}")
    for decision in decisions:
        print(
            f"  {decision.get('request_id')}  player {decision.get('player')}  "
            f"{decision.get('kind')}  ({decision.get('phase')})"
        )


def _print_result(action: str, player: int, result: types.CallToolResult) -> None:
    payload = result.structuredContent
    if result.isError:
        text = " ".join(item.text for item in result.content if isinstance(item, types.TextContent))
        print(f"error: {text or 'the tool call failed'}", file=sys.stderr)
        return
    if isinstance(payload, Mapping) and payload.get("ok") is True:
        print(f"accepted {action} by seat {player}")
        return
    code = payload.get("error") if isinstance(payload, Mapping) else "UNKNOWN"
    message = payload.get("message") if isinstance(payload, Mapping) else ""
    print(f"rejected {code}: {message}", file=sys.stderr)


def _player(
    payload: Mapping[str, Any], decisions: Sequence[Mapping[str, Any]], *, default: int
) -> int:
    value = payload.get("player", decisions[0].get("player") if decisions else default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ClientError("an action must name a seat")
    return value


async def _open_decisions(client: GameClient, game_id: str) -> list[dict[str, Any]]:
    """The decisions resource, when the level advertises it; L0 has none (PRD-v2 FR-4.1)."""
    if not client.has_resource(game_id, DECISIONS_RESOURCE):
        return []
    return await client.decisions(game_id)


async def _end(client: GameClient, game_id: str) -> None:
    with contextlib.suppress(ClientError):
        await client.end_session(game_id)
