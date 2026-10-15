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

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Final

from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, Event, JsonValue
from lgbg.games.catan import phases
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import (
    BANK_LACKS_RESOURCE,
    CARD_BOUGHT_THIS_TURN,
    CARD_NOT_PLAYABLE,
    NO_DEV_CARDS_REMAINING,
    ONE_CARD_PER_TURN,
)
from lgbg.games.catan.rules import building
from lgbg.games.catan.state import CARD_ORDER, RESOURCE_ORDER, CatanState, DevCard, Phase

Effect = Callable[[CatanState, Action, RandomSource], tuple[CatanState, list[Event]]]
"""What a played card does: a function of the position, the action, and the source of randomness.

The action is part of it because two of the five cards are *told* something by the player - which
resources to take, which to monopolise - and an effect that could not see the action could not
implement those cards at all.
"""

Requirement = Callable[[CatanState, Action], "Rejected | None"]
"""What a card must be told, checked while the card is still in the player's hand."""
"""What a played card does: a function of the position it is played in."""

PLAYABLE: tuple[DevCard, ...] = (
    DevCard.KNIGHT,
    DevCard.ROAD_BUILDING,
    DevCard.YEAR_OF_PLENTY,
    DevCard.MONOPOLY,
)
"""The four kinds that may be *played*. A victory-point card is not: RULES.md 4.13 item 3 says
revealing one is not an action, it is what winning looks like."""


def knight_effect(
    state: CatanState, action: Action, rng: RandomSource
) -> tuple[CatanState, list[Event]]:
    """A knight moves the robber and steals - the same flow a seven runs (FR-12.6; RULES.md 4.9).

    The flow is not re-implemented here. The card puts the game into the robber phase, and the
    phase machine asks the mover to move the robber and then to choose a victim: the two steps
    that a seven already runs, with the same rules and the same events. What a knight does *not*
    do is open the discard phase (A-2), and it does not, because nothing here mentions it.

    The card also counts itself: a knight that has been played stays face up for the rest of the
    game, and that count is what Largest Army is computed from (K-047).
    """
    player = action.player
    played = list(state.knights_played)
    played[player] += 1
    with_knight = replace(state, knights_played=tuple(played))
    entered, announced = phases.begin(with_knight, Phase.ROBBER)
    _ = rng  # the robber flow draws when it steals, not here
    return entered, announced


FREE_ROADS: Final[int] = 2
"""How many free roads the card owes (RULES.md 5.6 A-6 item 2)."""


def road_building_effect(
    state: CatanState, action: Action, rng: RandomSource
) -> tuple[CatanState, list[Event]]:
    """Two free roads, one decision at a time (FR-13.5; RULES.md 4.8 and 5.6 A-6).

    The card does not place anything: it opens the sub-phase and records how many placements are
    owed, and the phase machine asks for them one at a time, so each one is judged against the
    board the previous one left behind (A-6 item 6). A road that cannot be placed is lost, which
    is why the counter can end above zero without anything being wrong.
    """
    _ = rng
    entered, announced = phases.begin(replace(state, free_roads=FREE_ROADS), Phase.ROAD_BUILDING)
    return entered, announced


ANNOUNCEMENT: Final[int] = 1
"""How many resources a monopoly names: exactly one (RULES.md 4.8)."""

PLENTY: Final[int] = 2
"""How many cards the Year of Plenty takes: exactly two, the same resource or two (A-4)."""


def _chosen(action: Action, how_many: int) -> list[Resource] | Rejected:
    """Read the resources a card was told to take, refusing anything the rules would not."""
    value = action.params.get("resources")
    if isinstance(value, str) or not isinstance(value, Sequence):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"this card takes {how_many} named resources",
                details={"resources": None},
            )
        )
    chosen: list[Resource] = []
    for name in value:
        named = next((item for item in RESOURCE_ORDER if item.value == name), None)
        if named is None:
            return Rejected(
                Rejection(
                    code=BAD_PARAMS,
                    message=f"{name!r} is not a resource of this game",
                    details={"resource": name if isinstance(name, str) else None},
                )
            )
        chosen.append(named)
    if len(chosen) != how_many:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"this card takes exactly {how_many} resources, not {len(chosen)}",
                details={"resources": [item.value for item in chosen]},
            )
        )
    return chosen


def _named(action: Action, how_many: int) -> Rejected | None:
    """The monopoly announcement, which needs a resource and nothing else (RULES.md 4.8)."""
    chosen = _chosen(action, how_many)
    return chosen if isinstance(chosen, Rejected) else None


def _bank_holds(state: CatanState, action: Action) -> Rejected | None:
    """The Year of Plenty take, limited by what the bank holds (RULES.md 4.8, A-5).

    Checked before the card is spent, so a take the bank cannot cover costs nothing but the
    attempt: the card stays in hand and the player can try again with a resource that is there.
    """
    chosen = _chosen(action, PLENTY)
    if isinstance(chosen, Rejected):
        return chosen
    wanted = Counter(chosen)
    short = {
        item.value: wanted[item] - state.bank[RESOURCE_ORDER.index(item)]
        for item in RESOURCE_ORDER
        if wanted[item] > state.bank[RESOURCE_ORDER.index(item)]
    }
    if short:
        return Rejected(
            Rejection(
                code=BANK_LACKS_RESOURCE,
                message="the bank does not hold that many of those resources",
                details={"missing": short, "chosen": [item.value for item in chosen]},
            )
        )
    return None


def year_of_plenty_effect(
    state: CatanState, action: Action, rng: RandomSource
) -> tuple[CatanState, list[Event]]:
    """Take two cards from the bank, which may be the same resource twice (FR-13.6; A-4)."""
    _ = rng  # taking from the bank is a choice, not a draw
    chosen = _chosen(action, PLENTY)
    if isinstance(chosen, Rejected):
        raise ValueError("the requirement runs before the effect, so this cannot be reached")
    hand = list(state.hands[action.player])
    bank = list(state.bank)
    for item in chosen:
        index = RESOURCE_ORDER.index(item)
        hand[index] += 1
        bank[index] -= 1
    hands = list(state.hands)
    hands[action.player] = tuple(hand)
    return (
        replace(state, hands=tuple(hands), bank=tuple(bank)),
        [
            Event(
                type="resources_taken",
                payload={
                    "player": action.player,
                    "resources": [item.value for item in chosen],
                },
            )
        ],
    )


def monopoly_effect(
    state: CatanState, action: Action, rng: RandomSource
) -> tuple[CatanState, list[Event]]:
    """Every other player gives all of one resource, in one event (FR-13.7; RULES.md 4.8).

    Nothing comes from the bank: a monopoly moves cards between hands, which the test asserts by
    checking the bank to the card. A player who holds none of the named resource gives nothing,
    and the mover is not told in advance which of them those are - the *count* of every hand is
    public and its contents are not, which is what makes the choice a guess.
    """
    _ = rng  # a monopoly is an announcement, not a draw
    chosen = _chosen(action, ANNOUNCEMENT)
    if isinstance(chosen, Rejected):
        raise ValueError("the requirement runs before the effect, so this cannot be reached")
    wanted = RESOURCE_ORDER.index(chosen[0])
    given: dict[str, int] = {}
    hands = [list(row) for row in state.hands]
    taken = 0
    for seat in range(state.players):
        if seat == action.player:
            continue
        count = hands[seat][wanted]
        if not count:
            continue
        hands[seat][wanted] = 0
        hands[action.player][wanted] += count
        taken += count
        given[str(seat)] = count
    return (
        replace(state, hands=tuple(tuple(row) for row in hands)),
        [
            Event(
                type="monopoly_taken",
                payload={
                    "player": action.player,
                    "resource": chosen[0].value,
                    "given": given,
                    "total": taken,
                },
            )
        ],
    )


EFFECTS: Mapping[DevCard, Effect] = MappingProxyType(
    {
        DevCard.KNIGHT: knight_effect,
        DevCard.ROAD_BUILDING: road_building_effect,
        DevCard.YEAR_OF_PLENTY: year_of_plenty_effect,
        DevCard.MONOPOLY: monopoly_effect,
    }
)

REQUIREMENTS: Mapping[DevCard, Requirement] = MappingProxyType(
    {
        DevCard.YEAR_OF_PLENTY: _bank_holds,
        DevCard.MONOPOLY: lambda state, action: _named(action, ANNOUNCEMENT),
    }
)
"""What each playable card does, filled in by the cards that implement them (K-042 to K-046).

A card whose effect is not in here is not playable, and that is deliberate: an action that took a
card out of a player's hand and did nothing would be a rule missing *silently*, which is the one
thing this engine does not do. The knight is the first entry, and the four that follow are the
progress cards.
"""


def playable_cards(state: CatanState, player: int) -> tuple[DevCard, ...]:
    """What this player may play right now (RULES.md 4.8, timing rules 1 to 3).

    Four conditions, in the order the rules state them: it is this player's turn, they have not
    already played a card this turn, the card was not bought this turn, and the phase is one of
    the two windows. The window tests are written as what they are - the production phase *before
    the roll*, or the action phase - which is why a production phase whose dice are already rolled
    offers nothing: there is no third window for a card to be played in.
    """
    if player != state.turn or state.played_this_turn[player] >= 1:
        return ()
    if state.phase is Phase.TURN_PRODUCTION and state.dice is not None:
        return ()
    if state.phase not in (Phase.TURN_PRODUCTION, Phase.ACTION):
        return ()
    held = state.dev_cards[player]
    bought = state.bought_this_turn[player]
    return tuple(
        card
        for card in PLAYABLE
        if card in EFFECTS
        and held[CARD_ORDER.index(card)] > bought[CARD_ORDER.index(card)]
        and _has_somewhere_to_play(state, player, card)
    )


def _has_somewhere_to_play(state: CatanState, player: int, card: DevCard) -> bool:
    """The one card whose playability depends on the board rather than on the hand.

    RULES.md 5.6 A-6 item 1: the Road Building card may be played only when the player has a road
    left in supply *and* a legal edge to put it on. A card that could not do anything would be an
    action that took it out of the hand for nothing, and A-6 item 5 says it stays in hand instead.
    """
    if card is not DevCard.ROAD_BUILDING:
        return True
    return state.supply[player].roads > 0 and bool(building.road_targets(state, player))


def choices(state: CatanState, card: DevCard) -> list[dict[str, JsonValue]]:
    """What a card must be told, enumerated - so the offer and the rule agree (FR-17.5).

    The Year of Plenty is the card that needs this: it takes two named resources, and an
    enumeration that named only the card would offer an action the rule then refuses for being
    told nothing. Every pair is offered, duplicates included, limited to what the bank holds
    (A-4, A-5).
    """
    if card is DevCard.MONOPOLY:
        return [{"resources": [item.value]} for item in RESOURCE_ORDER]
    if card is not DevCard.YEAR_OF_PLENTY:
        return [{}]
    pairs: list[dict[str, JsonValue]] = []
    for first in RESOURCE_ORDER:
        for second in RESOURCE_ORDER:
            if second is first and state.bank[RESOURCE_ORDER.index(first)] < 2:
                continue
            if second is not first and (
                state.bank[RESOURCE_ORDER.index(first)] < 1
                or state.bank[RESOURCE_ORDER.index(second)] < 1
            ):
                continue
            pair = sorted(
                [first.value, second.value],
                key=lambda name: next(
                    index for index, item in enumerate(RESOURCE_ORDER) if item.value == name
                ),
            )
            chosen: dict[str, JsonValue] = {"resources": list(pair)}
            if chosen not in pairs:
                pairs.append(chosen)
    return pairs


def play_dev_card(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Play one development card, in one of the two windows it may be played in (FR-13.3, 13.4).

    The refusal names the *reason* rather than saying "you may not": a card bought this turn, a
    second card in the same turn, and a card that is never played at all are three different
    mistakes, and a player who is told which one they made can play the game.
    """
    if action.player != state.turn:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} is not to act; seat {state.turn} is",
                details={"turn": state.turn},
            )
        )
    if state.phase is Phase.TURN_PRODUCTION and state.dice is not None:
        return Rejected(
            Rejection(
                code=WRONG_PHASE,
                message="the roll is already resolved; a card is played before it or later",
                details={"phase": state.phase.value, "dice": list(state.dice or ())},
            )
        )
    if state.phase not in (Phase.TURN_PRODUCTION, Phase.ACTION):
        return Rejected(
            Rejection(
                code=WRONG_PHASE,
                message="a development card is played before the roll or in the action phase",
                details={
                    "phase": state.phase.value,
                    "dice": None if state.dice is None else list(state.dice),
                },
            )
        )
    card = _card(action)
    if isinstance(card, Rejected):
        return card
    if card not in EFFECTS:
        return Rejected(
            Rejection(
                code=CARD_NOT_PLAYABLE,
                message=f"{card.value} is not a card that is played",
                details={"card": card.value, "playable": [kind.value for kind in PLAYABLE]},
            )
        )
    if state.played_this_turn[action.player] >= 1:
        return Rejected(
            Rejection(
                code=ONE_CARD_PER_TURN,
                message="one development card a turn",
                details={
                    "player": action.player,
                    "played": state.played_this_turn[action.player],
                },
            )
        )
    index = CARD_ORDER.index(card)
    held = list(state.dev_cards[action.player])
    if held[index] < 1:
        return Rejected(
            Rejection(
                code=CARD_NOT_PLAYABLE,
                message=f"seat {action.player} does not hold a {card.value}",
                details={"player": action.player, "card": card.value, "held": held[index]},
            )
        )
    if held[index] - state.bought_this_turn[action.player][index] < 1:
        return Rejected(
            Rejection(
                code=CARD_BOUGHT_THIS_TURN,
                message="a card bought this turn may not be played this turn",
                details={"player": action.player, "card": card.value, "held": held[index]},
            )
        )

    requirement = REQUIREMENTS.get(card)
    if requirement is not None:
        refused = requirement(state, action)
        if refused is not None:
            return refused
    if not _has_somewhere_to_play(state, action.player, card):
        return Rejected(
            Rejection(
                code=CARD_NOT_PLAYABLE,
                message=f"a {card.value} could not do anything here",
                details={"card": card.value, "player": action.player},
            )
        )

    held[index] -= 1
    cards = list(state.dev_cards)
    cards[action.player] = tuple(held)
    played = list(state.played_this_turn)
    played[action.player] += 1
    after = replace(state, dev_cards=tuple(cards), played_this_turn=tuple(played))
    after, effects = EFFECTS[card](after, action, rng)
    return Applied(
        state=after,
        events=[
            Event(
                type="dev_card_played",
                payload={"player": action.player, "card": card.value},
            ),
            *effects,
        ],
    )


def _card(action: Action) -> DevCard | Rejected:
    """Read the card an action names, refusing anything that is not a card of this game."""
    value = action.params.get("card")
    if not isinstance(value, str):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message="card must name one of the five development cards",
                details={"card": value},
            )
        )
    try:
        return DevCard(value)
    except ValueError:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"{value!r} is not a development card",
                details={"card": value, "known": [card.value for card in CARD_ORDER]},
            )
        )


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
