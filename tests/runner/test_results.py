"""results.json: per game, per seat, per model, caveats included (K-032).

This is the artefact a researcher reads. The tests drive it through the experiment runner and then
read the file as a consumer would: the design point and its caveat, one line per game, the per-seat
split, and the per-model totals with abandonment kept out of wins and losses.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Final

import tests.games.concurrent_game
import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import ToolCall
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.core.config import RunConfig
from lgbg.core.contracts import validate_results
from lgbg.core.types import Action
from lgbg.runner import (
    ExperimentDesign,
    LlmAgent,
    ScriptedAgent,
    run_experiment,
)

RUN_ID: Final[str] = "r-k032"
AT: Final[str] = "2026-02-11T09:30:00+00:00"
MODEL_A: Final[str] = "model-a"
MODEL_B: Final[str] = "model-b"


def prompts(directory: Path, *, game: str = "concurrent") -> PromptSet:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "game.md"
    path.write_text(f"The {game} game, with no advice.\n", encoding="utf-8")
    return PromptSet.load(game, game_prompt=path)


def price_table(*models: str) -> PriceTable:
    return PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=tuple(
            ModelPrice(model=model, prompt=1_000_000, completion=2_000_000) for model in models
        ),
    )


def llm(model: str, provider: MockProvider) -> LlmAgent:
    return LlmAgent(
        provider=provider,
        model=model,
        provider_id="mock",
        provider_version="1",
    )


def results_of(result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.results_path.read_text(encoding="utf-8"))
    assert validate_results(payload) == []
    return payload


def test_results_record_every_game_seat_and_model(tmp_path: Path) -> None:
    """Two models, four seats, rotated: the file has a line per game, per seat and per model."""
    mark = ToolCall(id="mark", name="mark", arguments={})
    provider_a = MockProvider(Behaviour.ALWAYS_ILLEGAL, action=mark)
    provider_b = MockProvider(Behaviour.ALWAYS_ILLEGAL, action=mark)
    agent_a = llm(MODEL_A, provider_a)
    agent_b = llm(MODEL_B, provider_b)

    result = asyncio.run(
        run_experiment(
            game="concurrent",
            config=RunConfig(seed=7, players=4, interaction_protocol="concurrent"),
            root=tmp_path / "run",
            run_id=RUN_ID,
            seats=[agent_a, agent_b, agent_a, agent_b],
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(MODEL_A, MODEL_B),
            design=ExperimentDesign(seating="rotated"),
            clock=lambda: AT,
        )
    )

    payload = results_of(result)

    assert payload["schema"] == "lgbg.results.v1"
    assert payload["design"]["uncontrolled"] == []
    assert payload["summary"] == {
        "games": 4,
        "completed": 4,
        "abandoned": 0,
        "actions": 16,
        "rejections": 0,
        "rejections_by_code": {},
        "failures": 0,
        "failures_by_kind": {},
        "prompt_tokens": 160,
        "completion_tokens": 80,
        "total_tokens": 240,
        "cost_micro_usd": 320,
        "latency_ms": payload["summary"]["latency_ms"],
        "partial": False,
    }
    assert len(payload["games"]) == 4

    first = payload["games"][0]
    assert first["game_id"] == "g-0000"
    assert first["design"]["replicate"] == 0
    assert first["design"]["rotation"] == 0
    assert first["completed"] is True
    assert first["outcome"] == {
        "winner": 0,
        "scores": {"0": 4, "1": 3, "2": 2, "3": 1},
        "rounds": 1,
    }
    assert first["actions"] == 4
    assert [seat["seat"] for seat in first["seats"]] == [0, 1, 2, 3]
    assert first["seats"][0]["model"] == MODEL_A
    assert first["seats"][0]["outcome"] == "win"
    assert first["seats"][0]["place"] == 1
    assert first["seats"][1]["model"] == MODEL_B
    assert first["seats"][1]["outcome"] == "loss"
    assert first["seats"][1]["place"] == 2
    assert first["seats"][0]["actions"] == 1
    assert first["seats"][0]["prompt_tokens"] == 10
    assert first["seats"][0]["cost_micro_usd"] == 20

    per_model = {row["model"]: row for row in payload["per_model"]}
    assert set(per_model) == {MODEL_A, MODEL_B}
    for row in per_model.values():
        assert row["games"] == 4, "a model holding two seats still plays each game once"
        assert row["completed"] == 4
        assert row["wins"] == 2
        assert row["losses"] == 2
        assert row["abandoned"] == 0
        assert row["actions"] == 8
        assert row["prompt_tokens"] == 80
        assert row["completion_tokens"] == 40
        assert row["cost_micro_usd"] == 160
        assert row["place_counts"] == [{"place": 1, "games": 2}, {"place": 2, "games": 2}]
        assert row["seat_counts"] == [
            {"seat": 0, "games": 2},
            {"seat": 1, "games": 2},
            {"seat": 2, "games": 2},
            {"seat": 3, "games": 2},
        ]

    per_seat = {row["seat"]: row for row in payload["per_seat"]}
    assert set(per_seat) == {0, 1, 2, 3}
    assert per_seat[0]["wins"] == 4
    assert per_seat[0]["losses"] == 0
    assert per_seat[0]["place_counts"] == [{"place": 1, "games": 4}]
    assert per_seat[1]["wins"] == 0
    assert per_seat[1]["losses"] == 4
    assert per_seat[1]["place_counts"] == [{"place": 2, "games": 4}]
    assert per_seat[0]["models"] == [MODEL_A, MODEL_B]


def test_an_abandoned_game_is_its_own_row_and_never_a_loss(tmp_path: Path) -> None:
    """PRD-v2 FR-7.5, FR-11.8: the failing model abandons; no model is charged a loss."""
    provider = MockProvider(
        Behaviour.ALWAYS_ILLEGAL,
        action=ToolCall(id="illegal", name="spend", arguments={}),
    )

    result = asyncio.run(
        run_experiment(
            game="fixture",
            config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
            root=tmp_path / "run",
            run_id=RUN_ID,
            seats=[
                llm("mock-model", provider),
                ScriptedAgent(actions=[Action(player=1, type="take", params={})]),
            ],
            prompts=prompts(tmp_path / "prompts", game="fixture"),
            price_table=price_table("mock-model"),
            design=ExperimentDesign(seating="fixed"),
            policy=TurnPolicy(redo_budget=2),
            clock=lambda: AT,
        )
    )

    payload = results_of(result)

    assert payload["design"]["uncontrolled"] == ["seating"]
    assert payload["summary"]["games"] == 1
    assert payload["summary"]["completed"] == 0
    assert payload["summary"]["abandoned"] == 1
    assert payload["summary"]["actions"] == 0
    assert payload["summary"]["rejections"] == 2
    assert payload["summary"]["rejections_by_code"] == {"TOKENS_UNAVAILABLE": 2}
    assert payload["summary"]["failures_by_kind"] == {"redo_exhausted": 1}

    game = payload["games"][0]
    assert game["completed"] is False
    assert game["outcome"] is None
    assert game["abandonment"] == {
        "seat": 0,
        "model": "mock-model",
        "provider": "mock",
        "request_id": game["abandonment"]["request_id"],
        "failure": "redo_exhausted",
        "attempts": 2,
        "calls": 2,
        "redo_budget": 2,
        "final_rejection": {"code": "TOKENS_UNAVAILABLE", "detail": "standard", "attempt": 2},
        "actions": 0,
    }
    assert game["seats"][0]["abandoned"] is True
    assert game["seats"][0]["outcome"] is None
    assert game["seats"][0]["place"] is None
    assert game["seats"][1]["agent"] == "scripted"
    assert game["seats"][1]["abandoned"] is False

    per_model = {row["model"]: row for row in payload["per_model"]}
    assert set(per_model) == {"mock-model"}
    row = per_model["mock-model"]
    assert row["games"] == 1
    assert row["completed"] == 0
    assert row["wins"] == 0
    assert row["losses"] == 0
    assert row["abandoned"] == 1
    assert row["seat_counts"] == [{"seat": 0, "games": 1}]

    per_seat = {row["seat"]: row for row in payload["per_seat"]}
    assert set(per_seat) == {0}
    assert per_seat[0]["abandoned"] == 1
    assert per_seat[0]["losses"] == 0
