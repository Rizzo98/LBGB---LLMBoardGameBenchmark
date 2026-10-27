"""Context policy: what the model is shown of the position, declared not emergent (PRD-v2 FR-8).

Three strategies are supported and all three are recorded in the manifest: the full projection every
turn, a delta with a periodic full refresh (the default), and a bounded window of recent turns. The
strategy is one value for the whole run, so two models in one run cannot be compared across two
different contexts. The sidecar still records the exact messages sent, so any decision can be read
back without guessing which strategy produced it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.agents.context import ContextBuilder, ContextPolicy, ContextStrategy
from lgbg.agents.game import ModelSeat, ScriptedSeat, play_game
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import Message, Role, ToolCall
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.agents.sidecar import messages_from_run
from lgbg.core.assist import render_decision
from lgbg.core.config import AssistLevel, RunConfig
from lgbg.core.contracts import validate_manifest
from lgbg.core.game import Applied, Game, get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.core.types import Action, Observation

MODEL = "mock-model"
AT = "2026-02-11T09:30:00+00:00"
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


class RecordingMock(MockProvider):
    """A mock that remembers the exact messages each call was sent."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.seen: list[tuple[Message, ...]] = []

    async def complete(self, messages: Any, tools: Any, config: Any) -> Any:
        self.seen.append(tuple(messages))
        return await super().complete(messages, tools, config)


def provider() -> MockProvider:
    return MockProvider(Behaviour.CORRECT_PLAY, actions=calls(LEGAL_ZERO, "zero"))


def play(tmp_path: Path, context: ContextPolicy, run_id: str = "r-context") -> Any:
    return asyncio.run(
        play_game(
            game="fixture",
            config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
            directory=tmp_path / run_id,
            run_id=run_id,
            seats={
                0: ModelSeat(
                    provider=provider(),
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
            price_table=PriceTable(
                source="test",
                read_at=AT,
                unit=PRICE_UNIT,
                models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
            ),
            policy=TurnPolicy(redo_budget=2),
            context=context,
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


def observe(game: Game, state: Any, player: int) -> Observation:
    return game.observe(state, player)


def advance(game: Game, state: Any, player: int) -> Any:
    result = game.apply(
        state,
        Action(player=player, type="take", params={}),
        SeededRandomSource(1),
    )
    assert isinstance(result, Applied)
    return result.state


def user_texts(messages: Sequence[Message]) -> list[str | None]:
    return [message.content for message in messages if message.role is Role.USER]


def test_the_default_strategy_is_delta_with_refresh() -> None:
    policy = ContextPolicy()

    assert policy.strategy is ContextStrategy.DELTA_WITH_REFRESH
    assert policy.refresh_every >= 1
    assert policy.window >= 1


def test_full_projection_is_sent_every_turn(tmp_path: Path) -> None:
    game = get_game("fixture")
    state = game.initial_state(game_config(), SeededRandomSource(1))
    observation = observe(game, state, 0)
    surface = render_decision(game, state, 0, assist=AssistLevel.L1)
    builder = ContextBuilder(
        ContextPolicy(strategy=ContextStrategy.FULL),
        game=game,
    )

    messages = builder.messages(
        prompts(tmp_path), seat=0, decision=0, decision_surface=surface, observation=observation
    )

    assert user_texts(messages) == [surface]


def test_delta_with_refresh_sends_a_delta_between_full_projections(tmp_path: Path) -> None:
    game = get_game("fixture")
    state = game.initial_state(game_config(), SeededRandomSource(1))
    builder = ContextBuilder(
        ContextPolicy(strategy=ContextStrategy.DELTA_WITH_REFRESH, refresh_every=2),
        game=game,
    )
    first_observation = observe(game, state, 0)
    first_surface = render_decision(game, state, 0, assist=AssistLevel.L1)
    second_state = advance(game, state, 0)
    second_observation = observe(game, second_state, 0)
    second_surface = render_decision(game, second_state, 0, assist=AssistLevel.L1)
    third_state = advance(game, second_state, 1)
    third_observation = observe(game, third_state, 0)
    third_surface = render_decision(game, third_state, 0, assist=AssistLevel.L1)

    messages = [
        builder.messages(
            prompts(tmp_path),
            seat=0,
            decision=index,
            decision_surface=surface,
            observation=observation,
        )
        for index, (surface, observation) in enumerate(
            [
                (first_surface, first_observation),
                (second_surface, second_observation),
                (third_surface, third_observation),
            ]
        )
    ]

    assert user_texts(messages[0]) == [first_surface]
    delta = user_texts(messages[1])[0]
    assert delta is not None
    assert delta.startswith("delta:")
    assert "asking:" in delta, "the decision surface still travels with the delta"
    assert user_texts(messages[2]) == [third_surface], "the refresh is a full projection"


def test_a_bounded_window_keeps_only_the_most_recent_turns(tmp_path: Path) -> None:
    game = get_game("fixture")
    state = game.initial_state(game_config(), SeededRandomSource(1))
    builder = ContextBuilder(
        ContextPolicy(strategy=ContextStrategy.BOUNDED_WINDOW, window=2),
        game=game,
    )
    surfaces: list[str] = []
    observations: list[Observation] = []
    current = state
    for _ in range(3):
        surfaces.append(render_decision(game, current, 0, assist=AssistLevel.L1))
        observations.append(observe(game, current, 0))
        current = advance(game, current, current.turn)

    messages = [
        builder.messages(
            prompts(tmp_path),
            seat=0,
            decision=index,
            decision_surface=surfaces[index],
            observation=observations[index],
        )
        for index in range(3)
    ]

    assert user_texts(messages[0]) == [surfaces[0]]
    assert user_texts(messages[1]) == [surfaces[0], surfaces[1]]
    assert user_texts(messages[2]) == [surfaces[1], surfaces[2]]


def game_config() -> Any:
    from lgbg.core.config import GameConfig

    return GameConfig()


def test_the_default_is_delta_with_refresh_end_to_end(tmp_path: Path) -> None:
    result = play(tmp_path, ContextPolicy())
    manifest: dict[str, Any] = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    written = decisions(result)
    first = written[0]["messages"]
    second = written[1]["messages"]

    assert manifest["policies"]["context"] == "delta_with_refresh"
    first_user = next(
        message["content"] for message in reversed(first) if message["role"] == "user"
    )
    second_user = next(
        message["content"] for message in reversed(second) if message["role"] == "user"
    )
    assert first_user is not None
    assert first_user.startswith("{")
    assert second_user is not None
    assert second_user.startswith("delta:")


def test_one_context_policy_is_recorded_for_every_model_in_the_run(tmp_path: Path) -> None:
    from lgbg.agents.game import ModelSeat, build_manifest

    seats = {
        seat: ModelSeat(
            provider=MockProvider(Behaviour.CORRECT_PLAY, action=calls(LEGAL_ZERO, "x")[0]),
            model=f"model-{seat}",
            provider_id="mock",
            provider_version="1",
        )
        for seat in (0, 1)
    }
    manifest: dict[str, Any] = build_manifest(
        game=get_game("fixture"),
        config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
        run_id="r-policy",
        seats=seats,
        prompts=prompts(tmp_path),
        price_table=PriceTable(
            source="test",
            read_at=AT,
            unit=PRICE_UNIT,
            models=(
                ModelPrice(model="model-0", prompt=0, completion=0),
                ModelPrice(model="model-1", prompt=0, completion=0),
            ),
        ),
        policy=TurnPolicy(),
        context=ContextPolicy(strategy=ContextStrategy.DELTA_WITH_REFRESH, refresh_every=5),
    )

    assert validate_manifest(manifest) == []
    assert manifest["policies"]["context"] == "delta_with_refresh"
    assert manifest["policies"]["context_refresh_every"] == 5
    assert all("context" not in seat for seat in manifest["seats"])


def test_the_strategy_is_recorded_once_in_the_manifest(tmp_path: Path) -> None:
    result = play(
        tmp_path,
        ContextPolicy(strategy=ContextStrategy.BOUNDED_WINDOW, window=4),
    )
    manifest: dict[str, Any] = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert validate_manifest(manifest) == []
    assert manifest["policies"]["context"] == "bounded_window"
    assert manifest["policies"]["context_refresh_every"] == 10
    assert manifest["policies"]["context_window"] == 4


def test_each_strategy_plays_the_same_record_and_reconstructs_its_messages(
    tmp_path: Path,
) -> None:
    hashes: list[str] = []
    for strategy in (
        ContextStrategy.FULL,
        ContextStrategy.DELTA_WITH_REFRESH,
        ContextStrategy.BOUNDED_WINDOW,
    ):
        directory = tmp_path / strategy.value
        provider = RecordingMock(Behaviour.CORRECT_PLAY, actions=calls(LEGAL_ZERO, "zero"))
        result = asyncio.run(
            play_game(
                game="fixture",
                config=RunConfig(seed=7, players=2, interaction_protocol="decline_only"),
                directory=directory,
                run_id=f"r-{strategy.value}",
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
                price_table=PriceTable(
                    source="test",
                    read_at=AT,
                    unit=PRICE_UNIT,
                    models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
                ),
                policy=TurnPolicy(redo_budget=2),
                context=ContextPolicy(strategy=strategy, refresh_every=3, window=2),
                clock=lambda: AT,
            )
        )
        from lgbg.core.log import GameLogReader, god_log_path
        from lgbg.core.replay import verify

        log = GameLogReader(god_log_path(directory, result.game_id)).read()
        report = verify(log, get_game("fixture"))
        hashes.append(report.terminal_hash)

        for index, record in enumerate(decisions(result)):
            reconstructed = messages_from_run(directory, result.game_id, record["request_id"])
            assert reconstructed == record["messages"]
            assert reconstructed == [message.to_mapping() for message in provider.seen[index]]

    assert len(set(hashes)) == 1, "the context strategy must not change the game"
