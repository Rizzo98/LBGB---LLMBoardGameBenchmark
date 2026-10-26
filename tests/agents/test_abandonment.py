"""Exhaustion abandons the game, and an abandoned game is not a loss (PRD-v2 FR-7.5, FR-11.6).

A model that cannot produce a legal action inside its redo budget has failed in a way a forfeit
would hide. The game stops where it is: the god log gets no terminal record, the sidecar gets an
abandonment record naming the decision, the final refusal, the seat and the model, and the result is
reported as incomplete rather than as a game that was lost.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.adapters.cli.main import main
from lgbg.agents.game import ModelSeat, ScriptedSeat, play_game
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import ToolCall
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.agents.results import summarise
from lgbg.core.config import RunConfig
from lgbg.core.contracts import validate_abandonment
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify
from lgbg.core.types import Action

MODEL = "mock-model"
AT = "2026-02-11T09:30:00+00:00"
ILLEGAL = ToolCall(id="illegal", name="spend", arguments={})
LEGAL_ZERO: list[tuple[str, dict[str, Any]]] = [
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("spend", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("spend", {}),
]
LEGAL_ONE: list[tuple[str, dict[str, Any]]] = [
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("spend", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
]


def calls(actions: Sequence[tuple[str, dict[str, Any]]], prefix: str) -> list[ToolCall]:
    return [
        ToolCall(id=f"{prefix}-{index}", name=name, arguments=params)
        for index, (name, params) in enumerate(actions)
    ]


def prompts(tmp_path: Path) -> PromptSet:
    tmp_path.mkdir(parents=True, exist_ok=True)
    game_prompt = tmp_path / "game.md"
    game_prompt.write_text("The fixture game: take, gamble or spend.\n", encoding="utf-8")
    return PromptSet.load("fixture", game_prompt=game_prompt)


def price_table() -> PriceTable:
    return PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
    )


def play(
    tmp_path: Path,
    *,
    provider: MockProvider,
    run_id: str = "r-abandon",
    policy: TurnPolicy | None = None,
) -> Any:
    return asyncio.run(
        play_game(
            game="fixture",
            config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
            directory=tmp_path / run_id,
            run_id=run_id,
            seats={
                0: ModelSeat(
                    provider=provider,
                    model=MODEL,
                    provider_id="mock",
                    provider_version="1",
                ),
                1: ScriptedSeat(
                    actions=[
                        Action(player=1, type=name, params=params) for name, params in LEGAL_ONE
                    ]
                ),
            },
            prompts=prompts(tmp_path),
            price_table=price_table(),
            policy=policy or TurnPolicy(redo_budget=2),
            clock=lambda: AT,
        )
    )


def records(result: Any) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in result.sidecar_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_exhaustion_abandons_the_game_with_the_failing_decision(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.ALWAYS_ILLEGAL, action=ILLEGAL),
        policy=TurnPolicy(redo_budget=2),
    )
    written = records(result)
    decisions = [record for record in written if record["t"] == "decision"]
    abandonments = [record for record in written if record["t"] == "abandonment"]

    assert result.completed is False
    assert result.abandonment is not None
    assert result.abandonment.seat == 0
    assert result.abandonment.model == MODEL
    assert result.abandonment.attempts == 2
    assert result.abandonment.final_rejection == {
        "code": "TOKENS_UNAVAILABLE",
        "detail": "standard",
        "attempt": 2,
    }
    assert result.abandonment.failure == "redo_exhausted"
    assert len(decisions) == 2
    assert [record["attempt"] for record in decisions] == [1, 2]
    assert len(abandonments) == 1
    record = abandonments[0]
    assert record["game_id"] == result.game_id
    assert record["request_id"] == decisions[0]["request_id"]
    assert record["seat"] == 0
    assert record["player"] == 0
    assert record["model"] == MODEL
    assert record["provider"] == "mock"
    assert record["attempts"] == 2
    assert record["redo_budget"] == 2
    assert record["final_rejection"] == decisions[-1]["rejection"]
    assert record["failure"] == "redo_exhausted"
    assert validate_abandonment(record) == []
    broken = dict(record)
    del broken["final_rejection"]
    assert any("final_rejection" in problem for problem in validate_abandonment(broken))


def test_an_abandoned_game_writes_no_terminal_record(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.ALWAYS_ILLEGAL, action=ILLEGAL),
        policy=TurnPolicy(redo_budget=2),
    )
    log = GameLogReader(god_log_path(result.directory, result.game_id)).read()

    assert log.terminal is None
    assert len(log.actions) == 2, "the refused attempts are still in the god log"
    assert all(record.result.get("ok") is False for record in log.actions)
    assert all(record["t"] != "game" for record in records(result))


def test_verify_reports_an_abandoned_game_as_incomplete_without_failing(
    tmp_path: Path, capsys: Any
) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.ALWAYS_ILLEGAL, action=ILLEGAL),
        policy=TurnPolicy(redo_budget=2),
    )
    log = GameLogReader(god_log_path(result.directory, result.game_id)).read()
    report = verify(log, get_game("fixture"))

    assert report.completed is False
    capsys.readouterr()
    code = main(["verify", str(result.directory)])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "incomplete" in out
    assert "Traceback" not in out + err


def test_an_abandoned_game_is_excluded_from_outcomes_and_counted_per_model(
    tmp_path: Path,
) -> None:
    abandoned = play(
        tmp_path / "abandoned",
        provider=MockProvider(Behaviour.ALWAYS_ILLEGAL, action=ILLEGAL),
        run_id="r-abandoned",
        policy=TurnPolicy(redo_budget=2),
    )
    completed = play(
        tmp_path / "completed",
        provider=MockProvider(Behaviour.CORRECT_PLAY, actions=calls(LEGAL_ZERO, "zero")),
        run_id="r-completed",
        policy=TurnPolicy(redo_budget=2),
    )

    summary = summarise([abandoned, completed])
    rows = {row.model: row for row in summary.per_model}

    assert summary.completed == 1
    assert summary.abandoned == 1
    assert rows[MODEL].completed == 1
    assert rows[MODEL].wins == 1
    assert rows[MODEL].losses == 0
    assert rows[MODEL].abandoned == 1
