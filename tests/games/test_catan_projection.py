"""What a player can see, and what they cannot (PRD-v1 FR-16.5, FR-16.7).

A projection is built from an **allow-list**: the observation is assembled by walking a
declared list of fields, so a field added to the state does not appear in anyone's view until
somebody adds it deliberately. A deny-list would fail open in exactly the case that matters -
the day state grows - and the leak it would cause is silent.

Two projections exist from the start, because they are different artefacts: a player's view
and the spectator's. In a game with hidden information, "who is ahead" is not determinable
from any player's view, so analysis and replays use the spectator's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.canonical import to_canonical_json
from lgbg.core.rng import NullRandomSource, RandomSource, SeededRandomSource
from lgbg.core.types import JsonValue
from lgbg.games.catan.board.generation import load_board
from lgbg.games.catan.projection import (
    PLAYER_OBSERVATION_FIELDS,
    SPECTATOR_OBSERVATION_FIELDS,
    observe,
    observe_spectator,
)
from lgbg.games.catan.state import (
    NO_OWNER,
    CatanState,
    Placed,
    encode_state,
    initial_state,
)

PLAYERS: Final[int] = 4


def _opening() -> CatanState:
    return initial_state(load_board("standard_a"), players=PLAYERS, rng=SeededRandomSource(7))


def _played_state() -> CatanState:
    """An opening state with a settlement, a city and a road already on the board."""
    state = _opening()
    settlements = [NO_OWNER] * len(state.board.topology.vertices)
    cities = [NO_OWNER] * len(state.board.topology.vertices)
    roads = [NO_OWNER] * len(state.board.topology.edges)
    settlements[4] = 0
    settlements[11] = 2
    cities[4] = 0
    roads[17] = 3
    return replace(
        state,
        placed=Placed(settlements=tuple(settlements), cities=tuple(cities), roads=tuple(roads)),
    )


def test_a_player_sees_the_board_the_robber_and_every_players_pieces() -> None:
    observation = observe(_played_state(), 0)

    assert observation["robber"] == _played_state().board.desert_hex
    pieces = observation["pieces"]
    assert isinstance(pieces, dict)
    assert pieces["settlements"] == [[4, 0], [11, 2]]
    assert pieces["cities"] == [[4, 0]]
    assert pieces["roads"] == [[17, 3]]
    board = observation["board"]
    assert isinstance(board, dict)
    assert len(board["hexes"]) == len(_played_state().board.topology.hexes)
    assert len(board["ports"]) == 9


def test_the_board_carries_its_terrain_and_its_tokens() -> None:
    state = _played_state()
    board = observe(state, 0)["board"]

    assert isinstance(board, dict)
    hexes = board["hexes"]
    assert isinstance(hexes, list)
    assert [hex_["terrain"] for hex_ in hexes] == [terrain.value for terrain in state.board.terrain]
    assert [hex_["token"] for hex_ in hexes] == list(state.board.tokens)
    assert [hex_["id"] for hex_ in hexes] == [hex_.id for hex_ in state.board.topology.hexes]


def test_the_observation_holds_exactly_the_allowed_fields() -> None:
    """FR-16.5: a field reaches a player because it was named, not because it existed."""
    for player in range(PLAYERS):
        assert set(observe(_played_state(), player)) == PLAYER_OBSERVATION_FIELDS


def test_every_player_sees_the_same_public_board() -> None:
    state = _played_state()

    views = [observe(state, player) for player in range(PLAYERS)]

    assert all(view == views[0] for view in views)


def test_the_spectator_projection_is_a_distinct_superset() -> None:
    """FR-16.7: the spectator view is its own artefact, not the player view by another name."""
    spectator = observe_spectator(_played_state())

    assert set(spectator) == SPECTATOR_OBSERVATION_FIELDS
    assert PLAYER_OBSERVATION_FIELDS < SPECTATOR_OBSERVATION_FIELDS


def test_the_hidden_information_is_absent_from_a_players_view() -> None:
    """Slice 2 shows no hand and no deck on purpose; slice 3 adds hands with their leak tests."""
    observation = observe(_played_state(), 0)

    for hidden in ("hands", "dev_cards", "dev_deck", "bought_this_turn"):
        assert hidden not in observation


def test_the_spectator_sees_the_deck_order_and_every_hand() -> None:
    state = _played_state()

    spectator = observe_spectator(state)

    assert spectator["dev_deck"] == list(state.dev_deck)
    assert spectator["hands"] == [list(hand) for hand in state.hands]


def _mapping(value: JsonValue, what: str) -> Mapping[str, JsonValue]:
    assert isinstance(value, Mapping), f"{what} is not a JSON object: {value!r}"
    return value


def test_the_allow_list_names_fields_the_state_actually_has() -> None:
    """A typo in the list would silently drop a field a model needs to play."""
    state_fields = set(_mapping(encode_state(_opening()), "state"))
    assert state_fields, "control: the encoding describes the state"

    named = PLAYER_OBSERVATION_FIELDS | SPECTATOR_OBSERVATION_FIELDS

    assert named, "the allow-list must not be empty"
    assert set(PLAYER_OBSERVATION_FIELDS) <= SPECTATOR_OBSERVATION_FIELDS


def test_observing_consumes_no_randomness_and_does_not_change_the_state() -> None:
    """FR-2.6: observe is pure, and it is not even handed a source of randomness."""
    state = _played_state()
    before = encode_state(state)

    first = observe(state, 1)
    second = observe(state, 1)

    assert first == second
    assert encode_state(state) == before
    quiet: RandomSource = NullRandomSource()
    assert quiet.draws() == []


def test_the_observation_serialises_canonically() -> None:
    """FR-16.8: the observation is a JSON value, so a schema can describe it later."""
    for player in range(PLAYERS):
        assert to_canonical_json(observe(_played_state(), player))
    assert to_canonical_json(observe_spectator(_played_state()))


def test_the_bank_is_public_and_the_hands_are_not() -> None:
    """The resource supply is on the table; a hand is behind a screen."""
    observation = observe(_played_state(), 2)

    bank = observation["bank"]
    assert isinstance(bank, dict)
    assert set(bank) == {"wood", "brick", "wool", "wheat", "ore"}
    assert all(count == 19 for count in bank.values())
    assert "hands" not in observation


def test_an_unknown_player_number_is_still_answered() -> None:
    """The projection takes the observer as a parameter (FR-16.5): a seat, not a flag."""
    observation = observe(_opening(), NO_OWNER)

    assert set(observation) == PLAYER_OBSERVATION_FIELDS


def test_the_projection_reports_the_turn_and_the_phase() -> None:
    observation = observe(_opening(), 0)

    assert observation["turn"] == 0
    assert observation["phase"] == "setup_round_1"
    assert observation["round"] == 0
    assert observation["dice"] is None


def test_the_projection_reports_the_awards_as_unheld_at_the_start() -> None:
    awards = observe(_opening(), 0)["awards"]

    assert isinstance(awards, dict)
    assert awards == {"largest_army": NO_OWNER, "longest_road": NO_OWNER}


@pytest.mark.parametrize("player", range(PLAYERS))
def test_a_projection_is_a_plain_json_value(player: int) -> None:
    observation: Any = observe(_played_state(), player)

    assert observe_spectator(_played_state())
    assert isinstance(to_canonical_json(observation), str)
