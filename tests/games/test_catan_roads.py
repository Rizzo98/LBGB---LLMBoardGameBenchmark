"""Building roads (PRD-v1 FR-11.2, FR-11.3, FR-11.5; RULES.md 4.7).

A road is the cheapest thing in the game and the one that carries the most rules: it goes on an
empty edge, it extends the player's own network, and an opponent's building is never itself a
connection point - which is the rule that stops a road being built "on the other side of"
somebody else's settlement that happens to sit on the player's own line (RULES.md 4.7 items 2
and 3).

The supply is finite and it is the player's own: fifteen roads, and the sixteenth is not a
rejection to be discovered but an action that is not offered. The tests hold both halves of that:
can_build_road says no, and an attempt anyway says why.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.projection import observe
from lgbg.games.catan.rejections import (
    EDGE_OCCUPIED,
    NO_PIECES_REMAINING,
    NOT_CONNECTED,
    NOT_ENOUGH_RESOURCES,
)
from lgbg.games.catan.rules.building import ROAD, can_build_road, road_targets
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    NO_OWNER,
    RESOURCE_ORDER,
    CatanState,
    Phase,
    Placed,
    Supply,
)

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251020
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _hand(**counts: int) -> tuple[int, ...]:
    assert set(counts) <= set(SLOT), f"unknown resource in {sorted(counts)}"
    row = [0] * len(RESOURCE_ORDER)
    for name, count in counts.items():
        row[SLOT[name]] = count
    return tuple(row)


def _holding(state: CatanState, seat: int, **counts: int) -> CatanState:
    """Deal that hand out of the bank, so the position conserves cards like a real one."""
    hand = _hand(**counts)
    bank = tuple(cards - hand[index] for index, cards in enumerate(state.bank))
    assert min(bank) >= 0, "a hand cannot hold cards the bank does not have"
    hands = list(state.hands)
    hands[seat] = hand
    return replace(state, hands=tuple(tuple(row) for row in hands), bank=bank)


def _position(
    state: CatanState,
    *,
    roads: Sequence[tuple[int, int]] = (),
    settlements: Sequence[tuple[int, int]] = (),
    roads_in_supply: int | None = None,
) -> CatanState:
    """A board with pieces placed by hand, and every supply charged for what it put down.

    roads_in_supply, when given, is how many roads **seat 0** has left: the rest of that
    player's fifteen are laid out on free edges, so a position with an exhausted supply is still
    a position the rules could have produced rather than one that merely says so.
    """
    lines = [NO_OWNER] * len(state.placed.roads)
    sites = [NO_OWNER] * len(state.placed.settlements)
    for edge, seat in roads:
        lines[edge] = seat
    for vertex, seat in settlements:
        sites[vertex] = seat
    if roads_in_supply is not None:
        # The rest of seat 0's fifteen go somewhere that does not touch the roads already
        # placed, so the position under test keeps the target the test is about.
        ends = {
            vertex
            for edge, _seat in roads
            for vertex in state.board.topology.vertices_of_edge(edge)
        }
        spare = [
            edge
            for edge in range(len(lines))
            if lines[edge] == NO_OWNER
            and not ends & set(state.board.topology.vertices_of_edge(edge))
        ]
        mine = sum(1 for seat in lines if seat == 0)
        for edge in spare[: 15 - roads_in_supply - mine]:
            lines[edge] = 0
    supply = tuple(
        Supply(
            15 - sum(1 for seat in lines if seat == player),
            5 - sum(1 for seat in sites if seat == player),
            4,
        )
        for player in range(state.players)
    )
    return replace(
        state,
        placed=Placed(tuple(sites), state.placed.cities, tuple(lines)),
        supply=supply,
        phase=Phase.ACTION,
        turn=0,
    )


def _free_edge(state: CatanState, vertex: int) -> int:
    return next(
        edge
        for edge in state.board.topology.edges_at(vertex)
        if state.placed.roads[edge] == NO_OWNER
    )


def _build(state: CatanState, edge: Any, seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(player=seat, type=phases.BUILD_ROAD, params={"edge": edge}),
        NullRandomSource(),
    )


def _refusal(state: CatanState, edge: Any, seat: int = 0) -> Rejection:
    result = _build(state, edge, seat)
    assert isinstance(result, Rejected), "an illegal road must be refused"
    return result.rejection


def test_a_road_is_placed_on_an_empty_edge_of_the_network() -> None:
    """FR-11.2: the edge is empty, it extends the network, and the price is paid."""
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    ready = _holding(_position(state, roads=[(0, 0)]), 0, brick=2, wood=2)
    edge = _free_edge(ready, far)

    built = _build(ready, edge)

    assert isinstance(built, Applied)
    assert built.state.placed.roads[edge] == 0
    assert built.state.supply[0].roads == 13
    assert built.state.hands[0] == _hand(brick=1, wood=1)
    assert built.state.bank[SLOT["brick"]] == BANK_PER_RESOURCE - 1
    assert [event.type for event in built.events] == [
        "resources_spent",
        "road_built",
        "piece_taken",
    ]
    assert dict(built.events[1].payload) == {"player": 0, "edge": edge}
    assert GAME.check_invariants(built.state) == []
    assert near != far


def test_a_road_must_touch_the_players_own_network() -> None:
    """RULES.md 4.7 item 2: the edge must be incident to the player's own road or building."""
    state = _opening()
    ends = set(state.board.topology.vertices_of_edge(0))
    away = next(
        edge
        for edge in range(len(state.placed.roads))
        if not ends & set(state.board.topology.vertices_of_edge(edge))
    )
    ready = _holding(_position(state, roads=[(0, 0)]), 0, brick=2, wood=2)

    refusal = _refusal(ready, away)

    assert refusal.code == NOT_CONNECTED
    details = dict(refusal.details)
    assert details["edge"] == away
    assert details["network"] == sorted(ends), "both ends of the placed road are connection points"


def test_an_edge_that_already_carries_a_road_is_refused() -> None:
    state = _opening()
    ready = _holding(_position(state, roads=[(1, 1)]), 0, brick=2, wood=2)

    refusal = _refusal(ready, 1)

    assert refusal.code == EDGE_OCCUPIED
    assert dict(refusal.details)["owner"] == 1, "and the record says whose road it is"


def test_a_road_is_not_built_on_the_other_side_of_an_opponent_building() -> None:
    """RULES.md 4.7 item 3: an opponent's building is never itself a connection point."""
    state = _opening()
    blocked, open_end = state.board.topology.vertices_of_edge(0)
    ready = _holding(
        _position(state, roads=[(0, 0)], settlements=[(blocked, 1)]), 0, brick=2, wood=2
    )

    refusal = _refusal(ready, _free_edge(ready, blocked))

    assert refusal.code == NOT_CONNECTED
    assert dict(refusal.details)["network"] == [open_end], (
        "the blocked vertex carries this player's road and an opponent's settlement, and "
        "connects nothing further"
    )


def test_a_road_may_touch_an_opponent_building_at_its_far_end() -> None:
    """Item 3's other half: an edge is legal when the network reaches its *other* vertex."""
    state = _opening()
    theirs, mine = state.board.topology.vertices_of_edge(0)
    ready = _holding(
        _position(state, roads=[(0, 0)], settlements=[(theirs, 2)]), 0, brick=2, wood=2
    )

    built = _build(ready, _free_edge(ready, mine))

    assert isinstance(built, Applied)
    assert built.state.placed.roads[_free_edge(ready, mine)] == 0


def test_a_player_out_of_roads_cannot_build_one_and_is_not_offered_one() -> None:
    """FR-11.5: exhaustion makes the action unavailable rather than erroring."""
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    ready = _holding(_position(state, roads=[(0, 0)], roads_in_supply=0), 0, brick=2, wood=2)

    refusal = _refusal(ready, _free_edge(ready, far))

    assert refusal.code == NO_PIECES_REMAINING
    assert dict(refusal.details)["piece"] == ROAD
    assert can_build_road(ready, 0) is False
    assert ready.supply[0].roads == 0
    assert near != far


def test_the_last_road_in_supply_can_still_be_built() -> None:
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    ready = _holding(_position(state, roads=[(0, 0)], roads_in_supply=1), 0, brick=2, wood=2)

    built = _build(ready, _free_edge(ready, far))

    assert isinstance(built, Applied)
    assert built.state.supply[0].roads == 0
    assert can_build_road(built.state, 0) is False, "and now there is nothing to build with"
    assert GAME.check_invariants(built.state) == []
    assert near != far


def test_a_player_who_cannot_afford_a_road_loses_nothing() -> None:
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    ready = _position(state, roads=[(0, 0)])
    edge = _free_edge(ready, far)

    refusal = _refusal(ready, edge)

    assert refusal.code == NOT_ENOUGH_RESOURCES
    assert dict(refusal.details)["build"] == ROAD
    assert ready.hands[0] == (0,) * len(RESOURCE_ORDER)
    assert ready.placed.roads[edge] == NO_OWNER
    assert can_build_road(ready, 0) is False
    assert near != far


def test_a_road_is_not_built_out_of_turn_or_out_of_phase() -> None:
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    ready = _holding(_position(state, roads=[(0, 0)]), 0, brick=2, wood=2)

    elsewhere = _refusal(replace(ready, phase=Phase.TURN_PRODUCTION), _free_edge(ready, far))
    other_seat = _refusal(ready, _free_edge(ready, far), seat=1)

    assert elsewhere.code == WRONG_PHASE
    assert other_seat.code == NOT_YOUR_DECISION
    assert near != far


@pytest.mark.parametrize("edge", [72, -1, "three", None])
def test_an_edge_that_is_not_on_the_board_is_a_parameter_error(edge: Any) -> None:
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    ready = _holding(_position(state, roads=[(0, 0)]), 0, brick=2, wood=2)

    refusal = _refusal(ready, edge)

    assert refusal.code == BAD_PARAMS
    assert near != far


def test_a_road_is_worth_nothing_and_is_public() -> None:
    """FR-11.3: a road earns no victory points, and everybody can see it."""
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    ready = _holding(_position(state, roads=[(0, 0)]), 0, brick=2, wood=2)
    edge = _free_edge(ready, far)

    built = _build(ready, edge)

    assert isinstance(built, Applied)
    assert GAME.victory_points(built.state, 0) == 0
    pieces = observe(built.state, 3)["pieces"]
    assert isinstance(pieces, dict)
    assert [edge, 0] in pieces["roads"]
    assert near != far


def test_only_the_roads_that_can_be_built_are_offered() -> None:
    """FR-17.5, for this action: what is offered is exactly what the rule accepts."""
    state = _opening()
    ready = _holding(_position(state, roads=[(0, 0)]), 0, brick=2, wood=2)

    offered = [
        dict(action.params)["edge"]
        for action in GAME.legal_actions(ready, 0)
        if action.type == phases.BUILD_ROAD
    ]

    assert offered == list(road_targets(ready, 0))
    assert offered, "the fixture must offer something"
    for edge in offered:
        assert isinstance(_build(ready, edge), Applied)
    taken = next(
        edge for edge in range(len(ready.placed.roads)) if ready.placed.roads[edge] != NO_OWNER
    )
    assert _refusal(ready, taken).code == EDGE_OCCUPIED, (
        "and an edge that is not offered is refused"
    )


def test_the_action_phase_offers_a_road_only_when_it_can_be_taken() -> None:
    """FR-11.5 from the other side: the request says which actions it offers."""
    state = _opening()
    near, far = state.board.topology.vertices_of_edge(0)
    rich = _holding(_position(state, roads=[(0, 0)]), 0, brick=1, wood=1)
    poor = _position(state, roads=[(0, 0)])

    assert dict(GAME.pending_decisions(rich)[0].context)["actions"] == [
        phases.BUILD_ROAD,
        phases.END_TURN,
    ]
    assert dict(GAME.pending_decisions(poor)[0].context)["actions"] == [phases.END_TURN]
    built = [
        dict(action.params)["edge"]
        for action in GAME.legal_actions(rich, 0)
        if action.type == phases.BUILD_ROAD
    ]
    assert _free_edge(rich, far) in built
    assert near != far
