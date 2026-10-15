"""Ports, and what they are worth to a player (RULES.md 4.12.1; PRD-v1 FR-14.1).

The other half of this module is the trade that is *not* with the bank: the structured offer one
player makes to the table and the answers to it (RULES.md 4.12.2; FR-14.2 to FR-14.9). It is the
only decision in the game that several players are asked at once and that one of them asked, and
the only one that is answered out of turn. Neither half negotiates: a ratio comes from the
harbours a player controls and an offer is a plain statement of what is given and what is wanted,
because a benchmark that let players talk to each other would be measuring the talk.

A harbour is not a property of the board; it is a property of a *player's position* on the board.
The rules say a player controls a harbour when they have a settlement or a city on a coastal
intersection that borders it (S2 Almanac p.8), and they say it just as plainly the other way
round: you may not trade through a harbour where somebody else has settled (S5). So what this
module computes is, for each player, the best ratio they may use for each resource - derived from
the board's port placement and their own buildings, never authored.

The derivation is the whole of the rule: four to one by default, three to one if the player holds
a generic port, two to one if they hold the specific port *for the resource they are giving away*
- and a specific port never improves anything else, "not even to 3:1" (S2 Almanac p.9).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Final

from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, Event
from lgbg.games.catan import phases
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import (
    ALREADY_RESPONDED,
    BANK_LACKS_RESOURCE,
    INSUFFICIENT_RESOURCES,
    NO_OPEN_OFFER,
    NOT_A_RESPONDER,
    NOT_AN_ACCEPTOR,
    NOT_ENOUGH_RESOURCES,
    OFFER_NOT_BACKED,
    SAME_RESOURCE_TRADE,
    TRADE_ALREADY_OPEN,
    WRONG_TRADE_RATIO,
)
from lgbg.games.catan.state import (
    NO_OWNER,
    RESOURCE_ORDER,
    RESPONSE_ACCEPT,
    RESPONSE_DECLINE,
    RESPONSE_PENDING,
    CatanState,
    Phase,
    TradeOffer,
)

GENERAL: Final[int] = 4
"""The rate that is always available (S2 p.4: "The 4:1 trade is always possible")."""

GENERIC: Final[int] = 3
SPECIFIC: Final[int] = 2


def controls(state: CatanState, player: int, vertex: int) -> bool:
    """Whether this player has a building on this intersection, settlement or city."""
    return state.placed.settlements[vertex] == player or state.placed.cities[vertex] == player


def port_edges(state: CatanState, player: int) -> tuple[int, ...]:
    """Every harbour edge this player's buildings border, in board order.

    An edge is a harbour if the board says so, and a player controls it if one of the two
    intersections at its ends carries their building. Nothing is stored: a building that is
    placed or upgraded changes the answer on the next call, and a curated board that moved a port
    would move the answer with it.
    """
    topology = state.board.topology
    return tuple(
        port.edge
        for port in state.board.ports
        if any(controls(state, player, vertex) for vertex in topology.vertices_of_edge(port.edge))
    )


def ratios(state: CatanState, player: int) -> dict[Resource, int]:
    """The best exchange rate this player has for each resource (RULES.md 4.12.1 item 3)."""
    best = dict.fromkeys(RESOURCE_ORDER, GENERAL)
    for edge in port_edges(state, player):
        port = next(port for port in state.board.ports if port.edge == edge)
        for resource in RESOURCE_ORDER:
            if port.resource is not None and port.resource is not resource:
                continue
            best[resource] = min(best[resource], port.ratio)
    return best


def ratio(state: CatanState, player: int, resource: Resource) -> int:
    """What this player must give for one card of this resource."""
    return ratios(state, player)[resource]


def can_trade(state: CatanState, player: int) -> bool:
    """Whether maritime trade is available at all: something to give, and something to take.

    A player who owns no harbour may still trade at 4:1, so the condition is about what they
    hold rather than about where they built - and the bank must hold at least one card of some
    other resource, or there would be nothing to take (A-7).
    """
    return bool(trades(state, player))


def trades(state: CatanState, player: int) -> list[tuple[Resource, int, Resource]]:
    """Every exchange this player may make: what to give, how many, and what to take for it."""
    best = ratios(state, player)
    hand = state.hands[player]
    found: list[tuple[Resource, int, Resource]] = []
    for give in RESOURCE_ORDER:
        count = best[give]
        if hand[RESOURCE_ORDER.index(give)] < count:
            continue
        for want in RESOURCE_ORDER:
            if want is give or state.bank[RESOURCE_ORDER.index(want)] < 1:
                continue
            found.append((give, count, want))
    return found


def maritime_trade(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Exchange cards with the bank at the player's best ratio (FR-14.2, FR-14.3; RULES.md 4.12.1).

    The ratio is not negotiated: the player trades at the rate their harbours give them, so an
    action offering a different number is refused rather than quietly honoured. A trade is one
    atomic event - the cards move together or not at all - and no draw is involved in any of it.
    """
    del rng  # an exchange with the bank is a decision, not a draw
    refusal = phases.refuse_unless_acting(state, action, Phase.ACTION)
    if refusal is not None:
        return refusal
    give = _named(action, "give_resource")
    if isinstance(give, Rejected):
        return give
    want = _named(action, "want_resource")
    if isinstance(want, Rejected):
        return want
    if give is want:
        return Rejected(
            Rejection(
                code=SAME_RESOURCE_TRADE,
                message="a trade exchanges one resource for a different one",
                details={"resource": give.value},
            )
        )
    count = _count(action)
    if isinstance(count, Rejected):
        return count
    expected = ratio(state, action.player, give)
    if count != expected:
        return Rejected(
            Rejection(
                code=WRONG_TRADE_RATIO,
                message=f"this player trades {give.value} at {expected}:1, not {count}:1",
                details={"give_resource": give.value, "ratio": expected, "offered": count},
            )
        )
    index = RESOURCE_ORDER.index(give)
    wanted = RESOURCE_ORDER.index(want)
    hand = list(state.hands[action.player])
    if hand[index] < count:
        return Rejected(
            Rejection(
                code=NOT_ENOUGH_RESOURCES,
                message=f"the player does not hold {count} {give.value}",
                details={"give_resource": give.value, "held": hand[index], "asked": count},
            )
        )
    if state.bank[wanted] < 1:
        return Rejected(
            Rejection(
                code=BANK_LACKS_RESOURCE,
                message=f"the bank holds no {want.value}",
                details={"want_resource": want.value, "bank": state.bank[wanted]},
            )
        )

    hand[index] -= count
    hand[wanted] += 1
    hands = list(state.hands)
    hands[action.player] = tuple(hand)
    bank = list(state.bank)
    bank[index] += count
    bank[wanted] -= 1
    return Applied(
        state=replace(state, hands=tuple(hands), bank=tuple(bank)),
        events=[
            Event(
                type="traded_with_bank",
                payload={
                    "player": action.player,
                    "gave": give.value,
                    "count": count,
                    "took": want.value,
                },
            )
        ],
    )


def _named(action: Action, key: str) -> Resource | Rejected:
    """Read a resource name out of an action, refusing anything that is not one."""
    value = action.params.get(key)
    named = next((item for item in RESOURCE_ORDER if item.value == value), None)
    if named is None:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"{key} must name one of the five resources",
                details={key: value if isinstance(value, str) else None},
            )
        )
    return named


def _count(action: Action) -> int | Rejected:
    """Read how many cards an action offers, refusing anything that is not a whole number."""
    value = action.params.get("give_count")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message="give_count must be a whole number of cards",
                details={"give_count": value if isinstance(value, int) else None},
            )
        )
    return value


def _owners_are_known(state: CatanState) -> bool:
    """A guard the tests use: every building on the board belongs to somebody."""
    return all(
        seat == NO_OWNER or 0 <= seat < state.players
        for seat in (*state.placed.settlements, *state.placed.cities)
    )


# --- player-to-player trade: the offer, and the answers to it (RULES.md 4.12.2) ---

OFFER_GIVE: Final[str] = "give"
OFFER_WANT: Final[str] = "want"
RESPONSE: Final[str] = "response"
"""The three parameters of the protocol, named once, so no call site spells them itself."""

ACCEPT: Final[str] = "accept"
DECLINE: Final[str] = "decline"
ANSWERS: Final[tuple[str, ...]] = (ACCEPT, DECLINE)
"""The two answers an offer admits, in the order the requests offer them (FR-14.2)."""


def named(counts: Sequence[int]) -> dict[str, int]:
    """A count vector as resources by name, leaving out the resources it does not name.

    An offer *announces* what it gives and what it wants, and a resource it does not mention is
    not part of the announcement - unlike a hand or the bank, where "none of this" is a fact
    about the position worth writing down.
    """
    return {
        resource.value: counts[index]
        for index, resource in enumerate(RESOURCE_ORDER)
        if counts[index]
    }


def others_holding_cards(state: CatanState, player: int) -> tuple[int, ...]:
    """Every other player holding at least one resource card, in seat order (FR-14.4).

    The condition is about the *count* of a hand, which is public, and never about its kinds,
    which are not: the engine asks a player who holds a card, not a player who holds the
    *right* card, and an accept that turns out to be unaffordable is refused when the offer
    resolves (RULES.md 5.10 B-13).
    """
    return tuple(
        seat for seat in range(state.players) if seat != player and sum(state.hands[seat]) >= 1
    )


def responders(state: CatanState) -> tuple[int, ...]:
    """Every player the rules give a voice in the *open* offer, in seat order (FR-14.4).

    Not the offerer, who did the asking, and not a player holding no cards, who could only
    refuse: a request is worth opening for somebody who can answer it.
    """
    offer = state.offer
    if offer is None:
        return ()
    return others_holding_cards(state, offer.offerer)


def accepted(state: CatanState) -> tuple[int, ...]:
    """The seats that have accepted the open offer, in seat order (FR-14.5)."""
    return tuple(seat for seat in responders(state) if state.responses[seat] == RESPONSE_ACCEPT)


def can_offer(state: CatanState, player: int) -> bool:
    """Whether this player may open an offer: a card to give, somebody to ask, and no offer open.

    Whether the offer could ever *complete* is deliberately not asked - a player may offer
    anything they hold, because the offer is theirs to make - but whether there is anybody to
    answer it is asked, because an offer the whole table can only ignore is not a trade and is
    not worth a decision (FR-9.1, FR-14.4). Whose turn it is and which phase the game is in are
    the caller's business and are judged by the rule itself.
    """
    return (
        state.offer is None
        and sum(state.hands[player]) >= 1
        and bool(others_holding_cards(state, player))
    )


def offers(state: CatanState, player: int) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """The offers a driver is handed, as (what is given, what is wanted) count vectors.

    The rule accepts any exchange backed by the offerer's own cards; this enumerates a *family*
    out of that space rather than all of it. The whole space is a cross product over every
    composition of one hand against every composition of another, which grows with the hand and
    which is mostly offers no player would make; what is here is the trade a table actually
    makes - one kind of card for one kind of card:

    * the offerer gives a kind they hold, in any amount up to everything they hold (FR-14.7);
    * they ask for a kind, in any amount up to the largest hand at the table - the most one
      player could hand over, and a bound readable from the public hand counts (FR-16.2).

    A give and a want of the same kind in the same amount is left out because the rule refuses
    it (RULES.md 4.12.2 item 3). Like every enumeration, this one is a promise: each offer in it
    is accepted (FR-17.5). A model may offer a mixed trade and the rule will judge it; what a
    *driver* picks from is this list.
    """
    if not can_offer(state, player):
        return []
    hand = state.hands[player]
    limit = max((sum(state.hands[seat]) for seat in others_holding_cards(state, player)), default=0)
    found: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for index, held in enumerate(hand):
        for given in range(1, held + 1):
            give = _vector(index, given)
            for other in range(len(RESOURCE_ORDER)):
                for asked in range(1, limit + 1):
                    want = _vector(other, asked)
                    if give != want:
                        found.append((give, want))
    return found


def _vector(index: int, count: int) -> tuple[int, ...]:
    """One resource of one kind, in one amount, as a count vector in canonical order."""
    row = [0] * len(RESOURCE_ORDER)
    row[index] = count
    return tuple(row)


def close_offer(state: CatanState) -> CatanState:
    """The offer is over: nothing is open, and the answers to it are forgotten.

    Closing resets the tally rather than leaving it, because the tally is about *this* offer: a
    stale "accept" left in the state would make the same position hash two different ways
    depending on an offer that is over, and would be read as an answer to the next one.
    """
    return replace(state, offer=None, responses=(RESPONSE_PENDING,) * state.players)


def offer_trade(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Open a structured offer to the table (FR-14.2, FR-14.3, FR-14.7; RULES.md 4.12.2).

    The protocol is closed: an offer names what the offerer gives and what they want, every
    eligible player answers it exactly once, and no free text passes between them anywhere in a
    run (FR-14.9). The offer is validated *before* it is broadcast - a player may not offer
    cards they do not hold - because the alternative sends the table a decision that can never
    complete, spending another player's decision budget on a refusal nobody can tell apart from
    a model's mistake (RULES.md 5.10, B-10).

    Opening an offer moves the game into the response phase instead of leaving it in the action
    phase. That is what makes the answers concurrent and the turn resumable: the offerer's turn
    is waiting in the state, and it is the same turn it was when the game comes back (FR-9.5).
    """
    del rng  # an offer decides something; nothing about it is drawn
    refusal = _refuse_offer(state, action)
    if refusal is not None:
        return refusal
    give = _composition(action, OFFER_GIVE)
    if isinstance(give, Rejected):
        return give
    want = _composition(action, OFFER_WANT)
    if isinstance(want, Rejected):
        return want
    if not any(give) or not any(want):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message="an offer gives something and wants something",
                details={OFFER_GIVE: named(give), OFFER_WANT: named(want)},
            )
        )
    if give == want:
        return Rejected(
            Rejection(
                code=SAME_RESOURCE_TRADE,
                message="an offer must exchange one kind of card for another",
                details={OFFER_GIVE: named(give), OFFER_WANT: named(want)},
            )
        )
    unbacked = [
        resource.value
        for index, resource in enumerate(RESOURCE_ORDER)
        if give[index] > state.hands[action.player][index]
    ]
    if unbacked:
        return Rejected(
            Rejection(
                code=OFFER_NOT_BACKED,
                message="the offerer does not hold the cards the offer gives",
                details={"unbacked": unbacked, "held": named(state.hands[action.player])},
            )
        )

    offered = replace(
        state,
        offer=TradeOffer(offerer=action.player, give=give, want=want),
        responses=(RESPONSE_PENDING,) * state.players,
    )
    announced = Event(
        type="trade_offered",
        payload={"player": action.player, "give": named(give), "want": named(want)},
    )
    if not responders(offered):
        # Everybody else holds nothing, so nobody was asked anything: the round is over the
        # moment it opens and the offer closes in the same action, rather than leaving the
        # offerer to withdraw an offer the table was never asked about (RULES.md 4.12.2 item 5).
        return Applied(
            state=close_offer(offered),
            events=[announced, _closed("no_responders")],
        )
    entered, started = phases.begin(offered, Phase.TRADE_RESPONSE)
    return Applied(state=entered, events=[announced, *started])


def respond_trade(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Answer the open offer (FR-14.4; RULES.md 4.12.2 item 4).

    Answers are concurrent: every eligible player was asked at once and each answers into their
    own slot, so what one player answers cannot move another player's decision, and the record
    does not depend on the order the answers arrived in (FR-9.6, RULES.md 4.4 rule 3).

    An accept is validated against the cards the offer asks of the responder, and refused with
    INSUFFICIENT_RESOURCES if they cannot cover it (B-13). The request is still opened for such
    a player - they are asked, and may decline - but the accept is refused, because a trade the
    other side cannot complete is not a decision worth recording. The validation happens when
    the answer is made rather than when the round resolves, and it refuses exactly the same
    answers to exactly the same cards: no hand can change in between, since the only actions
    open in the phase are the answers themselves and withdrawing the offer.

    The answer that completes the round is also where the round resolves (RULES.md 4.12.2 item
    5): with no accept the offer closes and no card moves, and with exactly one accept the trade
    executes in that same action, atomically. Several acceptors leave the offer standing with
    the choice to the offerer, which is the next rule in this module.
    """
    del rng  # an answer decides something; nothing about it is drawn
    offer = state.offer
    if offer is None:
        return _no_open_offer(action)
    if state.phase is not Phase.TRADE_RESPONSE:
        return _wrong_phase(state, action, Phase.TRADE_RESPONSE)
    if action.player == offer.offerer:
        return _refused_answer(action, offer, "the offerer does not answer their own offer")
    if action.player not in responders(state):
        return _refused_answer(action, offer, "the player holds no resource cards")
    if state.responses[action.player] != RESPONSE_PENDING:
        return Rejected(
            Rejection(
                code=ALREADY_RESPONDED,
                message=f"seat {action.player} has already answered this offer",
                details={"player": action.player, "offerer": offer.offerer},
            )
        )
    answer = _answer(action)
    if isinstance(answer, Rejected):
        return answer
    if answer == RESPONSE_ACCEPT and not can_honour(state, action.player):
        return _cannot_honour(action, offer)

    responses = list(state.responses)
    responses[action.player] = answer
    answered = replace(state, responses=tuple(responses))
    spoken = Event(
        type="trade_responded",
        payload={
            "player": action.player,
            "offerer": offer.offerer,
            "response": ACCEPT if answer == RESPONSE_ACCEPT else DECLINE,
        },
    )
    if _still_waiting(answered):
        return Applied(state=answered, events=[spoken])
    # The round is over. The last answer is what resolves it - a phase rule reads the state, so
    # the state has to say what the round decided - and the two resolutions that land in an
    # action are the two this rule can carry: nobody accepted, and exactly one did.
    acceptors = accepted(answered)
    if not acceptors:
        return Applied(state=close_offer(answered), events=[spoken, _closed("declined")])
    if len(acceptors) > 1:
        # Several players want it, so the offer stays open and the offerer picks the partner
        # (FR-14.5); the engine never picks. That decision is 'choose_partner'.
        return Applied(state=answered, events=[spoken])
    executed = complete_trade(answered, offer, acceptors[0])
    if isinstance(executed, Rejected):
        return executed  # defensive: the acceptor's hand was validated when they accepted
    return Applied(state=executed.state, events=[spoken, *executed.events])


def cancel_trade(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Withdraw the open offer before it resolves (FR-14.6; RULES.md 4.12.2 item 6).

    Cancelling is an action rather than a flag for the same reason everything else is: the
    requests the offer opened are derived from the state, so closing the offer *is* withdrawing
    them, and no player is left holding a decision that is no longer theirs to make.
    """
    del rng  # withdrawing an offer decides something; nothing about it is drawn
    offer = state.offer
    if offer is None:
        return _no_open_offer(action)
    if state.phase is not Phase.TRADE_RESPONSE:
        return _wrong_phase(state, action, Phase.TRADE_RESPONSE)
    if action.player != offer.offerer:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} did not make this offer; seat {offer.offerer} did",
                details={"offerer": offer.offerer},
            )
        )
    return Applied(state=close_offer(state), events=[_closed("cancelled")])


PARTNER: Final[str] = "partner"
"""What the offerer names when several players accepted (FR-14.5)."""


def can_honour(state: CatanState, player: int) -> bool:
    """Whether this player holds everything the open offer asks of them (RULES.md 5.10 B-13).

    The question is about the *want* side of the offer, because that is what the other player
    would have to hand over; what the offerer gives is their own business and was validated when
    the offer was opened. A player who fails this is still asked to answer - they may decline -
    which is what FR-14.4 requires and what keeps the request set out of the hands it is about.
    """
    offer = state.offer
    if offer is None:
        return False
    hand = state.hands[player]
    return all(hand[index] >= offer.want[index] for index in range(len(RESOURCE_ORDER)))


def complete_trade(state: CatanState, offer: TradeOffer, partner: int) -> ApplyResult:
    """Move both sides of the trade at once, and close the offer (FR-14.8; RULES.md 4.12.2 item 7).

    One event and one state: there is no intermediate position in which the offerer has given
    what they promised and not been given what was promised back. A trade done in two steps
    could be interrupted between them, and the position between them is one the rules never
    allow - so it never exists, not even for the length of a function.

    The partner's side is checked here as well as when they accepted. That is not a second rule:
    it is the precondition of the transfer itself, and a transfer that quietly moved what it
    could would be a worse bug than a refusal.
    """
    offerer = offer.offerer
    if not can_honour(state, partner):
        return Rejected(
            Rejection(
                code=INSUFFICIENT_RESOURCES,
                message=f"seat {partner} cannot cover what the offer asks of them",
                details={
                    "partner": partner,
                    "want": named(offer.want),
                    "held": named(state.hands[partner]),
                },
            )
        )
    hands = list(state.hands)
    giving = list(hands[offerer])
    taking = list(hands[partner])
    for index in range(len(RESOURCE_ORDER)):
        giving[index] += offer.want[index] - offer.give[index]
        taking[index] += offer.give[index] - offer.want[index]
    hands[offerer] = tuple(giving)
    hands[partner] = tuple(taking)
    return Applied(
        state=replace(close_offer(state), hands=tuple(hands)),
        events=[
            Event(
                type="trade_completed",
                payload={
                    "offerer": offerer,
                    "partner": partner,
                    "give": named(offer.give),
                    "want": named(offer.want),
                },
            )
        ],
    )


def choose_partner(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """The offerer picks among several acceptors (FR-14.5; RULES.md 4.12.2 item 5).

    The engine never picks. When one player accepted there is nothing to choose and the trade
    has already executed, so this rule only ever runs where a choice exists - and the choice is
    the offerer's, made against a list of the players who accepted and nobody else.
    """
    del rng  # picking a partner decides something; nothing about it is drawn
    offer = state.offer
    if offer is None:
        return _no_open_offer(action)
    if state.phase is not Phase.TRADE_RESPONSE:
        return _wrong_phase(state, action, Phase.TRADE_RESPONSE)
    if action.player != offer.offerer:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} did not make this offer; seat {offer.offerer} did",
                details={"offerer": offer.offerer},
            )
        )
    partner = _partner(action)
    if partner is None:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"{PARTNER} must name the seat the offer is completed with",
                details={PARTNER: None},
            )
        )
    if partner not in accepted(state):
        return Rejected(
            Rejection(
                code=NOT_AN_ACCEPTOR,
                message=f"seat {partner} did not accept this offer",
                details={"partner": partner, "acceptors": list(accepted(state))},
            )
        )
    return complete_trade(state, offer, partner)


def _cannot_honour(action: Action, offer: TradeOffer) -> Rejected:
    """An accept from a player who does not hold what the offer asks of them (B-13)."""
    return Rejected(
        Rejection(
            code=INSUFFICIENT_RESOURCES,
            message="the offer asks this player for cards they do not hold",
            details={"player": action.player, "want": named(offer.want)},
        )
    )


def _partner(action: Action) -> int | None:
    """Read the seat the offerer picked, or None when nothing usable was named."""
    value = action.params.get(PARTNER)
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value


def _refuse_offer(state: CatanState, action: Action) -> Rejected | None:
    """The three refusals an offer meets before its contents are looked at (RULES.md 4.12.2).

    Seat first, then whether an offer is already standing, then the phase. The order earns its
    keep in one place: a game waiting for answers is in the *response* phase, so an offer that
    arrives while one is open would otherwise be refused for the phase - true, and a worse
    answer than saying that an offer is already open.
    """
    if action.player != state.turn:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} may not open an offer; seat {state.turn} is to act",
                details={"turn": state.turn},
            )
        )
    if state.offer is not None:
        return Rejected(
            Rejection(
                code=TRADE_ALREADY_OPEN,
                message="an offer is already open and must resolve or be cancelled first",
                details={"offerer": state.offer.offerer},
            )
        )
    if state.phase is not Phase.ACTION:
        return _wrong_phase(state, action, Phase.ACTION)
    return None


def _composition(action: Action, key: str) -> tuple[int, ...] | Rejected:
    """Read one side of an offer: resources named by the amount offered, in canonical order."""
    value = action.params.get(key)
    if not isinstance(value, Mapping):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"{key} must name resources and how many of each",
                details={key: None},
            )
        )
    counts = [0] * len(RESOURCE_ORDER)
    for name, count in value.items():
        slot = next(
            (index for index, resource in enumerate(RESOURCE_ORDER) if resource.value == name),
            None,
        )
        if slot is None:
            return Rejected(
                Rejection(
                    code=BAD_PARAMS,
                    message=f"{key} names {name!r}, which is not a resource of this game",
                    details={key: sorted(str(named) for named in value)},
                )
            )
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return Rejected(
                Rejection(
                    code=BAD_PARAMS,
                    message=f"{key} names at least one card of every resource it names",
                    details={key: named(tuple(counts))},
                )
            )
        counts[slot] = count
    return tuple(counts)


def _answer(action: Action) -> int | Rejected:
    """Read the answer an action gives, refusing anything that is not one of the two."""
    value = action.params.get(RESPONSE)
    if value == ACCEPT:
        return RESPONSE_ACCEPT
    if value == DECLINE:
        return RESPONSE_DECLINE
    return Rejected(
        Rejection(
            code=BAD_PARAMS,
            message=f"an answer is {ACCEPT!r} or {DECLINE!r}",
            details={RESPONSE: value if isinstance(value, str) else None},
        )
    )


def _still_waiting(state: CatanState) -> bool:
    """Whether any eligible player has still to answer the open offer."""
    return any(state.responses[seat] == RESPONSE_PENDING for seat in responders(state))


def _no_open_offer(action: Action) -> Rejected:
    """Nothing is open, so there is nothing to answer or to withdraw."""
    return Rejected(
        Rejection(
            code=NO_OPEN_OFFER,
            message=f"{action.type!r} needs an open offer, and none is open",
            details={"action_type": action.type},
        )
    )


def _wrong_phase(state: CatanState, action: Action, expected: Phase) -> Rejected:
    """The refusal every action of one phase shares, said the way the machine says it."""
    return Rejected(
        Rejection(
            code=WRONG_PHASE,
            message=f"{action.type!r} is not legal in the {state.phase.value} phase",
            details={"phase": state.phase.value, "expected": expected.value},
        )
    )


def _refused_answer(action: Action, offer: TradeOffer, why: str) -> Rejected:
    """An answer from somebody the offer did not ask."""
    return Rejected(
        Rejection(
            code=NOT_A_RESPONDER,
            message=f"seat {action.player} was not asked to answer this offer: {why}",
            details={"player": action.player, "offerer": offer.offerer},
        )
    )


def _closed(reason: str) -> Event:
    """How an offer ended, announced once, whatever ended it.

    One event for all three endings - withdrawn, declined by everybody, answered by nobody -
    because the fact a reader of the record needs is that the offer is over, and the reason is
    the only thing that differs.
    """
    return Event(type="trade_closed", payload={"reason": reason})
