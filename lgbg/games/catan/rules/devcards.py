"""The development deck: buying from it (RULES.md 4.8; PRD-v1 FR-13.1, FR-13.2).

The deck is not shuffled here. It was shuffled once, at game start, by draw D5, and this module
only ever removes the *front* card from it: that is what the rulebook says ("draw the top card of
the deck") and it is what makes a purchase cost no randomness at all. The order was decided before
the first action, so the same seed deals the same cards to the same players, and a purchase is a
fact about the deck rather than a draw.

What a purchase does move is the card itself - out of the deck, into the buyer's inventory, and
into a per-turn tally of what was bought, because a development card bought this turn may not be
played until the next one (K-041). Three counters, one writer.
"""

from __future__ import annotations

from dataclasses import replace

from lgbg.core.errors import Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, Event
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import (
    NO_DEV_CARDS_REMAINING,
)
from lgbg.games.catan.rules import building
from lgbg.games.catan.state import CARD_ORDER, CatanState, DevCard, Phase


def can_buy_dev_card(state: CatanState, player: int) -> bool:
    """Whether a purchase is on offer: a card in the deck, and the price in hand (FR-13.2).

    An empty deck makes the action *unavailable* rather than refused when attempted - the same
    shape as a player who has run out of roads - because a purchase from an empty deck is not a
    mistake anybody can avoid by playing better.
    """
    return bool(state.dev_deck) and building.affordable(state, player, building.DEVELOPMENT_CARD)


def buy_dev_card(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Buy the top card of the deck (FR-13.1, FR-13.2; RULES.md 4.8)."""
    del rng  # the deck was shuffled at game start, so a purchase draws nothing
    refusal = phases.refuse_unless_acting(state, action, Phase.ACTION)
    if refusal is not None:
        return refusal
    if not state.dev_deck:
        return Rejected(
            Rejection(
                code=NO_DEV_CARDS_REMAINING,
                message="the development deck is empty, so there is nothing to buy",
                details={"player": action.player, "remaining": 0},
            )
        )
    paid = building.pay(state, action.player, building.DEVELOPMENT_CARD)
    if isinstance(paid, Rejected):
        return paid

    bought, spent = paid
    card = bought.dev_deck[0]
    index = CARD_ORDER.index(DevCard(card))
    held = list(bought.dev_cards[action.player])
    held[index] += 1
    this_turn = list(bought.bought_this_turn[action.player])
    this_turn[index] += 1
    cards = list(bought.dev_cards)
    cards[action.player] = tuple(held)
    turns = list(bought.bought_this_turn)
    turns[action.player] = tuple(this_turn)
    deck = bought.dev_deck[1:]
    return Applied(
        state=replace(
            bought,
            dev_deck=deck,
            dev_cards=tuple(cards),
            bought_this_turn=tuple(turns),
        ),
        events=[
            spent,
            Event(
                type="dev_card_bought",
                payload={"player": action.player, "card": card, "remaining": len(deck)},
            ),
        ],
    )
