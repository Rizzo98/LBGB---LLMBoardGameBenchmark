"""The runner core: every seat is an agent, and one game runs through the facade (PRD-v2 FR-11.1,
FR-11.7, FR-10.1).

The runner owns the seat-to-agent mapping and the run manifest, and nothing else. Three kinds of
agent are declared - an LLM agent, a reference player and a scripted agent - so a table can mix a
model with a deterministic opponent, and the manifest says which seat was which. A reference player
is a *policy*: it chooses an action from the game's own offered actions, never from a prompt, and
the record never mistakes it for a model.

The game driven in these tests is the fixture: two seats, three actions and a terminal condition, so
a defect is a machinery defect rather than a rules defect. The one thing the runner must not do is
know which game it is driving: the initial configuration is what the design declares, not a key the
runner reads out of the game's options.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest

import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.agents.context import ContextPolicy
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import ToolCall
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.contracts import validate_manifest
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from lgbg.core.rng import Purpose
from lgbg.core.types import Action, JsonValue
from lgbg.runner import (
    AgentKind,
    GameDesign,
    LlmAgent,
    ManifestError,
    ReferenceAgent,
    ReferenceView,
    ScriptedAgent,
    build_manifest,
    run_game,
)

MODEL: Final[str] = "mock-model"
RUN_ID: Final[str] = "r-k027"
AT: Final[str] = "2026-02-11T09:30:00+00:00"

REFERENCE_CHOICE: Final[Purpose] = "reference_player_choice"
"""The reference doubles' one draw, named so a choice is not a bare literal (FR-2.3)."""

LEGAL_ZERO: Final[list[tuple[str, dict[str, Any]]]] = [
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
"""Seat 0's legal script: five takes, a score, five takes and a winning score."""

WINNING_SCRIPT: Final[list[tuple[str, dict[str, Any]]]] = [
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("spend", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("take", {}),
    ("spend", {}),
]
"""Seat 0's ten actions when it is scripted and a reference player holds seat 1."""


def calls(actions: Sequence[tuple[str, dict[str, Any]]], prefix: str) -> list[ToolCall]:
    return [
        ToolCall(id=f"{prefix}-{index}", name=name, arguments=params)
        for index, (name, params) in enumerate(actions)
    ]


def prompts(directory: Path) -> PromptSet:
    directory.mkdir(parents=True, exist_ok=True)
    game_prompt = directory / "game.md"
    game_prompt.write_text("The fixture game: take, gamble or spend.\n", encoding="utf-8")
    return PromptSet.load("fixture", game_prompt=game_prompt)


def memory_prompts() -> PromptSet:
    """The four layers as bytes in memory: a manifest test then needs no temporary directory."""
    layers = ("game", "policy", "redo", "system")
    return PromptSet(
        game="fixture",
        texts={layer: f"{layer} prompt\n" for layer in layers},
        sources={layer: Path(f"/{layer}.md") for layer in layers},
    )


def price_table() -> PriceTable:
    return PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
    )


def llm(
    actions: Sequence[ToolCall] | None = None,
    *,
    behaviour: Behaviour = Behaviour.CORRECT_PLAY,
) -> LlmAgent:
    if actions is None:
        name = "take" if behaviour is Behaviour.CORRECT_PLAY else "spend"
        actions = [ToolCall(id="m-0", name=name, arguments={})]
    return LlmAgent(
        provider=MockProvider(behaviour, actions=actions),
        model=MODEL,
        provider_id="mock",
        provider_version="1",
    )


@dataclass(frozen=True, slots=True)
class SpendFirst:
    """A reference player that spends when it can and takes otherwise: deterministic, no draws."""

    name: str = "spend-first"

    def choose(self, view: ReferenceView) -> Action:
        offered = view.game.legal_actions(view.state, view.seat)
        spending = [action for action in offered if action.type == "spend"]
        return spending[0] if spending else offered[0]


@dataclass(frozen=True, slots=True)
class RandomLegal:
    """A reference seat for tests: one of the offered actions, drawn."""

    name: str = "random-legal"

    def choose(self, view: ReferenceView) -> Action:
        offered = view.game.legal_actions(view.state, view.seat)
        # By index, like the fuzz harness: a draw records what it chose, and an Action is not JSON.
        return offered[view.chooser.randint(0, len(offered) - 1, purpose=REFERENCE_CHOICE)]


def config(*, players: int = 2, options: Mapping[str, JsonValue] | None = None) -> RunConfig:
    return RunConfig(
        seed=7,
        players=players,
        interaction_protocol="fixture",
        game_config=GameConfig(dict(options or {})),
    )


def manifest_for(
    seats: Mapping[int, Any],
    *,
    players: int = 2,
    design: GameDesign | None = None,
    options: Mapping[str, JsonValue] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = build_manifest(
        game=get_game("fixture"),
        config=config(players=players, options=options),
        run_id=RUN_ID,
        seats=seats,
        prompts=memory_prompts(),
        price_table=price_table(),
        policy=TurnPolicy(),
        context=ContextPolicy(),
        design=design or GameDesign.single_game(),
    )
    return manifest


# --- the declared agent set (FR-11.1) -----------------------------------------------------------


def test_a_table_may_declare_all_three_agent_kinds() -> None:
    """FR-11.1: an LLM agent, a reference player and a scripted agent, side by side."""
    manifest = manifest_for(
        {
            0: llm(),
            1: ReferenceAgent(SpendFirst()),
            2: ScriptedAgent([Action(player=2, type="take", params={})]),
        },
        players=3,
    )

    assert [row["agent"] for row in manifest["seats"]] == ["llm", "reference", "scripted"]
    assert [row["player"] for row in manifest["seats"]] == [None, "spend-first", "scripted"]
    assert [row["model"] for row in manifest["seats"]] == [MODEL, None, None]
    assert [row["provider"] for row in manifest["seats"]] == ["mock", None, None]
    assert validate_manifest(manifest) == []


def test_a_mixed_table_plays_to_a_verdict(tmp_path: Path) -> None:
    """A model and a reference player share one game, and the record keeps them apart."""
    directory = tmp_path / "run"

    result = asyncio.run(
        run_game(
            game="fixture",
            config=config(),
            directory=directory,
            run_id=RUN_ID,
            seats={0: llm(calls(WINNING_SCRIPT, "m")), 1: ReferenceAgent(SpendFirst())},
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(),
            clock=lambda: AT,
        )
    )

    assert result.completed is True
    assert result.winner == 0
    assert result.actions == 19, "seat 0's ten actions and seat 1's nine reference actions"
    assert result.decisions == 10, "only the model seat makes decisions worth recording"
    assert result.model_seats == {0: MODEL}, "a reference seat is never a model seat"

    manifest: dict[str, Any] = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert validate_manifest(manifest) == []
    assert manifest["seats"][1] == {
        "seat": 1,
        "agent": "reference",
        "player": "spend-first",
        "model": None,
        "provider": None,
        "sampling": None,
    }
    assert manifest["providers"] == [{"id": "mock", "version": "1"}]
    assert set(manifest["prompts"]) == {"game", "system", "policy", "redo"}
    assert manifest["price_table"]["models"] == [{"model": MODEL, "prompt": 0, "completion": 0}]
    assert manifest["policies"]["context"] == "delta_with_refresh"
    assert manifest["policies"]["redo_budget"] == TurnPolicy().redo_budget

    god = GameLogReader(god_log_path(directory, result.game_id)).read()
    report = verify(god, get_game("fixture"))
    assert report.actions == 19
    assert replay(god, get_game("fixture")).terminal_hash == report.terminal_hash

    records = [
        json.loads(line)
        for line in result.sidecar_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    decisions = [record for record in records if record["t"] == "decision"]
    assert len(decisions) == 10
    assert {record["seat"] for record in decisions} == {0}, "the reference seat has no sidecar"


def test_a_reference_player_chooses_from_the_offered_actions(tmp_path: Path) -> None:
    """The reference player reads the game's own enumeration; it never parses a prompt."""
    seen: list[tuple[int, tuple[str, ...]]] = []

    @dataclass(frozen=True, slots=True)
    class Recorder:
        name: str = "recorder"

        def choose(self, view: ReferenceView) -> Action:
            offered = view.game.legal_actions(view.state, view.seat)
            seen.append((view.seat, tuple(action.type for action in offered)))
            assert view.request.player == view.seat
            return offered[0]

    result = asyncio.run(
        run_game(
            game="fixture",
            config=config(),
            directory=tmp_path / "run",
            run_id=RUN_ID,
            seats={
                0: ScriptedAgent(
                    [Action(player=0, type=name, params=params) for name, params in WINNING_SCRIPT]
                ),
                1: ReferenceAgent(Recorder()),
            },
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(),
            clock=lambda: AT,
        )
    )

    assert result.completed is True
    assert seen, "the reference seat was asked for a decision"
    assert all(seat == 1 for seat, _ in seen)
    assert all(offered for _, offered in seen), "the enumeration was not empty"


def test_a_reference_seat_plays_the_same_game_twice(tmp_path: Path) -> None:
    """Its choice is drawn from a source the run derives, so two runs agree byte for byte."""
    logs: list[bytes] = []
    for index in range(2):
        directory = tmp_path / f"run-{index}"
        result = asyncio.run(
            run_game(
                game="fixture",
                config=config(),
                directory=directory,
                run_id=RUN_ID,
                seats={0: llm(calls(LEGAL_ZERO, "m")), 1: ReferenceAgent(RandomLegal())},
                prompts=prompts(tmp_path / "prompts"),
                price_table=price_table(),
                clock=lambda: AT,
            )
        )
        logs.append(god_log_path(directory, result.game_id).read_bytes())

    assert logs[0] == logs[1]


def test_an_abandoned_game_still_comes_back_through_the_runner(tmp_path: Path) -> None:
    """FR-11.6: a failure at the agent layer abandons the game, and the runner says so."""
    directory = tmp_path / "run"
    result = asyncio.run(
        run_game(
            game="fixture",
            config=config(),
            directory=directory,
            run_id=RUN_ID,
            seats={
                0: llm(behaviour=Behaviour.ALWAYS_ILLEGAL),
                1: ReferenceAgent(SpendFirst()),
            },
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(),
            clock=lambda: AT,
        )
    )

    assert result.completed is False
    assert result.abandonment is not None
    assert result.abandonment.seat == 0
    assert result.abandonment.model == MODEL

    god = GameLogReader(god_log_path(directory, result.game_id)).read()
    assert god.terminal is None, "an abandonment never gets a synthetic verdict"
    assert verify(god, get_game("fixture")).completed is False


def test_a_seat_without_an_agent_is_refused() -> None:
    with pytest.raises(ManifestError, match="seat 1"):
        manifest_for({0: llm()})


def test_a_seat_the_game_does_not_have_is_refused() -> None:
    with pytest.raises(ManifestError, match="seat 2"):
        manifest_for(
            {
                0: llm(),
                1: ReferenceAgent(SpendFirst()),
                2: ScriptedAgent([Action(player=2, type="take", params={})]),
            }
        )


# --- the manifest is the run's declaration (FR-10.1) --------------------------------------------


def test_the_manifest_records_the_design_it_was_given() -> None:
    """The runner records the experiment's declaration; it never invents one from a game option."""
    design = GameDesign(
        seating="rotated",
        initial_configuration="fixed:standard_a",
        configuration_scope="per_game",
        replicates=5,
        uncontrolled=("initial_configuration",),
        derivation={
            "rule": "games = replicates x seatings",
            "replicates": 5,
            "seatings": 2,
            "games": 10,
        },
    )

    manifest = manifest_for(
        {0: llm(), 1: ReferenceAgent(SpendFirst())},
        design=design,
        options={"board": "fixed:mystery"},
    )

    assert manifest["design"] == design.to_mapping()
    assert manifest["config"]["board"] == "fixed:mystery", "game options are carried, not read"
    assert validate_manifest(manifest) == []


def test_the_manifest_records_every_policy_and_hash() -> None:
    """FR-10.1: config, seats, policies, prompt hashes, provider identity and the price table."""
    manifest = manifest_for({0: llm(), 1: ReferenceAgent(SpendFirst())})

    assert manifest["run_id"] == RUN_ID
    assert manifest["game"] == {
        "name": "fixture",
        "rules_version": "fixture-rules-1",
        "schema_version": "fixture-actions-1",
    }
    assert manifest["config"]["players"] == 2
    assert manifest["policies"] == {
        "context": "delta_with_refresh",
        "context_refresh_every": 10,
        "context_window": 3,
        "redo_budget": TurnPolicy().redo_budget,
        "on_exhausted": "abandon_game",
        "step_budget": TurnPolicy().step_budget,
        "decision_timeout_s": int(TurnPolicy().decision_timeout_s),
        "game_timeout_s": 7200,
        "budget_micro_usd": None,
    }
    assert manifest["prompts"] == memory_prompts().hashes()
    assert manifest["price_table"]["read_at"] == AT
    assert validate_manifest(manifest) == []


def test_the_agent_kinds_are_the_declared_ones() -> None:
    """The kinds live beside the seat record whose vocabulary they fill."""
    assert [kind.value for kind in AgentKind] == ["llm", "reference", "scripted"]
