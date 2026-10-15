"""Buying development cards (PRD-v1 FR-13.1, FR-13.2; RULES.md 4.8).

The deck is fixed at the start: twenty-five cards in the Appendix A composition, shuffled once by
draw D5. Everything about a purchase follows from that - the *front* card is the card a player
gets, a purchase consumes no randomness at all, and when the deck runs out the action stops being
offered rather than failing when somebody tries it.

What a purchase writes is three counters and one event: the deck shrinks, the buyer's inventory
grows, and the turn's tally of what was bought grows with it, because a card bought this turn may
not be played until the next one (K-041). The event names the card, because the record is the god
view; keeping it private from the other players is the projection's job, and it has its own test.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig
from lgbg.core.errors import NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.projection import observe
from lgbg.games.catan.rejections import DECK_EMPTY, NOT_ENOUGH_RESOURCES
from lgbg.games.catan.rules.building import COSTS, DEVELOPMENT_CARD
from lgbg.games.catan.rules.devcards import can_buy_dev_card
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    CANONICAL_DECK,
    CARD_ORDER,
    DECK_COMPOSITION,
    CatanState,
    DevCard,
    Phase,
)
from tests.games.catan_boards import hand, holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251215
A_CARD: Final[dict[str, int]] = {"wool": 1, "wheat": 1, "ore": 1}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _ready(state: CatanState, seat: int = 0, **counts: int) -> CatanState:
    """A position in the action phase with the price of a card in hand."""
    board = layout(state, turn=seat)
    return holding(board, seat, **(counts or A_CARD))


def _buy(state: CatanState, seat: int = 0) -> Any:
    return GAME.apply(
        state, Action(player=seat, type=phases.BUY_DEV_CARD, params={}), NullRandomSource()
    )


def _refusal(state: CatanState, seat: int = 0) -> Rejection:
    result = _buy(state, seat)
    assert isinstance(result, Rejected), "an illegal purchase must be refused"
    return result.rejection


def _held(state: CatanState, seat: int, card: DevCard) -> int:
    return state.dev_cards[seat][CARD_ORDER.index(card)]


def test_the_deck_holds_the_appendix_a_composition() -> None:
    """FR-13.1: twenty-five cards, in the counts the appendix lists."""
    assert len(CANONICAL_DECK) == 25
    assert dict(DECK_COMPOSITION) == {
        DevCard.KNIGHT: 14,
        DevCard.VICTORY_POINT: 5,
        DevCard.ROAD_BUILDING: 2,
        DevCard.YEAR_OF_PLENTY: 2,
        DevCard.MONOPOLY: 2,
    }
    deck = _opening().dev_deck
    assert len(deck) == 25
    assert {card: deck.count(card) for card in deck} == {
        card.value: count for card, count in DECK_COMPOSITION.items()
    }


def test_the_deck_is_shuffled_at_the_start_and_not_again() -> None:
    """Draw D5 happens once: two openings from one seed deal the same order."""
    first = _opening().dev_deck
    second = _opening().dev_deck
    other = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED + 1)
    ).dev_deck

    assert first == second
    assert first != other, "another seed shuffles another way"
    assert first != tuple(card.value for card in CANONICAL_DECK), "and the order really is shuffled"


def test_the_price_is_the_one_appendix_a_lists() -> None:
    assert dict(COSTS[DEVELOPMENT_CARD]) == A_CARD
    cost = COSTS[DEVELOPMENT_CARD]
    assert sum(cost.values()) == 3


def test_buying_takes_the_top_card_of_the_deck() -> None:
    """A purchase removes the *front* card: the order was decided before the first action."""
    state = _ready(_opening())
    top = state.dev_deck[0]

    bought = _buy(state)

    assert isinstance(bought, Applied)
    assert bought.state.dev_deck == state.dev_deck[1:]
    assert _held(bought.state, 0, DevCard(top)) == 1
    assert bought.state.bought_this_turn[0][CARD_ORDER.index(DevCard(top))] == 1
    assert bought.state.hands[0] == hand()
    assert bought.state.bank[0] == BANK_PER_RESOURCE, "and the bank got its cards back"
    assert [event.type for event in bought.events] == ["resources_spent", "dev_card_bought"]
    assert dict(bought.events[1].payload) == {"player": 0, "card": top, "remaining": 24}
    assert GAME.check_invariants(bought.state) == []


def test_a_purchase_draws_nothing() -> None:
    """RULES.md 3.1: the deck order was fixed by D5, so buying consumes no draw."""
    source = NullRandomSource()

    bought = GAME.apply(
        _ready(_opening()), Action(player=0, type=phases.BUY_DEV_CARD, params={}), source
    )

    assert isinstance(bought, Applied)
    assert source.draws() == []


def test_two_purchases_take_the_first_two_cards() -> None:
    state = _ready(_opening(), wool=2, wheat=2, ore=2)

    first = _buy(state)
    assert isinstance(first, Applied)
    second = _buy(first.state)

    assert isinstance(second, Applied)
    assert second.state.dev_deck == state.dev_deck[2:]
    assert sum(second.state.dev_cards[0]) == 2, "both cards are in the hand, of whatever kind"
    assert second.state.bought_this_turn[0] == second.state.dev_cards[0]


def test_a_player_who_cannot_afford_a_card_loses_nothing() -> None:
    state = layout(_opening())
    deck = state.dev_deck

    refusal = _refusal(state)

    assert refusal.code == NOT_ENOUGH_RESOURCES
    assert dict(refusal.details)["build"] == DEVELOPMENT_CARD
    assert dict(refusal.details)["missing"] == A_CARD
    assert state.dev_deck == deck, "no card left the deck"
    assert state.hands[0] == hand()
    assert can_buy_dev_card(state, 0) is False


def test_an_empty_deck_makes_the_action_unavailable() -> None:
    """FR-13.2: the action stops being offered, and an attempt is refused for that reason."""
    state = _ready(replace(_opening(), dev_deck=()))

    refusal = _refusal(state)

    assert refusal.code == DECK_EMPTY
    assert dict(refusal.details) == {"player": 0, "remaining": 0}
    assert can_buy_dev_card(state, 0) is False
    offered = dict(GAME.pending_decisions(state)[0].context)["actions"]
    assert phases.BUY_DEV_CARD not in [str(name) for name in offered]
    assert state.hands[0] == hand(**A_CARD), "and the price is still in hand: nothing was spent"


def test_buying_is_the_last_card_taken_from_the_deck() -> None:
    """The boundary: a deck of one card sells that card, and then there is nothing left."""
    state = _ready(replace(_opening(), dev_deck=(DevCard.KNIGHT.value,)))

    bought = _buy(state)

    assert isinstance(bought, Applied)
    assert bought.state.dev_deck == ()
    assert _held(bought.state, 0, DevCard.KNIGHT) == 1
    assert can_buy_dev_card(bought.state, 0) is False


def test_a_purchase_is_not_made_out_of_turn_or_out_of_phase() -> None:
    state = _ready(_opening())

    elsewhere = _refusal(replace(state, phase=Phase.TURN_PRODUCTION))
    other_seat = _refusal(state, seat=1)

    assert elsewhere.code == WRONG_PHASE
    assert other_seat.code == NOT_YOUR_DECISION


def test_the_action_is_offered_with_its_price_and_disappears_when_the_deck_is_empty() -> None:
    """FR-13.1 and FR-17.4 together: the offer and the price are read from the same table."""
    state = _ready(_opening())

    offered = [dict(action.params) for action in GAME.legal_actions(state, 0)]
    domains = {domain.type: domain for domain in GAME.action_domains(state, 0)}

    assert {} in offered, "the purchase takes no parameters"
    assert phases.BUY_DEV_CARD in domains
    assert dict(domains[phases.BUY_DEV_CARD].cost or {}) == A_CARD
    empty = _ready(replace(_opening(), dev_deck=()))
    assert phases.BUY_DEV_CARD not in {domain.type for domain in GAME.action_domains(empty, 0)}


@pytest.mark.parametrize("seat", range(PLAYERS))
def test_the_card_a_player_bought_is_not_visible_to_anybody_else(seat: int) -> None:
    """FR-16.3: the record names the card, the projection does not."""
    bought = _buy(_ready(_opening(), seat=seat, **A_CARD), seat)
    assert isinstance(bought, Applied)

    for observer in range(PLAYERS):
        view = observe(bought.state, observer)
        assert "dev_cards" not in view
        assert "dev_deck" not in view
    assert GAME.observe_spectator(bought.state)["dev_cards"] == [
        list(row) for row in bought.state.dev_cards
    ]
