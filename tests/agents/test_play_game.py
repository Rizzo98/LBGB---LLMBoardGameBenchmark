"""One model plays a complete game, and the run directory is enough to read it back (SC-1, SC-4).

The game is Catan's committed 743-action fixture. Seat 0 is a model seat driven through the loop by
the mock provider; the other three seats are scripted and submit their recorded actions directly.
The test asserts that the god log still verifies and replays like a v1 record, that every model
decision is in the sidecar, and that the exact messages for a decision can be read from a
copy of the run directory with nothing else.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.agents.game import ModelSeat, ScriptedSeat, play_game
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import (
    Completion,
    CompletionConfig,
    Message,
    ToolCall,
    ToolSpec,
)
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.agents.sidecar import messages_from_run
from lgbg.core.config import RunConfig
from lgbg.core.contracts import validate_manifest
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from lgbg.core.types import Action

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "catan" / "full_game.json"
RUN_ID = "r-k022"
MODEL = "mock-model"
AT = "2026-02-11T09:30:00+00:00"


class RecordingMock(MockProvider):
    """A mock that remembers the exact messages each call was sent."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.seen: list[tuple[Message, ...]] = []

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        self.seen.append(tuple(messages))
        return await super().complete(messages, tools, config)


def fixture() -> dict[str, Any]:
    loaded: Any = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def actions_for(data: dict[str, Any], player: int) -> list[dict[str, Any]]:
    return [entry for entry in data["actions"] if int(entry["player"]) == player]


def test_one_model_plays_a_complete_game_and_the_directory_reconstructs_it(
    tmp_path: Path,
) -> None:
    data = fixture()
    config = RunConfig.from_mapping(data["config"], game_option_keys={"board"})
    seat_zero = actions_for(data, 0)
    provider = RecordingMock(
        Behaviour.CORRECT_PLAY,
        actions=[
            ToolCall(
                id=f"model-{index}",
                name=str(entry["type"]),
                arguments=dict(entry["params"]),
            )
            for index, entry in enumerate(seat_zero)
        ],
    )
    seats: dict[int, ModelSeat | ScriptedSeat] = {
        0: ModelSeat(
            provider=provider,
            model=MODEL,
            provider_id="mock",
            provider_version="1",
        ),
        **{
            player: ScriptedSeat(
                actions=[
                    Action(
                        player=player,
                        type=str(entry["type"]),
                        params=dict(entry["params"]),
                    )
                    for entry in actions_for(data, player)
                ]
            )
            for player in (1, 2, 3)
        },
    }
    price_table = PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
    )
    directory = tmp_path / "runs" / RUN_ID

    result = asyncio.run(
        play_game(
            game="catan",
            config=config,
            directory=directory,
            run_id=RUN_ID,
            seats=seats,
            prompts=PromptSet.load("catan"),
            price_table=price_table,
            clock=lambda: AT,
        )
    )

    assert result.completed is True
    assert result.actions == 743, "the whole fixture was played"
    assert result.decisions == len(seat_zero), "one sidecar record per model decision"

    manifest: dict[str, Any] = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert validate_manifest(manifest) == []
    assert [seat["agent"] for seat in manifest["seats"]] == [
        "llm",
        "scripted",
        "scripted",
        "scripted",
    ]
    assert manifest["providers"] == [{"id": "mock", "version": "1"}]
    assert set(manifest["prompts"]) == {"game", "system", "policy", "redo"}

    god = GameLogReader(god_log_path(directory, result.game_id)).read()
    report = verify(god, get_game("catan"))
    assert report.actions == 743
    assert report.rejections == 0
    replayed = replay(god, get_game("catan"))
    assert len(replayed.states) == 744
    assert replayed.terminal_hash == report.terminal_hash

    records = [
        json.loads(line)
        for line in result.sidecar_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    decisions = [record for record in records if record["t"] == "decision"]
    assert len(decisions) == len(seat_zero)
    assert any(record["t"] == "game" for record in records), "the v1 game record is still written"
    records = decisions
    assert all(record["model"] == MODEL for record in records)
    assert all(record["provider"] == "mock" for record in records)
    assert all(record["attempt"] == 1 for record in records)
    assert all(record["messages"] for record in records)
    assert all(record["usage"] is not None for record in records)
    assert len({record["request_id"] for record in records}) == len(records)

    action_records = {record.seq: record for record in god.actions}
    for record in records:
        engine = action_records[record["seq"]]
        assert engine.player == record["player"]
        assert engine.action.type == record["outcome"]["action"]["type"]
        assert engine.action.params == record["outcome"]["action"]["params"]

    copy = tmp_path / "copy"
    shutil.copytree(directory, copy)
    for index, record in enumerate(records):
        reconstructed = messages_from_run(copy, result.game_id, record["request_id"])
        expected = [message.to_mapping() for message in provider.seen[index]]
        assert reconstructed == expected
