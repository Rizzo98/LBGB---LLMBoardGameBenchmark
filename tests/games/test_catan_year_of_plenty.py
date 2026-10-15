"""The Year of Plenty card (PRD-v1 FR-13.6; RULES.md 4.8, A-4, A-5).

Two cards from the bank, and the two things worth testing are the two the rules had to pin: the
same resource twice is allowed (A-4 - "2 of the same resource"), and the take is limited by what
the bank actually holds (A-5). The second is also the first card whose *parameters* the rules
check, which is why a refusal here costs nothing: the card stays in hand and the player may name
something the bank has.
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
from lgbg.games.catan.rejections import BANK_LACKS_RESOURCE
from lgbg.games.catan.rules.devcards import PLENTY, choices, playable_cards
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    CARD_ORDER,
    RESOURCE_ORDER,
    CatanState,
    DevCard,
    Phase,
)
from tests.games.catan_boards import hand, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260112
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}
CARD: Final[DevCard] = DevCard.YEAR_OF_PLENTY


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _holding(state: CatanState, *, cards: int = 1, seat: int = 0) -> CatanState:
    board = layout(state, turn=seat)
    rows = [list(row) for row in board.dev_cards]
    rows[seat][CARD_ORDER.index(CARD)] = cards
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
    assert isinstance(result, Rejected), "an illegal take must be refused"
    return result.rejection


def test_two_different_resources_are_taken() -> None:
    state = _holding(_opening())
    before = state.bank

    played = _play(state, ["wool", "ore"])

    assert isinstance(played, Applied)
    assert played.state.hands[0] == hand(wool=1, ore=1)
    assert played.state.bank[SLOT["wool"]] == before[SLOT["wool"]] - 1
    assert played.state.bank[SLOT["ore"]] == before[SLOT["ore"]] - 1
    assert [event.type for event in played.events] == ["dev_card_played", "resources_taken"]
    assert dict(played.events[1].payload) == {"player": 0, "resources": ["wool", "ore"]}
    assert GAME.check_invariants(played.state) == []


def test_the_same_resource_twice_is_allowed() -> None:
    """A-4: the two cards may be the same resource, which the card's own text says."""
    state = _holding(_opening())
    before = state.bank[SLOT["wood"]]

    played = _play(state, ["wood", "wood"])

    assert isinstance(played, Applied)
    assert played.state.hands[0] == hand(wood=PLENTY)
    assert played.state.bank[SLOT["wood"]] == before - PLENTY


def test_the_take_is_limited_by_what_the_bank_holds() -> None:
    """A-5: a player may not take a card the bank does not have."""
    state = _holding(_opening())
    bank = list(state.bank)
    bank[SLOT["wheat"]] = 1
    starved = replace(state, bank=tuple(bank))

    refusal = _refusal(starved, ["wheat", "wheat"])

    assert refusal.code == BANK_LACKS_RESOURCE
    assert dict(refusal.details)["missing"] == {"wheat": 1}
    assert starved.dev_cards[0][CARD_ORDER.index(CARD)] == 1, "the card stays in hand"
    assert starved.hands[0] == hand()


def test_a_refused_take_costs_nothing() -> None:
    """The requirement runs before the card leaves the hand, so a bad choice is only an attempt."""
    state = _holding(_opening())

    refusal = _refusal(state, ["wool"])

    assert refusal.code == BAD_PARAMS
    assert state.dev_cards[0][CARD_ORDER.index(CARD)] == 1
    assert state.played_this_turn[0] == 0, "the turn has not spent its card"


def test_an_unknown_resource_is_a_parameter_error() -> None:
    state = _holding(_opening())

    assert _refusal(state, ["gold", "ore"]).code == BAD_PARAMS
    assert _refusal(state, "wool").code == BAD_PARAMS
    assert _refusal(state, None).code == BAD_PARAMS


def test_the_enumeration_offers_every_pair_the_bank_can_cover() -> None:
    """FR-17.5: what is offered is what the rule accepts, including the pair itself."""
    state = _holding(_opening())

    offered = [
        dict(action.params)["resources"]
        for action in GAME.legal_actions(state, 0)
        if action.type == phases.PLAY_DEV_CARD
    ]

    assert len(offered) == len(choices(state, CARD)) == 15, "five resources, twice, unordered"
    assert ["wool", "wool"] in offered
    assert ["wool", "ore"] in offered, "pairs are written in canonical order"
    for pair in offered:
        result = _play(state, pair)
        assert isinstance(result, Applied), f"{pair} was offered and refused"


def test_a_starved_bank_shrinks_what_is_offered() -> None:
    """The offer is read from the bank, so an empty bank offers fewer pairs."""
    state = _holding(_opening())
    bank = list(state.bank)
    bank[SLOT["wool"]] = 0
    starved = replace(state, bank=tuple(bank))

    offered = choices(starved, CARD)

    assert {"resources": ["wool", "wool"]} not in offered
    for entry in offered:
        pair = dict(entry)["resources"]
        assert isinstance(pair, list)
        assert "wool" not in pair
    assert state.bank[SLOT["wool"]] == BANK_PER_RESOURCE


def test_the_card_is_played_in_the_action_phase_and_the_bank_pays() -> None:
    state = _holding(_opening())
    assert CARD in playable_cards(state, 0)

    played = _play(state, ["brick", "brick"])

    assert isinstance(played, Applied)
    assert played.state.phase is Phase.ACTION, "the take resolves inside the play, in one action"
    assert sum(sum(row) for row in played.state.hands) == 2
