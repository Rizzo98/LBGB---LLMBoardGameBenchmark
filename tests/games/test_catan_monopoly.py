"""The Monopoly card (PRD-v1 FR-13.7; RULES.md 4.8).

One resource is announced, and every other player gives all of it. Three things are worth
testing, and each is a way the card is easy to get wrong: the mover's *own* holding is not taken
(the card says every other player), nothing comes *from the bank* (a monopoly moves cards between
hands), and a player holding none gives nothing rather than blocking the take.

The announcement is the second card to be *told* something by the player, so it goes through the
same requirement table the Year of Plenty uses: a bad announcement costs the attempt and not the
card.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.errors import BAD_PARAMS, Rejection
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rules.devcards import choices, playable_cards
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    CARD_ORDER,
    RESOURCE_ORDER,
    CatanState,
    DevCard,
)
from tests.games.catan_boards import hand, holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260119
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}
CARD: Final[DevCard] = DevCard.MONOPOLY


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _stocked(state: CatanState) -> CatanState:
    """A table where three of the four seats hold wool, one of them none."""
    board = layout(state, turn=0)
    board = holding(board, 1, wool=2, ore=1)
    board = holding(board, 2, brick=3)
    board = holding(board, 3, wool=4, wheat=1)
    rows = [list(row) for row in board.dev_cards]
    rows[0][CARD_ORDER.index(CARD)] = 1
    return replace(board, dev_cards=tuple(tuple(row) for row in rows))


def _play(state: CatanState, resources: Any, seat: int = 0) -> Any:
    params: dict[str, Any] = {"card": CARD.value}
    if resources is not None:
        params["resources"] = resources
    return GAME.apply(
        state, Action(player=seat, type=phases.PLAY_DEV_CARD, params=params), NullRandomSource()
    )


def _refusal(state: CatanState, resources: Any) -> Rejection:
    result = _play(state, resources)
    assert isinstance(result, Rejected), "an illegal announcement must be refused"
    return result.rejection


def test_every_other_player_gives_all_of_the_named_resource() -> None:
    state = _stocked(holding(_opening(), 0, wool=1))

    played = _play(state, ["wool"])

    assert isinstance(played, Applied)
    assert played.state.hands[0][SLOT["wool"]] == 1 + 2 + 4, "the mover's own wool is kept"
    assert played.state.hands[1][SLOT["wool"]] == 0
    assert played.state.hands[2][SLOT["wool"]] == 0
    assert played.state.hands[3][SLOT["wool"]] == 0
    assert played.state.hands[1][SLOT["ore"]] == 1, "and nothing else moves"
    assert played.state.hands[3][SLOT["wheat"]] == 1


def test_a_player_holding_none_gives_nothing() -> None:
    state = _stocked(_opening())

    played = _play(state, ["wool"])

    assert isinstance(played, Applied)
    assert dict(played.events[1].payload)["given"] == {"1": 2, "3": 4}, "seat 2 gave nothing"
    assert dict(played.events[1].payload)["total"] == 6


def test_nothing_is_taken_from_the_bank() -> None:
    """A monopoly moves cards between hands: the bank is asserted to the card."""
    state = _stocked(_opening())
    before = state.bank

    played = _play(state, ["wool"])

    assert isinstance(played, Applied)
    assert played.state.bank == before
    assert GAME.check_invariants(played.state) == []
    for index in range(len(RESOURCE_ORDER)):
        held = sum(row[index] for row in played.state.hands)
        assert played.state.bank[index] + held == BANK_PER_RESOURCE


def test_the_event_names_every_contribution() -> None:
    state = _stocked(_opening())

    played = _play(state, ["wool"])

    assert isinstance(played, Applied)
    assert [event.type for event in played.events] == ["dev_card_played", "monopoly_taken"]
    assert dict(played.events[1].payload) == {
        "player": 0,
        "resource": "wool",
        "given": {"1": 2, "3": 4},
        "total": 6,
    }


def test_an_announcement_that_names_nothing_is_refused_and_costs_nothing() -> None:
    state = _stocked(_opening())

    missing = _refusal(state, None)
    unknown = _refusal(state, ["gold"])
    two = _refusal(state, ["wool", "ore"])

    assert missing.code == BAD_PARAMS
    assert unknown.code == BAD_PARAMS
    assert two.code == BAD_PARAMS
    assert state.dev_cards[0][CARD_ORDER.index(CARD)] == 1, "the card stays in hand"
    assert state.played_this_turn[0] == 0


def test_the_enumeration_offers_each_resource_once() -> None:
    """FR-17.5: five announcements on offer, and every one of them accepted."""
    state = _stocked(_opening())

    offered = [
        dict(action.params)["resources"]
        for action in GAME.legal_actions(state, 0)
        if action.type == phases.PLAY_DEV_CARD
    ]

    assert offered == [[item.value] for item in RESOURCE_ORDER]
    assert len(choices(state, CARD)) == len(RESOURCE_ORDER)
    for announcement in offered:
        assert isinstance(_play(state, announcement), Applied)


def test_the_card_may_be_played_even_when_nobody_holds_the_resource() -> None:
    """Nothing in the rules requires the announcement to be worth anything."""
    state = _stocked(_opening())
    board = replace(state, hands=tuple(hand() for _ in range(PLAYERS)))

    played = _play(board, ["wool"])

    assert isinstance(played, Applied)
    assert dict(played.events[1].payload)["total"] == 0
    assert board.dev_cards[0][CARD_ORDER.index(CARD)] == 1
    assert CARD in playable_cards(state, 0)


def test_the_mover_keeps_their_own_cards() -> None:
    """The card says *every other* player: a mover holding wool does not give to themselves."""
    state = _stocked(holding(_opening(), 0, wool=3))

    played = _play(state, ["wool"])

    assert isinstance(played, Applied)
    assert played.state.hands[0][SLOT["wool"]] == 3 + 6
    assert sum(row[SLOT["wool"]] for row in played.state.hands) == 9, "three in hand, six taken"
