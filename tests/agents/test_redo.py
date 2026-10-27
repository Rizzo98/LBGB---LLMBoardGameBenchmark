"""The redo loop: one shared prompt, one budget, one conversation (PRD-v2 FR-7.1 to FR-7.4).

An illegal action is answered inside the same decision turn. The model is told the engine's refusal
in one shared sentence, keeps the conversation it already had, and is asked again. Every attempt is
recorded, including the rejected ones, so a turn that needed two tries shows both.

The fixture game is used because it isolates the policy from Catan's rules: a spend without tokens
is refused, a take is always legal, and the policy above the engine is what these tests measure.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import ToolCall
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.core.config import RunConfig
from lgbg.core.prompts import digest
from lgbg.core.types import Action
from lgbg.runner import LlmAgent, ScriptedAgent, run_game

MODEL = "mock-model"
AT = "2026-02-11T09:30:00+00:00"
ILLEGAL = ToolCall(id="illegal", name="spend", arguments={})
# Seat 0 wins the fixture in twelve legal actions: five takes, a spend, five more takes, a spend.
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
    game_prompt = tmp_path / "game.md"
    game_prompt.write_text("The fixture game: take, gamble or spend.\n", encoding="utf-8")
    return PromptSet.load("fixture", game_prompt=game_prompt)


def scripted_one() -> ScriptedAgent:
    return ScriptedAgent(
        actions=[Action(player=1, type=name, params=params) for name, params in LEGAL_ONE]
    )


def model_zero(provider: MockProvider) -> LlmAgent:
    return LlmAgent(
        provider=provider,
        model=MODEL,
        provider_id="mock",
        provider_version="1",
    )


def run(
    tmp_path: Path,
    *,
    model_actions: Sequence[ToolCall],
    policy: TurnPolicy | None = None,
) -> dict[str, Any]:
    directory = tmp_path / "run"
    provider = MockProvider(Behaviour.CORRECT_PLAY, actions=model_actions)
    price_table = PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
    )
    result = run_game_sync(
        game="fixture",
        config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
        directory=directory,
        run_id="r-redo",
        seats={0: model_zero(provider), 1: scripted_one()},
        prompts=prompts(tmp_path),
        price_table=price_table,
        policy=policy,
        clock=lambda: AT,
    )
    records = [
        json.loads(line)
        for line in result.sidecar_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {"result": result, "records": records, "directory": directory}


def run_game_sync(**kwargs: Any) -> Any:
    import asyncio

    return asyncio.run(run_game(**kwargs))


def decision_records(run_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        record
        for record in run_data["records"]
        if record["t"] == "decision" and record["model"] == MODEL
    ]


def test_a_refused_action_is_asked_again_in_the_same_decision_turn(tmp_path: Path) -> None:
    model_actions = [ILLEGAL, *calls(LEGAL_ZERO, "zero")]
    data = run(tmp_path, model_actions=model_actions, policy=TurnPolicy(redo_budget=3))
    records = decision_records(data)

    assert data["result"].completed is True
    assert [record["attempt"] for record in records[:2]] == [1, 2]
    first, second = records[:2]
    assert first["request_id"] == second["request_id"], "a redo is not a fresh decision"
    assert first["outcome"] == {"kind": "rejection"}
    assert first["rejection"]["code"] == "TOKENS_UNAVAILABLE"
    assert second["outcome"]["kind"] == "action"
    assert second["rejection"] == {
        "code": "TOKENS_UNAVAILABLE",
        "detail": "standard",
        "attempt": 1,
    }
    assert second["messages"][: len(first["messages"])] == first["messages"], (
        "the retry continues the conversation rather than starting another"
    )


def test_the_redo_carries_the_one_shared_prompt(tmp_path: Path) -> None:
    model_actions = [ILLEGAL, *calls(LEGAL_ZERO, "zero")]
    data = run(tmp_path, model_actions=model_actions, policy=TurnPolicy(redo_budget=3))
    manifest = json.loads(data["result"].manifest_path.read_text(encoding="utf-8"))
    expected = prompts(tmp_path)
    records = decision_records(data)
    retry = records[1]

    texts = [message["content"] for message in retry["messages"]]
    assert expected.redo_text("TOKENS_UNAVAILABLE") in texts
    assert manifest["prompts"]["redo"] == digest(expected.text("redo"))
    assert expected.hashes() == manifest["prompts"]


def test_the_redo_budget_is_one_declared_value_for_every_attempt(tmp_path: Path) -> None:
    model_actions = [ILLEGAL, *calls(LEGAL_ZERO, "zero")]
    policy = TurnPolicy(redo_budget=2)
    data = run(tmp_path, model_actions=model_actions, policy=policy)
    manifest = json.loads(data["result"].manifest_path.read_text(encoding="utf-8"))
    records = decision_records(data)

    assert manifest["policies"]["redo_budget"] == 2
    assert {record["redo_budget"] for record in records} == {2}
    assert all(record["attempt"] <= policy.redo_budget for record in records)


def test_every_attempt_of_a_turn_is_reconstructible_from_the_record(tmp_path: Path) -> None:
    model_actions = [ILLEGAL, *calls(LEGAL_ZERO, "zero")]
    data = run(tmp_path, model_actions=model_actions, policy=TurnPolicy(redo_budget=3))
    records = decision_records(data)
    first, second = records[:2]
    game_id = data["result"].game_id

    from lgbg.agents.sidecar import messages_from_run

    first_messages = messages_from_run(data["directory"], game_id, first["request_id"], attempt=1)
    final_messages = messages_from_run(data["directory"], game_id, first["request_id"])

    assert first_messages == first["messages"]
    assert final_messages == second["messages"]


def test_two_models_and_two_seats_receive_the_same_budget_and_words(tmp_path: Path) -> None:
    directory = tmp_path / "run-two"
    provider_a = MockProvider(Behaviour.CORRECT_PLAY, actions=[ILLEGAL, *calls(LEGAL_ZERO, "a")])
    provider_b = MockProvider(Behaviour.CORRECT_PLAY, actions=[ILLEGAL, *calls(LEGAL_ONE, "b")])
    price_table = PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=(
            ModelPrice(model="model-a", prompt=0, completion=0),
            ModelPrice(model="model-b", prompt=0, completion=0),
        ),
    )
    result = run_game_sync(
        game="fixture",
        config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
        directory=directory,
        run_id="r-uniform",
        seats={
            0: LlmAgent(
                provider=provider_a,
                model="model-a",
                provider_id="mock",
                provider_version="1",
            ),
            1: LlmAgent(
                provider=provider_b,
                model="model-b",
                provider_id="mock",
                provider_version="1",
            ),
        },
        prompts=prompts(tmp_path),
        price_table=price_table,
        policy=TurnPolicy(redo_budget=2),
        clock=lambda: AT,
    )

    records = [
        json.loads(line)
        for line in result.sidecar_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    decisions = [record for record in records if record["t"] == "decision"]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    retries = [record for record in decisions if record["attempt"] == 2]
    redo_texts = {
        record["model"]: [
            message["content"]
            for message in record["messages"]
            if message["content"] and "Your action was refused" in message["content"]
        ]
        for record in retries
    }

    assert result.completed is True
    assert manifest["policies"]["redo_budget"] == 2
    assert {record["redo_budget"] for record in decisions} == {2}
    assert set(redo_texts) == {"model-a", "model-b"}
    assert all(len(texts) == 1 for texts in redo_texts.values())
    assert len({texts[0] for texts in redo_texts.values()}) == 1
