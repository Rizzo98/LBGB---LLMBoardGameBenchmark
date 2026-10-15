"""The Road Building card (PRD-v1 FR-13.5; RULES.md 4.8, 5.6 A-6).

Two roads for nothing, placed one at a time, and the card's whole interest is in the edges of
that: the second road is judged against the board the first one left behind, and a road that
cannot be placed is *lost* rather than refused - the card is consumed either way, which is what
A-6 pins and what an implementation that "needs two roads" gets wrong.

The card also has the one playability condition in the game that depends on the board rather than
on the hand: it may only be played when there is a road in supply and somewhere legal to put it,
and otherwise it stays in hand (A-6 item 5).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.errors import WRONG_PHASE
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import CARD_NOT_PLAYABLE, NOT_CONNECTED
from lgbg.games.catan.rules.building import road_targets
from lgbg.games.catan.rules.devcards import FREE_ROADS, playable_cards
from lgbg.games.catan.state import (
    CARD_ORDER,
    PIECES_PER_PLAYER,
    CatanState,
    DevCard,
    Phase,
    Supply,
)
from tests.games.catan_boards import hand, holding, layout, vertices_of

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260105
CARD: Final[DevCard] = DevCard.ROAD_BUILDING


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _with_card(
    state: CatanState,
    *,
    cards: int = 1,
    roads: int = 15,
    seat: int = 0,
    phase: Phase = Phase.ACTION,
    dice: tuple[int, int] | None = (3, 4),
    lines: tuple[tuple[int, int], ...] = (),
) -> CatanState:
    """A position holding the card, with a chosen number of roads left in supply."""
    # One road on the board, because a free road obeys the connectivity rule: without a network
    # of its own a player has nowhere legal to build, and the card could not be played at all.
    board = layout(state, roads=[(0, seat), *lines], turn=seat)
    stock = list(board.supply)
    held = stock[seat]
    stock[seat] = Supply(roads, held.settlements, held.cities)
    rows = [list(row) for row in board.dev_cards]
    rows[seat][CARD_ORDER.index(CARD)] = cards
    return replace(
        board,
        supply=tuple(stock),
        dev_cards=tuple(tuple(row) for row in rows),
        phase=phase,
        dice=dice,
    )


def _play(state: CatanState, seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(player=seat, type=phases.PLAY_DEV_CARD, params={"card": CARD.value}),
        NullRandomSource(),
    )


def _place(state: CatanState, edge: int, seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(player=seat, type=phases.PLACE_FREE_ROAD, params={"edge": edge}),
        NullRandomSource(),
    )


def test_the_card_opens_a_phase_that_owes_two_roads() -> None:
    state = _with_card(_opening())

    played = _play(state)

    assert isinstance(played, Applied)
    assert played.state.phase is Phase.ROAD_BUILDING
    assert played.state.free_roads == FREE_ROADS == 2
    requests = GAME.pending_decisions(played.state)
    assert [request.kind for request in requests] == [phases.PLACE_FREE_ROAD]
    assert dict(requests[0].context)["roads_left"] == 2


def test_two_free_roads_are_placed_and_nothing_is_paid() -> None:
    state = _with_card(_opening())
    played = _play(state)
    assert isinstance(played, Applied)
    targets = list(road_targets(played.state, 0))

    first = _place(played.state, targets[0])
    assert isinstance(first, Applied)
    assert first.state.free_roads == 1
    assert first.state.hands[0] == hand(), "a free road costs nothing"
    assert first.state.placed.roads[targets[0]] == 0

    second = _place(first.state, road_targets(first.state, 0)[0])

    assert isinstance(second, Applied)
    assert second.state.free_roads == 0
    assert second.state.phase is Phase.ACTION, "the card is done and the turn goes on"
    before = sum(1 for seat in played.state.placed.roads if seat == 0)
    assert sum(1 for seat in second.state.placed.roads if seat == 0) == before + 2


def test_the_second_road_is_judged_against_the_board_the_first_one_made() -> None:
    """A-6 item 6: a free road may open the edge for the next one."""
    state = _with_card(_opening())
    played = _play(state)
    assert isinstance(played, Applied)
    first_edge = road_targets(played.state, 0)[0]
    before = set(road_targets(played.state, 0))

    first = _place(played.state, first_edge)
    assert isinstance(first, Applied)

    assert set(road_targets(first.state, 0)) != before, "the board it is judged against has moved"
    assert first_edge not in road_targets(first.state, 0)


def test_a_road_that_cannot_be_placed_is_lost_and_the_card_is_still_spent() -> None:
    """A-6 items 3 and 4: one road placed, the second impossible, and the card is gone."""
    state = _with_card(_opening(), roads=1)
    played = _play(state)
    assert isinstance(played, Applied)

    first = _place(played.state, road_targets(played.state, 0)[0])

    assert isinstance(first, Applied)
    assert first.state.supply[0].roads == 0, "the supply is exhausted"
    assert first.state.phase is Phase.ACTION, "so the phase stops asking"
    assert first.state.free_roads == 1, "and one free road was never placed"
    assert first.state.dev_cards[0][CARD_ORDER.index(CARD)] == 0, "the card is consumed anyway"


def test_a_road_on_an_edge_that_is_not_legal_is_refused() -> None:
    state = _with_card(_opening())
    played = _play(state)
    assert isinstance(played, Applied)
    illegal = next(
        edge
        for edge in range(len(played.state.placed.roads))
        if played.state.placed.roads[edge] == -1 and edge not in road_targets(played.state, 0)
    )

    refused = _place(played.state, illegal)

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NOT_CONNECTED, "a free road obeys the same rules as a paid one"


def test_the_card_is_not_offered_when_it_could_not_place_a_road() -> None:
    """A-6 item 5: with no road in supply, or nowhere legal to put one, the card stays in hand."""
    no_supply = _with_card(_opening(), roads=0)
    assert CARD not in playable_cards(no_supply, 0)
    refused = _play(no_supply)
    assert isinstance(refused, Rejected)
    assert refused.rejection.code == CARD_NOT_PLAYABLE
    assert no_supply.dev_cards[0][CARD_ORDER.index(CARD)] == 1, "the card stays in hand"


def test_a_placement_with_no_card_running_is_refused() -> None:
    """The phase is not open, so the request is not open either."""
    state = _with_card(_opening(), phase=Phase.ACTION)

    refused = _place(state, 0)

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == WRONG_PHASE, "no card is running, so no phase is open"


def test_the_free_road_counts_for_the_road_supply_and_the_award() -> None:
    """A free road is a road: it comes from supply, and it can make a longest road."""
    state = _with_card(_opening(), roads=14)
    played = _play(state)
    assert isinstance(played, Applied)
    edge = road_targets(played.state, 0)[0]

    first = _place(played.state, edge)

    assert isinstance(first, Applied)
    assert first.state.supply[0].roads == 13, "the fixture's stock, less the free road"
    assert (
        first.state.supply[0].roads + sum(1 for seat in first.state.placed.roads if seat == 0)
        == PIECES_PER_PLAYER[0]
    ), "a free road comes out of the same fifteen"
    assert len(vertices_of(first.state, edge)) == 2, "a road joins two vertices"


def test_the_turn_returns_to_the_roll_when_the_card_was_played_before_it() -> None:
    state = _with_card(_opening(), phase=Phase.TURN_PRODUCTION, dice=None)
    played = _play(state)
    assert isinstance(played, Applied)

    first = _place(played.state, road_targets(played.state, 0)[0])
    assert isinstance(first, Applied)
    second = _place(first.state, road_targets(first.state, 0)[0])

    assert isinstance(second, Applied)
    assert second.state.phase is Phase.TURN_PRODUCTION
    assert second.state.dice is None, "the roll is still to come"


def test_the_shortfall_in_supply_is_the_pinned_behaviour() -> None:
    """A-6: as many roads as the supply allows, and the rest are lost."""
    state = _with_card(_opening(), roads=1)
    played = _play(state)
    assert isinstance(played, Applied)
    assert played.state.free_roads == 2

    placed = _place(played.state, road_targets(played.state, 0)[0])
    assert isinstance(placed, Applied)

    assert placed.state.free_roads == 1
    assert placed.state.supply[0].roads == 0
    assert [request.kind for request in GAME.pending_decisions(placed.state)] != [
        phases.PLACE_FREE_ROAD
    ]
    assert holding(placed.state, 3, wool=1) is not placed.state
