"""The benchmark profile, audited against what the game does (FR-6.7, SC-13; card K-062).

The profile is the plugin's declaration of the facts the platform needs to design a valid
experiment: whether seat order matters, what an outcome looks like, how much variance there is,
and how long a game is. None of it can be inferred from code, so all of it is declared - and a
declaration nobody checks is a guess with a straight face. The numbers here are the estimate the
catan plugin ships, and this file holds them to measurements from the corpus and from fuzzed play;
the campaign that replaces the estimate with a measured distribution is K-067.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import InteractionCharacter, OutcomeShape, VarianceClass, get_game
from lgbg.core.log import GameLogReader
from lgbg.core.rng import SeededRandomSource
from lgbg.core.run import GameRun

GAME: Final[Any] = get_game("catan")
SEEDS: Final[tuple[int, ...]] = (20260901, 20260902, 20260903)
MAX_ACTIONS: Final[int] = 4000
TOLERANCE: Final[int] = 4
"""How far the declared typical length may sit from the measured median, as a factor."""


def _corpus_lengths() -> list[int]:
    root = Path(__file__).resolve().parents[1] / "golden" / "catan"
    return [len(GameLogReader(path).read().actions) for path in sorted(root.glob("*.god.jsonl"))]


def _fuzzed_lengths(seeds: tuple[int, ...] = SEEDS) -> list[int]:
    lengths: list[int] = []
    for seed in seeds:
        chooser = random.Random(seed)
        config = RunConfig(
            seed=seed,
            players=4,
            interaction_protocol="decline_only",
            game_config=GameConfig({"board": "fixed:standard_a"}),
        )
        run = GameRun(GAME, config, game_id="g-profile")
        for _ in range(MAX_ACTIONS):
            if GAME.is_terminal(run.state):
                break
            offered = [
                action
                for request in run.pending
                for action in GAME.legal_actions(run.state, request.player)
            ]
            run.submit(chooser.choice(offered))
        lengths.append(run.actions)
    return lengths


def test_the_profile_is_complete_and_says_what_catan_is() -> None:
    """FR-6.7: every field declared, and the three enums saying something true."""
    profile = GAME.benchmark_profile()

    assert profile.positional_asymmetry is True, "seat order is a real advantage in Catan"
    assert profile.configuration_is_variable is True, "Catan deals a different board every game"
    assert profile.outcome_shape is OutcomeShape.SINGLE_WINNER
    assert profile.variance_class is VarianceClass.HIGH
    assert profile.interaction_character is InteractionCharacter.MIXED
    assert profile.typical_decisions > 0
    assert profile.worst_case_decisions >= profile.typical_decisions


def test_the_seat_order_advantage_is_structural_rather_than_claimed() -> None:
    """The draft runs in seat order: unmirrored pairings would flatter seat 0."""
    state = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": 4}),
        SeededRandomSource(20260901),
    )
    first = GAME.pending_decisions(state)[0]

    assert first.player == 0, "the first pick goes to seat 0 and to nobody else"
    assert GAME.legal_actions(state, 1) == []
    assert GAME.legal_actions(state, 0), "and seat 0 has somewhere to put it"


def test_the_declared_length_distribution_holds_for_games_that_end() -> None:
    """The audit: the estimate has to bracket the games the corpus actually played."""
    profile = GAME.benchmark_profile()
    measured = sorted(_corpus_lengths())
    median = measured[len(measured) // 2]

    assert len(measured) >= 5, "the five recorded games"
    assert measured[-1] <= profile.worst_case_decisions, (
        f"a game of {measured[-1]} actions exceeds the declared worst case"
    )
    assert median <= profile.typical_decisions * TOLERANCE, (
        f"a median of {median} against a declared typical of {profile.typical_decisions}"
    )
    assert profile.typical_decisions <= median * TOLERANCE


def test_a_random_driver_wanders_past_the_declared_worst_case() -> None:
    """What this audit found, asserted rather than left for the harness to discover.

    The declared worst case is a statement about play that *ends*. A uniform-random driver makes
    pointless trades and wanders - one of the three seeds here played the cap of 4000 actions
    without finishing - so the fuzz harness has to report a game that will not end as a livelock,
    distinctly from a rule failure, which is what its card asks of it (K-064).
    """
    # One seed is enough to show it, and 4000 actions is not cheap: the corpus audit above is
    # the card's evidence, and this is the finding it turned up.
    lengths = _fuzzed_lengths((SEEDS[0],))

    assert lengths == [MAX_ACTIONS], "the cap is what stopped it, not a win"
