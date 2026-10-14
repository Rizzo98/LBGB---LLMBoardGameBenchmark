"""The starting endowment (PRD-v1 FR-8.4 as RULES.md 4.3 item 6 pins it).

The rule is one resource card from the bank **for each hex adjacent to the second
settlement**, of the type that hex produces. RULES.md records that the PRD's "one of each
resource" is shorthand (correction D-3): two forest hexes adjacent to one settlement grant two
wood, not one wood and one of everything else. The difference matters for balance - it is the
whole reason a player chooses a corner - so it is tested directly.

The other two things here are the ones a benchmark needs to be able to trust: the bank is
finite and conserved, and its exhaustion is a defined outcome rather than an accident.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.game import Applied, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan.board.generation import load_board
from lgbg.games.catan.board.layout import Board, Resource, Terrain
from lgbg.games.catan.rules.setup import neighbouring_vertices
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    NO_OWNER,
    PIECES_PER_PLAYER,
    RESOURCE_ORDER,
    CatanState,
    Phase,
    Placed,
    Supply,
    initial_state,
)

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20250501


def _opening(board: Board | None = None) -> CatanState:
    chosen = load_board("standard_a") if board is None else board
    return initial_state(chosen, players=PLAYERS, rng=SeededRandomSource(SEED))


def _in_round_two(state: CatanState, *, turn: int, keep_free: int | None = None) -> CatanState:
    """A state where round one is done, so the next settlement is everybody's second.

    The round-one pieces are placed legally - apart from each other and, if asked, clear of one
    vertex - so that a test can aim at a particular vertex without tripping the distance rule.
    """
    settlements = [NO_OWNER] * len(state.placed.settlements)
    roads = [NO_OWNER] * len(state.placed.roads)
    blocked = set() if keep_free is None else {keep_free, *neighbouring_vertices(state, keep_free)}
    placed = 0
    for vertex in range(len(settlements)):
        if placed >= state.players:
            break
        if vertex in blocked or any(
            site in blocked for site in neighbouring_vertices(state, vertex)
        ):
            continue
        if any(settlements[site] != NO_OWNER for site in neighbouring_vertices(state, vertex)):
            continue
        if state.board.terrain[vertex] is Terrain.DESERT:
            continue
        settlements[vertex] = placed
        roads[placed] = placed
        placed += 1
    assert placed == state.players, "the round-one pieces must fit"
    # Round one spent a road and a settlement from each supply, and the invariant notices.
    supply = tuple(Supply(*PIECES_PER_PLAYER) for _ in range(state.players))
    spent = tuple(
        Supply(roads=item.roads - 1, settlements=item.settlements - 1, cities=item.cities)
        for item in supply
    )
    return replace(
        state,
        supply=spent,
        placed=Placed(tuple(settlements), state.placed.cities, tuple(roads)),
        phase=Phase.SETUP_SETTLEMENT,
        setup_vertex=NO_OWNER,
        turn=turn,
    )


def _free_vertex(state: CatanState, *, touching: tuple[Terrain, ...] = ()) -> int:
    """A vertex the distance rule allows, optionally with chosen terrain around it."""
    for vertex in range(len(state.placed.settlements)):
        if state.placed.settlements[vertex] != NO_OWNER:
            continue
        if any(
            state.placed.settlements[site] != NO_OWNER
            for site in neighbouring_vertices(state, vertex)
        ):
            continue
        if touching:
            around = [
                state.board.terrain[hex_id] for hex_id in state.board.topology.hexes_at(vertex)
            ]
            if not all(terrain in around for terrain in touching):
                continue
        return vertex
    raise AssertionError("no vertex satisfies the request")


def _settle(state: CatanState, vertex: int, seat: int) -> Applied:
    result = GAME.apply(
        state,
        Action(player=seat, type="place_settlement", params={"vertex": vertex}),
        NullRandomSource(),
    )
    assert isinstance(result, Applied), result
    return result


def _endowment(result: Applied) -> dict[str, Any]:
    """The endowment event, found by type: a settlement also closes its phase."""
    return dict(next(event.payload for event in result.events if event.type == "resources_granted"))


def _event_types(result: Applied) -> list[str]:
    return [event.type for event in result.events]


def _hand(state: CatanState, seat: int) -> dict[str, int]:
    return {
        resource.value: state.hands[seat][index] for index, resource in enumerate(RESOURCE_ORDER)
    }


def test_the_bank_starts_full() -> None:
    state = _opening()

    assert state.bank == (BANK_PER_RESOURCE,) * len(RESOURCE_ORDER)
    assert all(hand == (0,) * len(RESOURCE_ORDER) for hand in state.hands)


def test_a_first_round_settlement_grants_nothing() -> None:
    state = _opening()
    vertex = _free_vertex(state)

    result = _settle(state, vertex, 0)

    assert result.state.hands[0] == (0,) * len(RESOURCE_ORDER)
    assert result.state.bank == state.bank
    assert _event_types(result)[:2] == ["settlement_placed", "piece_taken"]
    assert "resources_granted" not in _event_types(result)


def test_a_second_settlement_grants_one_card_for_each_adjacent_hex() -> None:
    state = _in_round_two(_opening(), turn=3)
    vertex = _free_vertex(state)
    hexes = state.board.topology.hexes_at(vertex)
    expected: dict[str, int] = {}
    for hex_id in hexes:
        resource = state.board.resource_of_hex(hex_id)
        if resource is not None:
            expected[resource.value] = expected.get(resource.value, 0) + 1
    assert expected, "the vertex must border something productive"

    result = _settle(state, vertex, 3)

    assert _hand(result.state, 3) == {name: expected.get(name, 0) for name in _hand(state, 3)}
    assert sum(expected.values()) > 0
    assert _endowment(result)["granted"] == expected


def _doubled_board() -> Board:
    """The curated board with two hexes of one vertex both made forest.

    A test double, deliberately: the curated board's balance property is that no vertex sees
    the same terrain twice, so "two hexes, two cards" cannot be exercised on it.
    """
    board = load_board("standard_a")
    target = next(
        vertex
        for vertex in range(len(board.topology.vertices))
        if len(board.topology.hexes_at(vertex)) >= 2
        and all(
            board.terrain[hex_id] is not Terrain.DESERT
            for hex_id in board.topology.hexes_at(vertex)[:2]
        )
    )
    hexes = list(board.topology.hexes_at(target))
    terrain = list(board.terrain)
    terrain[hexes[0]] = Terrain.FOREST
    terrain[hexes[1]] = Terrain.FOREST
    return Board(
        name=board.name,
        topology=board.topology,
        terrain=tuple(terrain),
        tokens=board.tokens,
        ports=board.ports,
        token_start_hex=board.token_start_hex,
    )


def _double_forest_vertex(board: Board) -> int:
    return next(
        vertex
        for vertex in range(len(board.topology.vertices))
        if sum(
            1
            for hex_id in board.topology.hexes_at(vertex)
            if board.terrain[hex_id] is Terrain.FOREST
        )
        >= 2
    )


def test_two_hexes_of_the_same_terrain_grant_two_cards() -> None:
    """Correction D-3: the endowment is per hex, not one of each resource."""
    board = _doubled_board()
    target = _double_forest_vertex(board)
    hexes = list(board.topology.hexes_at(target))
    state = _in_round_two(_opening(board), turn=2, keep_free=target)
    assert sum(1 for hex_id in hexes if state.board.terrain[hex_id] is Terrain.FOREST) == 2

    result = _settle(state, target, 2)

    assert _hand(result.state, 2)["wood"] == 2


def test_the_desert_grants_nothing() -> None:
    state = _in_round_two(_opening(), turn=0)
    vertex = _free_vertex(state, touching=(Terrain.DESERT,))

    result = _settle(state, vertex, 0)

    desert = state.board.desert_hex
    assert desert in state.board.topology.hexes_at(vertex)
    around = [
        state.board.resource_of_hex(hex_id) for hex_id in state.board.topology.hexes_at(vertex)
    ]
    expected = {resource.value for resource in around if resource is not None}
    held = {name for name, count in _hand(result.state, 0).items() if count}
    assert held == expected


def test_the_bank_pays_what_it_has_and_what_it_pays_is_conserved() -> None:
    state = _in_round_two(_opening(), turn=1)
    # A bank holding nothing is only reachable if somebody holds those cards: conservation is
    # the invariant under test, so the drained bank is drawn as an empty bank and a full hand.
    empty = (0,) * len(RESOURCE_ORDER)
    full = (BANK_PER_RESOURCE,) * len(RESOURCE_ORDER)
    drained = replace(state, bank=empty, hands=(full, *state.hands[1:]))
    vertex = _free_vertex(state)

    result = _settle(drained, vertex, 1)
    after = result.state

    assert after.hands[1] == (0,) * len(RESOURCE_ORDER), "an empty bank grants nothing"
    assert GAME.check_invariants(after) == []
    for index in range(len(RESOURCE_ORDER)):
        held = sum(hand[index] for hand in after.hands)
        assert after.bank[index] + held == BANK_PER_RESOURCE


def test_a_short_bank_gives_what_remains_and_the_rest_is_lost() -> None:
    """RULES.md 4.3 item 8: the entitlements are satisfied in order and the shortfall is lost."""
    board = _doubled_board()
    target = _double_forest_vertex(board)
    state = _in_round_two(_opening(board), turn=1, keep_free=target)
    wood = RESOURCE_ORDER.index(Resource.WOOD)
    bank = list(state.bank)
    bank[wood] = 1
    # Move the rest of the wood out of the bank, so the state stays conserving.
    hands = [list(hand) for hand in state.hands]
    hands[0][wood] += BANK_PER_RESOURCE - 1
    short = replace(state, bank=tuple(bank), hands=tuple(tuple(hand) for hand in hands))

    result = _settle(short, target, 1)
    details = _endowment(result)

    assert result.state.hands[1][wood] == 1, "the player takes what is left"
    assert details["granted"] == {"wood": 1}
    assert details["shortfall"] == {"wood": 1}
    assert GAME.check_invariants(result.state) == []


def test_the_endowment_names_what_it_took_and_what_it_lost() -> None:
    state = _in_round_two(_opening(), turn=2)
    vertex = _free_vertex(state)

    result = _settle(state, vertex, 2)
    payload = _endowment(result)

    assert payload["player"] == 2
    assert set(payload) >= {"granted", "shortfall"}
    assert sum(dict(payload["granted"]).values()) + sum(dict(payload["shortfall"]).values()) == len(
        state.board.topology.hexes_at(vertex)
    ) - (1 if state.board.desert_hex in state.board.topology.hexes_at(vertex) else 0)


def test_the_second_round_endowments_follow_the_draft_order() -> None:
    """RULES.md 4.3 item 7: seats 3, 2, 1, 0 take theirs as they place, one at a time."""
    state = _opening()
    seats = []
    for _ in range(PLAYERS):
        vertex = _free_vertex(state)
        state = _settle(state, vertex, state.turn).state
        seats.append(state.placed.settlements[vertex])
        edge = state.board.topology.edges_at(vertex)[0]
        state = GAME.apply(
            state,
            Action(player=state.turn, type="place_road", params={"edge": edge}),
            NullRandomSource(),
        ).state
    round_two = []
    for _ in range(PLAYERS):
        seat = state.turn
        round_two.append(seat)
        vertex = _free_vertex(state)
        before = state.hands[seat]
        state = _settle(state, vertex, seat).state
        assert state.placed.settlements[vertex] == seat
        assert any(count > before[index] for index, count in enumerate(state.hands[seat])), (
            "endowed"
        )
        edge = state.board.topology.edges_at(vertex)[0]
        state = GAME.apply(
            state, Action(player=seat, type="place_road", params={"edge": edge}), NullRandomSource()
        ).state

    assert round_two == [3, 2, 1, 0]
    assert GAME.check_invariants(state) == []


def test_resources_are_conserved_across_a_whole_draft() -> None:
    state = _opening()
    for _ in range(8):
        assert GAME.check_invariants(state) == []
        vertex = _free_vertex(state)
        state = _settle(state, vertex, state.turn).state
        assert GAME.check_invariants(state) == []
        edge = state.board.topology.edges_at(vertex)[0]
        state = GAME.apply(
            state,
            Action(player=state.turn, type="place_road", params={"edge": edge}),
            NullRandomSource(),
        ).state

    assert GAME.check_invariants(state) == []
    for index in range(len(RESOURCE_ORDER)):
        held = sum(hand[index] for hand in state.hands)
        assert state.bank[index] + held == BANK_PER_RESOURCE
    total = sum(sum(hand) for hand in state.hands)
    assert 8 <= total <= 12, "each player takes one card per adjacent hex: two or three"


def test_a_player_can_never_hold_more_than_the_bank_had() -> None:
    """A guard on the arithmetic: the endowment moves cards, it never creates them."""
    state = _in_round_two(_opening(), turn=0)
    vertex = _free_vertex(state)

    result = _settle(state, vertex, 0)

    for index in range(len(RESOURCE_ORDER)):
        assert result.state.hands[0][index] <= state.bank[index]
        assert result.state.bank[index] >= 0


def test_the_opening_state_keeps_the_player_option_out_of_the_bank() -> None:
    """The seat count is not a resource; a confused configuration must not drain the bank."""
    state = initial_state(load_board("standard_a"), players=PLAYERS, rng=SeededRandomSource(SEED))

    assert state.bank == (BANK_PER_RESOURCE,) * len(RESOURCE_ORDER)
    assert all(supply == Supply(15, 5, 4) for supply in state.supply)


@pytest.mark.parametrize("resource", list(Resource))
def test_every_resource_is_in_the_bank_and_in_the_order(resource: Resource) -> None:
    state = _opening()

    assert RESOURCE_ORDER[list(Resource).index(resource)] is resource
    assert state.bank[RESOURCE_ORDER.index(resource)] == BANK_PER_RESOURCE
