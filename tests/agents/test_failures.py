"""Failure kinds and the budgets they are charged to (PRD-v2 FR-7.6 to FR-7.11).

Every way a model can fail is a named kind in a declared set, and each kind is charged to the budget
that explains it: a malformed tool call spends a redo, prose and a runaway do not, and a timeout
abandons like exhaustion. No behaviour can leave the runner waiting: each one reaches a completed or
an abandoned result, which is the property these tests exist to keep.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.agents.game import ModelSeat, ScriptedSeat, play_game
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import ToolCall
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.core.config import RunConfig
from lgbg.core.contracts import FAILURE_KINDS, validate_decision
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


def play(tmp_path: Path, provider: MockProvider, policy: TurnPolicy) -> Any:
    tmp_path.mkdir(parents=True, exist_ok=True)
    game_prompt = tmp_path / "game.md"
    game_prompt.write_text("The fixture game: take, gamble or spend.\n", encoding="utf-8")
    return asyncio.run(
        play_game(
            game="fixture",
            config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
            directory=tmp_path / "run",
            run_id="r-failure",
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
            prompts=PromptSet.load("fixture", game_prompt=game_prompt),
            price_table=PriceTable(
                source="test",
                read_at=AT,
                unit=PRICE_UNIT,
                models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
            ),
            policy=policy,
            clock=lambda: AT,
        )
    )


def decisions(result: Any) -> list[dict[str, Any]]:
    return [
        record
        for record in (
            json.loads(line)
            for line in result.sidecar_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if record["t"] == "decision"
    ]


def test_the_failure_kinds_are_a_declared_closed_set(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.PROSE_ONLY),
        policy=TurnPolicy(redo_budget=2),
    )
    record = decisions(result)[0]

    assert FAILURE_KINDS == (
        "malformed_arguments",
        "no_action",
        "redo_exhausted",
        "runaway",
        "timeout",
    )
    assert record["failure"] in FAILURE_KINDS
    broken = dict(record)
    broken["failure"] = "made_up"
    assert any("failure" in problem for problem in validate_decision(broken))


@pytest.mark.parametrize(
    ("behaviour", "failure", "attempts", "calls_made"),
    [
        (Behaviour.ALWAYS_ILLEGAL, "redo_exhausted", 2, 2),
        (Behaviour.MALFORMED_ARGUMENTS, "redo_exhausted", 2, 2),
        (Behaviour.PROSE_ONLY, "no_action", 0, 1),
        (Behaviour.TIMEOUT, "timeout", 0, 1),
        (Behaviour.RUNAWAY, "runaway", 0, 3),
    ],
)
def test_every_failing_behaviour_terminates_completed_or_abandoned(
    tmp_path: Path,
    behaviour: Behaviour,
    failure: str,
    attempts: int,
    calls_made: int,
) -> None:
    provider = (
        MockProvider(behaviour, action=ILLEGAL)
        if behaviour is Behaviour.ALWAYS_ILLEGAL
        else MockProvider(behaviour)
    )
    result = play(
        tmp_path,
        provider=provider,
        policy=TurnPolicy(redo_budget=2, step_budget=3, decision_timeout_s=5),
    )

    assert result.completed is False
    assert result.abandonment is not None
    assert result.abandonment.failure == failure
    assert result.abandonment.attempts == attempts
    assert result.abandonment.calls == calls_made
    assert len(decisions(result)) == calls_made
    assert all(
        record["failure"] is None or record["failure"] in FAILURE_KINDS
        for record in decisions(result)
    )


def test_a_malformed_tool_call_is_charged_to_the_redo_budget(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.MALFORMED_ARGUMENTS),
        policy=TurnPolicy(redo_budget=2),
    )
    written = decisions(result)

    assert [record["attempt"] for record in written] == [1, 2]
    assert [record["failure"] for record in written] == [
        "malformed_arguments",
        "malformed_arguments",
    ]
    assert [record["rejection"] for record in written] == [
        {"code": "MALFORMED_ARGUMENTS", "detail": "standard", "attempt": 1},
        {"code": "MALFORMED_ARGUMENTS", "detail": "standard", "attempt": 2},
    ]
    assert result.abandonment.attempts == 2


def test_prose_only_is_recorded_and_does_not_consume_a_redo(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.PROSE_ONLY),
        policy=TurnPolicy(redo_budget=2),
    )
    record = decisions(result)[0]

    assert record["attempt"] == 1
    assert record["redo_budget"] == 2
    assert record["failure"] == "no_action"
    assert record["outcome"] == {"kind": "failure"}
    assert record["response"] == {"text": "I would rather not move.", "tool_calls": None}
    assert result.abandonment.attempts == 0


def test_a_runaway_does_not_consume_a_redo(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.RUNAWAY),
        policy=TurnPolicy(redo_budget=2, step_budget=3),
    )
    written = decisions(result)

    assert len(written) == 3, "the step budget is what stopped it"
    assert [record["failure"] for record in written] == [None, None, "runaway"]
    assert result.abandonment.attempts == 0
    assert result.abandonment.failure == "runaway"


def test_a_timeout_records_the_call_and_the_exchange_it_had(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.TIMEOUT),
        policy=TurnPolicy(redo_budget=2),
    )
    record = decisions(result)[0]

    assert record["failure"] == "timeout"
    assert record["outcome"] == {"kind": "failure"}
    assert record["usage"] is None
    assert record["cost_micro_usd"] is None
    assert record["wire"] is not None
    assert "mock" in record["wire"]["request"]
    assert result.abandonment.attempts == 0
    assert result.abandonment.final_rejection is None


def test_a_correct_play_still_completes(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        provider=MockProvider(Behaviour.CORRECT_PLAY, actions=calls(LEGAL_ZERO, "zero")),
        policy=TurnPolicy(redo_budget=2),
    )

    assert result.completed is True
    assert result.abandonment is None
