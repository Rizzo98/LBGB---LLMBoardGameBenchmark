"""The invariants the plugin declares (PRD-v1 FR-6.9; kanban card K-061).

A game tells the platform what must always be true of it, so that one generic harness can check
any game - including games that do not exist yet. For Catan that is two conservation laws, and
they are checked here in the three ways that matter: that they hold in every position of the
recorded corpus, that they survive random play, and that the checker actually bites when a
position is broken by hand.
"""

from __future__ import annotations

import inspect
import random
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import Game, get_game
from lgbg.core.log import GameLogReader
from lgbg.core.replay import replay
from lgbg.core.run import GameRun
from lgbg.games.catan.state import BANK_PER_RESOURCE

GAME: Final[Any] = get_game("catan")
SEATS: Final[int] = 4
SEEDS: Final[tuple[int, ...]] = (20260801, 20260802)
MAX_ACTIONS: Final[int] = 400


def _corpus() -> list[Any]:
    root = Path(__file__).resolve().parents[1] / "golden" / "catan"
    states: list[Any] = []
    for path in sorted(root.glob("*.god.jsonl")):
        states.extend(replay(GameLogReader(path).read(), GAME).states)
    return states


def test_the_invariants_hold_in_every_recorded_position() -> None:
    """Both laws, over five games: 19 of each resource, and every piece accounted for."""
    states = _corpus()

    assert len(states) > 1000, "the corpus is the evidence, so it has to be read"
    for state in states:
        assert GAME.check_invariants(state) == [], state.turn


def test_the_invariants_hold_after_every_action_of_a_fuzzed_game() -> None:
    """FR-6.9 in the hands of a driver: the laws hold under play nobody planned."""
    for seed in SEEDS:
        chooser = random.Random(seed)
        config = RunConfig(
            seed=seed,
            players=SEATS,
            interaction_protocol="decline_only",
            game_config=GameConfig({"board": "fixed:standard_a"}),
        )
        run = GameRun(GAME, config, game_id="g-invariants")
        for _ in range(MAX_ACTIONS):
            if GAME.is_terminal(run.state):
                break
            offered = [
                action
                for request in run.pending
                for action in GAME.legal_actions(run.state, request.player)
            ]
            run.submit(chooser.choice(offered))
            assert GAME.check_invariants(run.state) == [], f"seed {seed}"


def test_the_checker_bites_when_a_position_is_broken_by_hand() -> None:
    """The control: an invariant nothing can violate is one nothing checks."""
    state = _corpus()[-1]
    hands = list(state.hands)
    hands[0] = tuple(count + 1 for count in hands[0])
    richer = replace(state, hands=tuple(hands))
    found = GAME.check_invariants(richer)

    assert sorted({violation.invariant for violation in found}) == ["resource_conservation"]
    assert str(BANK_PER_RESOURCE) in found[0].detail

    supply = (replace(state.supply[0], roads=state.supply[0].roads + 1), *state.supply[1:])
    lost = GAME.check_invariants(replace(state, supply=supply))

    assert sorted({violation.invariant for violation in lost}) == ["piece_conservation"]


def test_the_checker_is_declared_by_the_plugin_and_is_pure() -> None:
    """Declared rather than hardcoded (FR-6.9), and a reading rather than a step."""
    state = _corpus()[7]
    before = to_canonical_json(GAME.encode_state(state))

    assert hasattr(Game, "check_invariants")
    assert list(inspect.signature(Game.check_invariants).parameters) == ["self", "state"]
    assert GAME.check_invariants(state) == GAME.check_invariants(state)
    assert to_canonical_json(GAME.encode_state(state)) == before, "checking changes nothing"
