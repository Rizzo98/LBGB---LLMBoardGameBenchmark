"""Upgrading a settlement to a city (PRD-v1 FR-11.6; RULES.md 4.7, "Cities").

A city is not built; it is *created* out of a settlement that is already on the board. RULES.md
is emphatic about the consequence: a city may never be placed on an empty vertex, for any price.
The tests below hold that line by asking from three directions - an empty vertex, an opponent's
settlement, and a settlement of the player's own - and then check the two things a city is for:
it produces twice as much, and it is worth twice as many points.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, ReplayRandomSource, RngDraw, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import (
    NO_PIECES_REMAINING,
    NOT_ENOUGH_RESOURCES,
    NOT_YOUR_SETTLEMENT,
)
from lgbg.games.catan.rules.building import CITY, can_build_city, city_targets
from lgbg.games.catan.rules.production import DICE_DIE_1, DICE_DIE_2
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState, Phase
from tests.games.catan_boards import at_distance, hand, holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251103
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}
A_CITY: Final[dict[str, int]] = {"wheat": 2, "ore": 3}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _token_hex(state: CatanState, total: int) -> int:
    return next(
        hex_.id for hex_ in state.board.topology.hexes if state.board.tokens[hex_.id] == total
    )


def _ready(state: CatanState, vertex: int, seat: int = 0) -> CatanState:
    """A position where this seat has a settlement on the vertex and exactly a city in hand."""
    return holding(layout(state, settlements=[(vertex, seat)]), seat, **A_CITY)


def _build(state: CatanState, vertex: Any, seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(player=seat, type=phases.BUILD_CITY, params={"vertex": vertex}),
        NullRandomSource(),
    )


def _refusal(state: CatanState, vertex: Any, seat: int = 0) -> Rejection:
    result = _build(state, vertex, seat)
    assert isinstance(result, Rejected), "an illegal city must be refused"
    return result.rejection


def test_a_settlement_is_upgraded_where_it_stands() -> None:
    """FR-11.6: the vertex does not change, and the settlement goes back to its owner's supply."""
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    ready = _ready(state, vertex)

    built = _build(ready, vertex)

    assert isinstance(built, Applied)
    assert built.state.placed.cities[vertex] == 0
    assert built.state.placed.settlements[vertex] == -1, "the settlement is no longer on the board"
    assert built.state.supply[0] == replace(ready.supply[0], cities=3, settlements=5)
    assert built.state.hands[0] == hand()
    assert [event.type for event in built.events] == [
        "resources_spent",
        "city_built",
        "piece_taken",
        "piece_returned",
    ]
    assert GAME.victory_points(built.state, 0) == 2, "a city is worth two points, not three"
    assert GAME.check_invariants(built.state) == []


def test_a_city_is_never_placed_on_an_empty_vertex() -> None:
    """RULES.md 4.7: not for any price, which is what an upgrade-only rule means."""
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    ready = holding(layout(state), 0, **A_CITY)

    refusal = _refusal(ready, vertex)

    assert refusal.code == NOT_YOUR_SETTLEMENT
    assert dict(refusal.details)["vertex"] == vertex
    assert ready.placed.cities[vertex] == -1


def test_an_opponents_settlement_cannot_be_upgraded() -> None:
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    ready = _ready(state, vertex, seat=2)

    refusal = _refusal(ready, vertex)

    assert refusal.code == NOT_YOUR_SETTLEMENT
    assert dict(refusal.details)["owner"] == 2


def test_a_player_out_of_cities_cannot_build_one_and_is_not_offered_one() -> None:
    """FR-11.6 with the four-city limit: the piece is the limit, and it is not a counter.

    The fixture lays out what the supply has to account for - three cities standing and two
    settlements to upgrade - on vertices far enough from the target to leave it playable, so the
    fourth city is built against a supply that genuinely holds one.
    """
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    far = sorted(at_distance(state, vertex, 3))
    second = far[1]
    ready = holding(
        layout(
            state,
            settlements=[(vertex, 0), (second, 0)],
            cities=[(site, 0) for site in far[2:5]],
        ),
        0,
        **A_CITY,
    )
    assert ready.supply[0].cities == 1, "the fixture must leave exactly one city in supply"

    built = _build(ready, vertex)

    assert isinstance(built, Applied)
    assert built.state.supply[0].cities == 0
    assert can_build_city(built.state, 0) is False
    assert city_targets(built.state, 0) == (second,), "the other settlement is still a target"
    assert _refusal(built.state, second).code == NO_PIECES_REMAINING


def test_a_player_who_cannot_afford_a_city_loses_nothing() -> None:
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    ready = layout(state, settlements=[(vertex, 0)])

    refusal = _refusal(ready, vertex)

    assert refusal.code == NOT_ENOUGH_RESOURCES
    assert dict(refusal.details)["build"] == CITY
    assert dict(refusal.details)["missing"] == A_CITY
    assert ready.placed.cities[vertex] == -1
    assert ready.placed.settlements[vertex] == 0, "the settlement is still standing"
    assert can_build_city(ready, 0) is False


def test_a_city_is_not_built_out_of_turn_or_out_of_phase() -> None:
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    ready = _ready(state, vertex)

    elsewhere = _refusal(replace(ready, phase=Phase.TURN_PRODUCTION), vertex)
    other_seat = _refusal(ready, vertex, seat=1)

    assert elsewhere.code == WRONG_PHASE
    assert other_seat.code == NOT_YOUR_DECISION


@pytest.mark.parametrize("vertex", [54, -1, "two", None])
def test_a_vertex_that_is_not_on_the_board_is_a_parameter_error(vertex: Any) -> None:
    state = _opening()
    target = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    ready = _ready(state, target)

    refusal = _refusal(ready, vertex)

    assert refusal.code == BAD_PARAMS


def test_a_city_produces_twice_what_a_settlement_produced() -> None:
    """FR-11.6: two cards per adjacent hex whose number is rolled."""
    state = _opening()
    hex_id = _token_hex(state, 5)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    built = _build(_ready(state, vertex), vertex)
    assert isinstance(built, Applied)

    paid = GAME.apply(
        replace(built.state, phase=Phase.TURN_PRODUCTION, dice=None, turn=0),
        Action(player=0, type="roll_dice", params={}),
        ReplayRandomSource(
            [
                RngDraw(purpose=DICE_DIE_1, kind="randint", args={"lo": 1, "hi": 6}, value=2),
                RngDraw(purpose=DICE_DIE_2, kind="randint", args={"lo": 1, "hi": 6}, value=3),
            ],
            action="roll_dice",
        ),
    )

    assert isinstance(paid, Applied)
    resource = state.board.resource_of_hex(hex_id)
    assert resource is not None
    assert paid.state.hands[0][SLOT[resource.value]] == 2
    assert GAME.victory_points(paid.state, 0) == 2


def test_only_the_settlements_that_can_be_upgraded_are_offered() -> None:
    """FR-17.5, for this action: the offered set is the settlements the player owns."""
    state = _opening()
    first = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    second = state.board.topology.vertices_of_hex(_token_hex(state, 6))[0]
    ready = holding(layout(state, settlements=[(first, 0), (second, 1)]), 0, **A_CITY)

    offered = [
        dict(action.params)["vertex"]
        for action in GAME.legal_actions(ready, 0)
        if action.type == phases.BUILD_CITY
    ]

    assert offered == [first] == list(city_targets(ready, 0))
    for site in offered:
        assert isinstance(_build(ready, site), Applied)
    assert _refusal(ready, second).code == NOT_YOUR_SETTLEMENT


def test_the_action_phase_offers_a_city_only_when_it_can_be_taken() -> None:
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    ready = _ready(state, vertex)
    poor = layout(state, settlements=[(vertex, 0)])

    assert phases.BUILD_CITY in [
        str(name) for name in GAME.pending_decisions(ready)[0].context["actions"]
    ]
    assert phases.BUILD_CITY not in [
        str(name) for name in GAME.pending_decisions(poor)[0].context["actions"]
    ]
