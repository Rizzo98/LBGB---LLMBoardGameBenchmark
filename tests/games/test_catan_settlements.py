"""Building settlements (PRD-v1 FR-11.4; RULES.md 4.7, "Settlements").

Three rules decide where a settlement may go, and each is a question about a different
neighbourhood: is this vertex empty, is every vertex one edge away free of buildings of any
colour, and does the player's own network reach it. The distance rule is the one implementations
get wrong by measuring the wrong distance, so its boundary is tested from both sides - one edge
away is refused, two and three are not.

The fixtures are shared with the road tests (tests/games/catan_boards.py), and they charge for
what they place, so a conservation assertion on a result means something.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    NOT_CONNECTED,
    NOT_ENOUGH_RESOURCES,
    TOO_CLOSE,
    VERTEX_OCCUPIED,
)
from lgbg.games.catan.rules.building import SETTLEMENT, can_build_settlement, settlement_targets
from lgbg.games.catan.rules.production import DICE_DIE_1, DICE_DIE_2
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState, Phase
from tests.games.catan_boards import (
    at_distance,
    free_edge,
    hand,
    holding,
    layout,
    vertices_of,
)

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251027
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}
A_SETTLEMENT: Final[dict[str, int]] = {"brick": 1, "wood": 1, "wool": 1, "wheat": 1}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _a_vertex(state: CatanState) -> int:
    """A vertex of the hex that shows five, so a built settlement has something to produce."""
    hex_id = next(
        hex_.id for hex_ in state.board.topology.hexes if state.board.tokens[hex_.id] == 5
    )
    return state.board.topology.vertices_of_hex(hex_id)[0]


def _ready(
    state: CatanState,
    vertex: int,
    *,
    settlements: Sequence[tuple[int, int]] = (),
    cities: Sequence[tuple[int, int]] = (),
    roads: Sequence[tuple[int, int]] = (),
) -> CatanState:
    """A position where seat 0 has a road into this vertex and holds exactly a settlement."""
    edge = free_edge(state, vertex)
    board = layout(state, roads=[(edge, 0), *roads], settlements=settlements, cities=cities)
    return holding(board, 0, **A_SETTLEMENT)


def _connected_elsewhere(state: CatanState, vertex: int) -> CatanState:
    """Seat 0 has the price in hand, but its roads are somewhere that does not reach here."""
    elsewhere = next(
        edge
        for edge in range(len(state.placed.roads))
        if vertex not in vertices_of(state, edge)
        and all(
            vertex not in vertices_of(state, other)
            for other in range(len(state.placed.roads))
            if other == edge
        )
    )
    return holding(layout(state, roads=[(elsewhere, 0)]), 0, **A_SETTLEMENT)


def _build(state: CatanState, vertex: Any, seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(player=seat, type=phases.BUILD_SETTLEMENT, params={"vertex": vertex}),
        NullRandomSource(),
    )


def _refusal(state: CatanState, vertex: Any, seat: int = 0) -> Rejection:
    result = _build(state, vertex, seat)
    assert isinstance(result, Rejected), "an illegal settlement must be refused"
    return result.rejection


def test_a_settlement_is_placed_on_an_empty_vertex_of_the_network() -> None:
    """FR-11.4: the vertex is empty, the network reaches it, and the price is paid."""
    state = _opening()
    vertex = _a_vertex(state)
    ready = _ready(state, vertex)

    built = _build(ready, vertex)

    assert isinstance(built, Applied)
    assert built.state.placed.settlements[vertex] == 0
    assert built.state.supply[0].settlements == 4
    assert built.state.hands[0] == hand(), "a settlement costs exactly this hand"
    assert [event.type for event in built.events] == [
        "resources_spent",
        "settlement_placed",
        "piece_taken",
    ]
    assert dict(built.events[1].payload)["vertex"] == vertex
    assert GAME.victory_points(built.state, 0) == 1
    assert GAME.check_invariants(built.state) == []


def test_the_distance_rule_refuses_a_vertex_one_edge_away() -> None:
    """RULES.md 4.7: none of the three neighbours may carry a building, of any colour."""
    state = _opening()
    vertex = _a_vertex(state)
    crowded = next(iter(sorted(at_distance(state, vertex, 1))))
    ready = _ready(state, vertex, settlements=[(crowded, 1)])

    refusal = _refusal(ready, vertex)

    assert refusal.code == TOO_CLOSE
    assert dict(refusal.details)["blocked_by"] == [crowded]


def test_the_distance_rule_refuses_the_players_own_building_too() -> None:
    """The rule says "the placing player's own included", which is easy to get wrong."""
    state = _opening()
    vertex = _a_vertex(state)
    mine = next(iter(sorted(at_distance(state, vertex, 1))))
    ready = _ready(state, vertex, settlements=[(mine, 0)])

    refusal = _refusal(ready, vertex)

    assert refusal.code == TOO_CLOSE
    assert dict(refusal.details)["blocked_by"] == [mine]


def test_a_city_one_edge_away_blocks_the_vertex_as_well() -> None:
    state = _opening()
    vertex = _a_vertex(state)
    upgraded = next(iter(sorted(at_distance(state, vertex, 1))))
    ready = _ready(state, vertex, cities=[(upgraded, 2)])

    refusal = _refusal(ready, vertex)

    assert refusal.code == TOO_CLOSE


def test_a_vertex_two_edges_away_is_far_enough() -> None:
    """The boundary the rule actually draws: two edges is the distance settlements keep."""
    state = _opening()
    vertex = _a_vertex(state)
    neighbour = next(iter(sorted(at_distance(state, vertex, 2))))
    ready = _ready(state, vertex, settlements=[(neighbour, 1)])

    built = _build(ready, vertex)

    assert isinstance(built, Applied)
    assert built.state.placed.settlements[vertex] == 0


def test_a_vertex_three_edges_away_is_far_enough() -> None:
    state = _opening()
    vertex = _a_vertex(state)
    distant = next(iter(sorted(at_distance(state, vertex, 3))))
    ready = _ready(state, vertex, settlements=[(distant, 1)])

    built = _build(ready, vertex)

    assert isinstance(built, Applied)


def test_a_vertex_that_already_carries_a_building_is_refused() -> None:
    state = _opening()
    vertex = _a_vertex(state)
    edge = free_edge(state, vertex)
    ready = holding(layout(state, roads=[(edge, 0)], cities=[(vertex, 3)]), 0, **A_SETTLEMENT)

    refusal = _refusal(ready, vertex)

    assert refusal.code == VERTEX_OCCUPIED
    assert dict(refusal.details) == {"vertex": vertex, "owner": 3}


def test_a_settlement_must_touch_the_players_own_network() -> None:
    """RULES.md 4.7 item 3: an edge of the player's own road must reach the vertex."""
    state = _opening()
    vertex = _a_vertex(state)
    away = _connected_elsewhere(state, vertex)

    refusal = _refusal(away, vertex)

    assert refusal.code == NOT_CONNECTED
    details = dict(refusal.details)
    network = details["network"]
    assert isinstance(network, list)
    assert details["vertex"] == vertex
    assert vertex not in network


def test_a_player_out_of_settlements_cannot_build_one_and_is_not_offered_one() -> None:
    """FR-11.5: five settlements is the limit, and the sixth is simply not on the table."""
    state = _opening()
    vertex = _a_vertex(state)
    elsewhere = sorted(at_distance(state, vertex, 3))[:4]
    assert len(elsewhere) == 4, "the fixture needs four vertices three edges away"
    ready = _ready(state, vertex, settlements=[(site, 0) for site in elsewhere])
    assert ready.supply[0].settlements == 1

    built = _build(ready, vertex)

    assert isinstance(built, Applied)
    assert built.state.supply[0].settlements == 0
    assert can_build_settlement(built.state, 0) is False
    assert settlement_targets(built.state, 0) == ()
    assert (
        _refusal(built.state, next(iter(sorted(at_distance(built.state, vertex, 2))))).code
        == NO_PIECES_REMAINING
    )


def test_a_player_who_cannot_afford_a_settlement_loses_nothing() -> None:
    state = _opening()
    vertex = _a_vertex(state)
    ready = layout(state, roads=[(free_edge(state, vertex), 0)])

    refusal = _refusal(ready, vertex)

    assert refusal.code == NOT_ENOUGH_RESOURCES
    assert dict(refusal.details)["build"] == SETTLEMENT
    assert dict(refusal.details)["missing"] == A_SETTLEMENT
    assert ready.placed.settlements[vertex] == -1
    assert ready.hands[0] == hand()
    assert can_build_settlement(ready, 0) is False


def test_a_settlement_is_not_built_out_of_turn_or_out_of_phase() -> None:
    state = _opening()
    vertex = _a_vertex(state)
    ready = _ready(state, vertex)

    elsewhere = _refusal(replace(ready, phase=Phase.TURN_PRODUCTION), vertex)
    other_seat = _refusal(ready, vertex, seat=2)

    assert elsewhere.code == WRONG_PHASE
    assert other_seat.code == NOT_YOUR_DECISION


@pytest.mark.parametrize("vertex", [54, -1, "four", None])
def test_a_vertex_that_is_not_on_the_board_is_a_parameter_error(vertex: Any) -> None:
    state = _opening()
    target = _a_vertex(state)
    ready = _ready(state, target)

    refusal = _refusal(ready, vertex)

    assert refusal.code == BAD_PARAMS


def test_a_settlement_produces_one_card_from_each_adjacent_hex() -> None:
    """FR-11.4: one victory point, and one card when the number beside it is rolled."""
    state = _opening()
    vertex = _a_vertex(state)
    ready = _ready(state, vertex)
    built = _build(ready, vertex)
    assert isinstance(built, Applied)
    rolled = replace(built.state, phase=Phase.TURN_PRODUCTION, dice=None, turn=0)

    paid = GAME.apply(
        rolled,
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
    resource = state.board.resource_of_hex(
        next(hex_.id for hex_ in state.board.topology.hexes if state.board.tokens[hex_.id] == 5)
    )
    assert resource is not None
    assert paid.state.hands[0][SLOT[resource.value]] == 1
    assert GAME.victory_points(paid.state, 0) == 1


def test_only_the_settlements_that_can_be_built_are_offered() -> None:
    """FR-17.5, for this action: what is offered is exactly what the rule accepts."""
    state = _opening()
    vertex = _a_vertex(state)
    ready = _ready(state, vertex)

    offered = [
        dict(action.params)["vertex"]
        for action in GAME.legal_actions(ready, 0)
        if action.type == phases.BUILD_SETTLEMENT
    ]

    assert offered == list(settlement_targets(ready, 0))
    assert vertex in offered, "the vertex the fixture prepared must be among them"
    for site in offered:
        assert isinstance(_build(ready, site), Applied)
    sample = [site for site in range(len(ready.placed.settlements)) if site not in offered][:8]
    assert sample, "the board must have vertices that are not on offer"
    for site in sample:
        assert isinstance(_build(ready, site), Rejected), (
            f"vertex {site} is not offered, so it must not be accepted either"
        )


def test_the_action_phase_offers_a_settlement_only_when_it_can_be_taken() -> None:
    """FR-11.5 from the other side: the request says which actions it offers."""
    state = _opening()
    vertex = _a_vertex(state)
    ready = _ready(state, vertex)
    poor = layout(state, roads=[(free_edge(state, vertex), 0)])

    assert phases.BUILD_SETTLEMENT in [
        str(name) for name in GAME.pending_decisions(ready)[0].context["actions"]
    ]
    assert phases.BUILD_SETTLEMENT not in [
        str(name) for name in GAME.pending_decisions(poor)[0].context["actions"]
    ]
