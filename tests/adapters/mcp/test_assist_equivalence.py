"""Assist equivalence through the real MCP transport (PRD-v2 FR-4.5, FR-7.4, SC-3).

v1 proved that the same script at L0, L1 and L2 produces one record when the engine is driven
directly. This module proves it again through the surface, because the surface is exactly where a
level can leak: the resources, the refusal rendering and the transport are all new, and none of
them existed when v1's equivalence test was written.

The script is one committed file, played three times through three real stdio processes. The god
logs are compared byte for byte after the two fields the level determines - `assist`, and the
rejection-detail tier it defaults to - are blanked out of the header. Nothing else may move.

The second test follows the redo turn, the channel FR-7.4 calls out. A wrong-seat attempt is
refused at every level, but only L2 may show the alternatives: L0 gets a category, L1 gets the
sentence and the facts, L2 gets the list. The record keeps the full detail at all three levels,
which is what makes the levels comparable.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

import tests.games.fixture_game  # noqa: F401 - registers the fixture game for verification
from lgbg.adapters.cli.mcp_client import GameClient
from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import AssistLevel
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from tests.adapters.mcp.support import REPO

FIXTURE: Final[Path] = (
    Path(__file__).resolve().parents[2] / "fixtures" / "v2" / "assist_script.json"
)
LEVELS: Final[tuple[AssistLevel, ...]] = (AssistLevel.L0, AssistLevel.L1, AssistLevel.L2)
SESSION_ID: Final[str] = "g-assist"
WRONG_SEAT: Final[int] = 1
"""The script's second attempt is seat 1 acting while seat 0 is to act: the redo-turn probe."""


@dataclass(frozen=True, slots=True)
class Played:
    """One level's run: what the surface answered, and the record it wrote."""

    level: AssistLevel
    answers: tuple[Mapping[str, Any], ...]
    path: Path


def _params(directory: Path, level: AssistLevel) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "lgbg.adapters.mcp.sandbox",
            "--game",
            "fixture",
            "--plugin",
            "tests.games.fixture_game",
            "--assist",
            level.value,
            "--record-dir",
            str(directory),
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )


async def _scenario(directory: Path, level: AssistLevel, script: Mapping[str, Any]) -> Played:
    async with (
        stdio_client(_params(directory, level)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        client = GameClient(session)
        await client.discover()
        game_id = await client.create_session(
            seed=int(script["seed"]),
            players=int(script["players"]),
            extra={
                "interaction_protocol": str(script["interaction_protocol"]),
                "session_id": SESSION_ID,
            },
        )
        answers: list[Mapping[str, Any]] = []
        for index, entry in enumerate(script["actions"]):
            result = await client.submit(
                game_id,
                action=str(entry["type"]),
                player=int(entry["player"]),
                params=entry.get("params", {}),
            )
            assert not result.isError, f"attempt {index} did not reach the engine: {result}"
            payload = result.structuredContent
            assert payload is not None, f"attempt {index} returned no structured answer"
            answers.append(payload)
        await client.end_session(game_id)
    return Played(level=level, answers=tuple(answers), path=god_log_path(directory, SESSION_ID))


def _play(directory: Path, level: AssistLevel, script: Mapping[str, Any]) -> Played:
    return asyncio.run(asyncio.wait_for(_scenario(directory, level, script), timeout=120))


@pytest.fixture(scope="module")
def played(tmp_path_factory: pytest.TempPathFactory) -> dict[AssistLevel, Played]:
    """The one script, played once at each level through its own stdio process."""
    base = tmp_path_factory.mktemp("assist-equivalence")
    script: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {level: _play(base / level.value, level, script) for level in LEVELS}


def _without_the_level(record: bytes) -> list[bytes]:
    """The record with the two fields the level determines blanked out of its header.

    'assist' is the level; 'rejection_detail' is the tier it defaults to, and the two are
    separate run-config fields on purpose (FR-5.3). Both are what an operator chose, not what
    the game did, so both are normalised here - and the test then asserts that they are the
    only two that moved.
    """
    lines = record.splitlines()
    header = json.loads(lines[0])
    config = dict(header["config"])
    config["assist"] = "?"
    config["rejection_detail"] = "?"
    header["config"] = config
    return [to_canonical_json(header).encode(), *lines[1:]]


def test_the_same_script_at_three_levels_produces_one_record(
    played: dict[AssistLevel, Played],
) -> None:
    """SC-3: 21 attempts, three levels, one set of bytes below the header."""
    reference = _without_the_level(played[AssistLevel.L0].path.read_bytes())
    for level in LEVELS:
        assert _without_the_level(played[level].path.read_bytes()) == reference, (
            f"the {level.value} record differs below its header"
        )

    headers = {
        level: json.loads(played[level].path.read_bytes().splitlines()[0]) for level in LEVELS
    }
    moved = {
        key
        for key in headers[AssistLevel.L0]["config"]
        if headers[AssistLevel.L0]["config"][key] != headers[AssistLevel.L2]["config"][key]
    }
    assert moved == {"assist", "rejection_detail"}, (
        "nothing else in the header moved with the level"
    )

    log = GameLogReader(played[AssistLevel.L0].path).read()
    game = get_game("fixture")
    assert log.terminal is not None, "the script plays to a verdict"
    assert len(log.actions) == 21
    assert sum(1 for record in log.actions if record.result.get("ok") is False) == 2
    assert verify(log, game).actions == 21
    assert len(replay(log, game).states) == len(log.actions) + 1


def test_the_redo_turn_reveals_no_more_at_l0_than_it_does_at_l2(
    played: dict[AssistLevel, Played],
) -> None:
    """FR-7.4: the redo is a leak channel, and only the full tier may show alternatives."""
    minimal = played[AssistLevel.L0].answers[WRONG_SEAT]
    standard = played[AssistLevel.L1].answers[WRONG_SEAT]
    full = played[AssistLevel.L2].answers[WRONG_SEAT]

    assert minimal == {"ok": False, "error": "NOT_YOUR_DECISION"}
    assert standard["ok"] is False
    assert standard["error"] == "NOT_YOUR_DECISION"
    assert "message" in standard, "the standard tier keeps the sentence the rule wrote"
    assert "details" not in standard, "the list is an enumeration, whatever tier is asked for"
    assert full["details"] == {"open_players": [0]}
    assert set(minimal) < set(full), "L2 is a superset, not a different answer"

    for level in LEVELS:
        recorded = GameLogReader(played[level].path).read().actions[WRONG_SEAT]
        assert recorded.result["details"] == {"open_players": [0]}, (
            f"{level.value} lost the detail from the record; only the surface may filter it"
        )
