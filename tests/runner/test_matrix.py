"""The experiment-design matrix: what varies, where each game sits, and how many there are.

A run's comparability lives here. Seating and initial configuration are two independent axes, and a
design either varies an axis or records that it did not; the game count is a product of declared
choices rather than a number somebody typed. This module tests the matrix, not the playing: a plan
is a value, so most of these tests never touch a game at all, and the one that does plays a small
fixture experiment end to end and reads the point back out of every run directory.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest

import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.core.config import RunConfig
from lgbg.core.contracts import validate_manifest
from lgbg.core.game import (
    BenchmarkProfile,
    InteractionCharacter,
    OutcomeShape,
    VarianceClass,
)
from lgbg.core.types import Action
from lgbg.runner import (
    AXIS_INITIAL_CONFIGURATION,
    AXIS_SEATING,
    DERIVATION_RULE,
    DesignError,
    ExperimentDesign,
    ReferenceAgent,
    ReferenceView,
    ScriptedAgent,
    experiment_record,
    plan,
    run_experiment,
)

MODEL: Final[str] = "mock-model"
RUN_ID: Final[str] = "r-k028"
AT: Final[str] = "2026-02-11T09:30:00+00:00"

ASYMMETRIC: Final[BenchmarkProfile] = BenchmarkProfile(
    positional_asymmetry=True,
    configuration_is_variable=False,
    outcome_shape=OutcomeShape.SINGLE_WINNER,
    variance_class=VarianceClass.LOW,
    interaction_character=InteractionCharacter.ADVERSARIAL,
    typical_decisions=12,
    worst_case_decisions=60,
)
"""A game where seat order matters, which is the fact the seating axis exists for."""

VARIABLE: Final[BenchmarkProfile] = BenchmarkProfile(
    positional_asymmetry=True,
    configuration_is_variable=True,
    outcome_shape=OutcomeShape.SINGLE_WINNER,
    variance_class=VarianceClass.LOW,
    interaction_character=InteractionCharacter.ADVERSARIAL,
    typical_decisions=12,
    worst_case_decisions=60,
)
"""A game that can deal more than one opening position, so its configuration can vary."""

SYMMETRIC: Final[BenchmarkProfile] = BenchmarkProfile(
    positional_asymmetry=False,
    configuration_is_variable=False,
    outcome_shape=OutcomeShape.SINGLE_WINNER,
    variance_class=VarianceClass.LOW,
    interaction_character=InteractionCharacter.ADVERSARIAL,
    typical_decisions=12,
    worst_case_decisions=60,
)


def scripted(tag: str) -> ScriptedAgent:
    """A scripted agent tagged so two seats can be told apart in a plan."""
    return ScriptedAgent([Action(player=0, type="take", params={"tag": tag})])


@dataclass(frozen=True, slots=True)
class SpendWhenPossible:
    """A reference player that scores when it can and takes otherwise: legal and terminating."""

    name: str = "spender"

    def choose(self, view: ReferenceView) -> Action:
        offered = view.game.legal_actions(view.state, view.seat)
        spending = [action for action in offered if action.type == "spend"]
        return spending[0] if spending else offered[0]


def prompts(directory: Path) -> PromptSet:
    directory.mkdir(parents=True, exist_ok=True)
    game_prompt = directory / "game.md"
    game_prompt.write_text("The fixture game: take, gamble or spend.\n", encoding="utf-8")
    return PromptSet.load("fixture", game_prompt=game_prompt)


def price_table() -> PriceTable:
    return PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
    )


def config(*, players: int = 2, seed: int = 7) -> RunConfig:
    return RunConfig(seed=seed, players=players, interaction_protocol="fixture")


def four_seats() -> list[ScriptedAgent]:
    return [scripted(tag) for tag in ("a", "b", "c", "d")]


# --- the derivation (FR-11.4, SC-7) -------------------------------------------------------------


def test_five_replicates_of_a_four_seat_rotation_is_twenty_games() -> None:
    """SC-7: the count is the product, and the product is recorded, not only the result."""
    design = ExperimentDesign(seating="rotated", replicates=5)

    planned = plan(design=design, table=four_seats(), seed=11, profile=ASYMMETRIC)

    assert len(planned) == 20
    assert [game.design.replicate for game in planned] == [
        replicate for replicate in range(5) for _ in range(4)
    ]
    assert [game.design.rotation for game in planned] == [0, 1, 2, 3] * 5
    assert {tuple(sorted(game.design.derivation.items())) for game in planned} == {
        tuple(
            sorted({"rule": DERIVATION_RULE, "replicates": 5, "seatings": 4, "games": 20}.items())
        )
    }
    for position, agent in enumerate(planned[0].seats):
        for seat in range(4):
            assert sum(1 for game in planned if game.seats[seat] is agent) == 5, (
                f"table position {position} must occupy seat {seat} five times"
            )


def test_the_game_count_is_derived_from_the_axes() -> None:
    """FR-11.4: games = replicates x (rotated ? seats : 1), for all three seating rules."""
    rotated = ExperimentDesign(seating="rotated", replicates=5)
    fixed = ExperimentDesign(seating="fixed", replicates=5)
    random = ExperimentDesign(seating="random", replicates=5)

    assert rotated.game_count(4) == 20
    assert fixed.game_count(4) == 5
    assert random.game_count(4) == 5
    assert rotated.derivation(4) == {
        "rule": DERIVATION_RULE,
        "replicates": 5,
        "seatings": 4,
        "games": 20,
    }
    assert fixed.derivation(4) == {
        "rule": DERIVATION_RULE,
        "replicates": 5,
        "seatings": 1,
        "games": 5,
    }


# --- rotation (FR-11.9, SC-7) -------------------------------------------------------------------


def test_a_rotated_design_is_the_cyclic_shifts_of_the_table() -> None:
    table = four_seats()
    design = ExperimentDesign(seating="rotated", replicates=1)

    planned = plan(design=design, table=table, seed=3, profile=ASYMMETRIC)

    for rotation, game in enumerate(planned):
        expected = tuple(table[(seat + rotation) % len(table)] for seat in range(len(table)))
        assert game.seats == expected
        assert game.design.rotation == rotation


def test_rotation_balances_a_table_with_a_repeated_agent() -> None:
    """FR-11.9: an agent holding r seats occupies each seat index r times, with no special case."""
    first, second = scripted("a"), scripted("b")
    table = [first, second, first, second]
    design = ExperimentDesign(seating="rotated", replicates=2)

    planned = plan(design=design, table=table, seed=9, profile=ASYMMETRIC)

    for replicate in range(2):
        games = [game for game in planned if game.design.replicate == replicate]
        assert len(games) == 4
        for seat in range(4):
            occupants = [game.seats[seat] for game in games]
            assert occupants.count(first) == 2, "the repeated agent holds two seats"
            assert occupants.count(second) == 2


def test_a_random_seating_draws_one_permutation_per_replicate() -> None:
    table = four_seats()
    design = ExperimentDesign(seating="random", replicates=6)

    planned = plan(design=design, table=table, seed=5, profile=ASYMMETRIC)
    again = plan(design=design, table=table, seed=5, profile=ASYMMETRIC)

    assert len(planned) == 6
    assert all(game.design.rotation == 0 for game in planned)
    assignments = [tuple(map(id, game.seats)) for game in planned]
    assert assignments == [tuple(map(id, game.seats)) for game in again], (
        "the draw is deterministic"
    )
    assert all(sorted(seats) == sorted(map(id, table)) for seats in assignments)
    assert len(set(assignments)) > 1, "six replicates are not one seating drawn six times"


def test_a_fixed_seating_keeps_the_table_in_order() -> None:
    table = four_seats()
    design = ExperimentDesign(seating="fixed", replicates=3)

    planned = plan(design=design, table=table, seed=2, profile=ASYMMETRIC)

    assert [game.seats for game in planned] == [tuple(table)] * 3
    assert all(game.design.rotation == 0 for game in planned)


# --- seeds and configuration scope (FR-11.3) ----------------------------------------------------


def test_a_rotated_replicate_shares_one_seed_and_a_per_game_configuration_does_not() -> None:
    """Mirroring means the same seed and configuration across the rotations of one replicate."""
    table = four_seats()
    rotated = ExperimentDesign(seating="rotated", replicates=2)

    mirrored = plan(design=rotated, table=table, seed=5, profile=ASYMMETRIC)
    per_game = plan(
        design=ExperimentDesign(
            seating="rotated",
            replicates=2,
            initial_configuration="random",
            configuration_scope="per_game",
        ),
        table=table,
        seed=5,
        profile=VARIABLE,
    )
    per_experiment = plan(
        design=ExperimentDesign(
            seating="rotated",
            replicates=2,
            initial_configuration="random",
            configuration_scope="per_experiment",
        ),
        table=table,
        seed=5,
        profile=VARIABLE,
    )

    for replicate in range(2):
        assert len({game.seed for game in mirrored if game.design.replicate == replicate}) == 1
        assert (
            len({game.seed for game in per_experiment if game.design.replicate == replicate}) == 1
        )
        assert len({game.seed for game in per_game if game.design.replicate == replicate}) == 4
    assert {game.seed for game in per_game if game.design.replicate == 0}.isdisjoint(
        {game.seed for game in per_game if game.design.replicate == 1}
    )


def test_a_fixed_configuration_ignores_a_per_game_scope() -> None:
    """Scope answers where a *draw* happens; a fixed configuration draws nothing."""
    table = four_seats()
    design = ExperimentDesign(
        seating="rotated",
        replicates=1,
        initial_configuration="fixed:standard_a",
        configuration_scope="per_game",
    )

    planned = plan(design=design, table=table, seed=5, profile=ASYMMETRIC)

    assert len({game.seed for game in planned}) == 1
    assert {game.design.initial_configuration for game in planned} == {"fixed:standard_a"}


# --- configuration variability (FR-11.11) --------------------------------------------------------


def test_config_variability_a_fixed_start_rejects_a_random_draw() -> None:
    """A game with one starting position cannot be asked to draw another: that is an error."""
    with pytest.raises(DesignError, match="single fixed starting position"):
        plan(
            design=ExperimentDesign(seating="random", initial_configuration="random"),
            table=four_seats(),
            seed=5,
            profile=ASYMMETRIC,
        )


def test_config_variability_a_variable_game_accepts_a_random_draw() -> None:
    """The same request is the axis working as intended where the game can vary its start."""
    planned = plan(
        design=ExperimentDesign(seating="rotated", initial_configuration="random"),
        table=four_seats(),
        seed=5,
        profile=VARIABLE,
    )

    assert {game.design.initial_configuration for game in planned} == {"random"}


# --- the profile's declaration (FR-11.12, ARCHITECTURE 7.10) ------------------------------------


def test_a_pinned_configuration_of_a_variable_game_is_marked_uncontrolled() -> None:
    """A fixed start where the game could have varied it is a caveat the record must carry."""
    planned = plan(
        design=ExperimentDesign(seating="rotated", initial_configuration="fixed:standard_a"),
        table=four_seats(),
        seed=1,
        profile=VARIABLE,
    )

    assert planned[0].design.uncontrolled == (AXIS_INITIAL_CONFIGURATION,)


def test_a_random_configuration_of_a_variable_game_is_controlled() -> None:
    """Drawing the start is the axis being controlled, so there is nothing to mark."""
    planned = plan(
        design=ExperimentDesign(seating="rotated", initial_configuration="random"),
        table=four_seats(),
        seed=1,
        profile=VARIABLE,
    )

    assert planned[0].design.uncontrolled == ()


def test_a_game_without_configuration_variation_needs_no_configuration_marking() -> None:
    """The game has one starting position, so the axis is not a caveat: there is nothing to vary."""
    planned = plan(
        design=ExperimentDesign(seating="rotated", initial_configuration="fixed"),
        table=four_seats(),
        seed=1,
        profile=ASYMMETRIC,
    )

    assert planned[0].design.uncontrolled == ()


def test_both_axes_can_be_uncontrolled_at_once() -> None:
    """The marks are independent, and the record names both in the declared axis order."""
    planned = plan(
        design=ExperimentDesign(seating="fixed", initial_configuration="fixed:standard_a"),
        table=four_seats(),
        seed=1,
        profile=VARIABLE,
    )

    assert planned[0].design.uncontrolled == (AXIS_INITIAL_CONFIGURATION, AXIS_SEATING)


def test_positional_asymmetry_marks_a_fixed_seating_uncontrolled() -> None:
    """A pinned seat order in a game that rewards moving first is a caveat the record must carry."""
    table = four_seats()
    fixed = ExperimentDesign(seating="fixed", replicates=1)
    rotated = ExperimentDesign(seating="rotated", replicates=1)

    assert plan(design=fixed, table=table, seed=1, profile=ASYMMETRIC)[0].design.uncontrolled == (
        "seating",
    )
    assert plan(design=fixed, table=table, seed=1, profile=SYMMETRIC)[0].design.uncontrolled == ()
    assert (
        plan(design=rotated, table=table, seed=1, profile=ASYMMETRIC)[0].design.uncontrolled == ()
    )


# --- the single-game default (FR-11.13) ---------------------------------------------------------


def test_one_game_default_uses_random_seats_and_a_random_configuration() -> None:
    """The exploration case is one game, with both axes drawn where the game can vary them."""
    design = ExperimentDesign.exploration(VARIABLE)

    planned = plan(design=design, table=four_seats(), seed=5, profile=VARIABLE)

    assert (design.seating, design.initial_configuration, design.replicates) == (
        "random",
        "random",
        1,
    )
    assert len(planned) == 1
    assert planned[0].design.uncontrolled == ()


def test_one_game_default_does_not_ask_a_fixed_game_for_a_start_it_cannot_draw() -> None:
    """A game with one opening position explores at that position rather than failing."""
    design = ExperimentDesign.exploration(ASYMMETRIC)

    planned = plan(design=design, table=four_seats(), seed=5, profile=ASYMMETRIC)

    assert (design.seating, design.initial_configuration, design.replicates) == (
        "random",
        "fixed",
        1,
    )
    assert len(planned) == 1
    assert planned[0].design.uncontrolled == ()


def test_one_game_default_is_what_an_undeclared_experiment_plays(tmp_path: Path) -> None:
    """FR-11.13: a caller who declares no design gets exactly one exploration game."""
    table = [
        ReferenceAgent(SpendWhenPossible("alpha")),
        ReferenceAgent(SpendWhenPossible("beta")),
    ]

    result = asyncio.run(
        run_experiment(
            game="fixture",
            config=config(),
            root=tmp_path / "run",
            run_id=RUN_ID,
            seats=table,
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(),
            clock=lambda: AT,
        )
    )

    assert len(result.games) == 1
    manifest: dict[str, Any] = json.loads(result.games[0].manifest_path.read_text(encoding="utf-8"))
    assert manifest["design"]["seating"] == "random"
    assert manifest["design"]["initial_configuration"] == "fixed"
    assert manifest["design"]["replicates"] == 1
    assert manifest["design"]["replicate"] == 0
    assert manifest["design"]["rotation"] == 0
    assert manifest["design"]["derivation"] == {
        "rule": DERIVATION_RULE,
        "replicates": 1,
        "seatings": 1,
        "games": 1,
    }


# --- the point each game occupies (FR-11.10, SC-7) ----------------------------------------------


def test_every_played_game_records_its_point_in_the_design(tmp_path: Path) -> None:
    """The record answers replicate, rotation, seat, seed and configuration without the plan."""
    table = [
        ReferenceAgent(SpendWhenPossible("alpha")),
        ReferenceAgent(SpendWhenPossible("beta")),
    ]
    design = ExperimentDesign(seating="rotated", replicates=2)

    result = asyncio.run(
        run_experiment(
            game="fixture",
            config=config(),
            root=tmp_path / "run",
            run_id=RUN_ID,
            seats=table,
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(),
            design=design,
            clock=lambda: AT,
        )
    )

    assert len(result.games) == 4
    assert all(game.completed for game in result.games)
    assert (result.completed, result.abandoned) == (4, 0)
    assert [game.game_id for game in result.games] == ["g-0000", "g-0001", "g-0002", "g-0003"]
    assert result.derivation == {
        "rule": DERIVATION_RULE,
        "replicates": 2,
        "seatings": 2,
        "games": 4,
    }

    seeds: list[int] = []
    for index, game in enumerate(result.games):
        manifest: dict[str, Any] = json.loads(game.manifest_path.read_text(encoding="utf-8"))
        assert validate_manifest(manifest) == []
        assert manifest["design"]["replicate"] == index // 2
        assert manifest["design"]["rotation"] == index % 2
        assert manifest["design"]["initial_configuration"] == "fixed"
        assert manifest["design"]["derivation"] == result.derivation
        assert [row["player"] for row in manifest["seats"]] == (
            ["alpha", "beta"] if index % 2 == 0 else ["beta", "alpha"]
        )
        seeds.append(int(manifest["config"]["seed"]))

    assert seeds[0] == seeds[1], "the rotations of one replicate are a mirrored pair"
    assert seeds[2] == seeds[3]
    assert len(set(seeds)) == 2


def test_the_table_must_fill_every_seat(tmp_path: Path) -> None:
    with pytest.raises(DesignError, match="3 agents"):
        asyncio.run(
            run_experiment(
                game="fixture",
                config=config(players=2),
                root=tmp_path / "run",
                run_id=RUN_ID,
                seats=[ReferenceAgent(SpendWhenPossible()) for _ in range(3)],
                prompts=prompts(tmp_path / "prompts"),
                price_table=price_table(),
                design=ExperimentDesign(),
                clock=lambda: AT,
            )
        )


def test_a_rotated_design_needs_at_least_two_seats() -> None:
    with pytest.raises(DesignError, match="two seats"):
        plan(
            design=ExperimentDesign(seating="rotated"),
            table=[scripted("a")],
            seed=1,
            profile=ASYMMETRIC,
        )


# --- the caveat travels into the results (FR-11.12) ----------------------------------------------


def test_uncontrolled_design_marked(tmp_path: Path) -> None:
    """A run that pins an axis says so in results.json, so the data carries its own caveat."""
    table = [
        ReferenceAgent(SpendWhenPossible("alpha")),
        ReferenceAgent(SpendWhenPossible("beta")),
    ]

    result = asyncio.run(
        run_experiment(
            game="fixture",
            config=config(),
            root=tmp_path / "run",
            run_id=RUN_ID,
            seats=table,
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(),
            design=ExperimentDesign(seating="fixed"),
            clock=lambda: AT,
        )
    )

    payload: dict[str, Any] = json.loads(result.results_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "lgbg.results.v1"
    assert payload["design"]["seating"] == "fixed"
    assert payload["design"]["uncontrolled"] == ["seating"]
    assert payload["games"] == {"planned": 1, "completed": 1, "abandoned": 0}


def test_results_carry_a_configuration_caveat() -> None:
    """The same record carries the other axis when the game could have varied its start."""
    record = experiment_record(
        run_id=RUN_ID,
        design=ExperimentDesign(seating="rotated", initial_configuration="fixed:standard_a"),
        profile=VARIABLE,
        seats=4,
        derivation={
            "rule": DERIVATION_RULE,
            "replicates": 1,
            "seatings": 4,
            "games": 4,
        },
        planned=4,
        completed=4,
        abandoned=0,
    )

    design_record = record["design"]
    assert isinstance(design_record, dict)
    assert design_record["initial_configuration"] == "fixed:standard_a"
    assert design_record["uncontrolled"] == ["initial_configuration"]
