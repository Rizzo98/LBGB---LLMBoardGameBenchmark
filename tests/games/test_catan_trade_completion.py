"""Completing a trade: the partner, and the cards moving (FR-14.5, FR-14.8; RULES.md 4.12.2).

An offer resolves into a trade in two ways, and the difference between them is who decides.
With one acceptor there is nothing to decide - the rules say the trade executes - so it does,
in the action that completes the round, moving both sides at once. With several acceptors the
offerer picks the partner and the engine never picks: the offer stays open until they do.

What is asserted here is that both roads end in the same kind of step: one event, one state,
with no position in between where a card has been given and nothing received.
"""

from __future__ import annotations

from typing import Any, Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import GameConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import NOT_AN_ACCEPTOR
from lgbg.games.catan.rules import trading
from lgbg.games.catan.rules.trading import ACCEPT, DECLINE, RESPONSE
from lgbg.games.catan.state import (
    RESOURCE_ORDER,
    RESPONSE_PENDING,
    CatanState,
    Phase,
)
from tests.games.catan_boards import hand, holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260406
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _table(*hands: dict[str, int]) -> CatanState:
    """The action phase, seat 0 to act, with the named hands dealt out of the bank."""
    state = layout(_opening())
    for seat, cards in enumerate(hands):
        state = holding(state, seat, **cards)
    return state


def _open(state: CatanState, give: dict[str, int], want: dict[str, int]) -> CatanState:
    result = GAME.apply(
        state,
        Action(
            player=0,
            type=phases.OFFER_TRADE,
            params={trading.OFFER_GIVE: give, trading.OFFER_WANT: want},
        ),
        NullRandomSource(),
    )
    assert isinstance(result, Applied)
    opened: CatanState = result.state
    return opened


def _answer(seat: int, answer: str) -> Action:
    return Action(player=seat, type=phases.RESPOND_TRADE, params={RESPONSE: answer})


def _step(state: CatanState, action: Action) -> Any:
    return GAME.apply(state, action, NullRandomSource())


def _applied(state: CatanState, action: Action) -> Any:
    """Apply an action that must be accepted, so a failure is a failure of the action itself."""
    result = _step(state, action)
    assert isinstance(result, Applied), result
    return result


def _bound(seat: int, partner: int) -> Action:
    return Action(player=seat, type=phases.CHOOSE_PARTNER, params={trading.PARTNER: partner})


def _two_acceptors() -> CatanState:
    """One offer, two players who can honour it, and a round that has come to a close.

    Seats 1 and 2 hold the wool the offer asks for; seat 3 holds brick and declines. What the
    answers leave is an offer everybody has answered and that two players want.
    """
    state = _table(
        {"wood": 2, "ore": 1},
        {"wool": 1},
        {"wool": 1, "wheat": 1},
        {"brick": 1},
    )
    opened = _open(state, {"wood": 2}, {"wool": 1})
    answered: CatanState = _applied(opened, _answer(3, DECLINE)).state
    answered = _applied(answered, _answer(1, ACCEPT)).state
    standing: CatanState = _applied(answered, _answer(2, ACCEPT)).state
    return standing


def test_one_acceptor_is_not_a_choice_and_the_trade_executes() -> None:
    """RULES.md 4.12.2 item 5: one accept means the trade executes, with no decision in between.

    The answer that completes the round is where the round resolves, so the trade lands in a
    recorded action like everything else - and the offer is gone with it.
    """
    state = _table({"wood": 2, "ore": 1}, {"wool": 1}, {"wheat": 2}, {"brick": 1})
    opened = _open(state, {"wood": 2}, {"wool": 1})

    running = _applied(opened, _answer(2, DECLINE)).state
    running = _applied(running, _answer(3, DECLINE)).state
    settled = _applied(running, _answer(1, ACCEPT))

    assert settled.state.offer is None
    assert settled.state.responses == (RESPONSE_PENDING,) * PLAYERS
    assert settled.state.phase is Phase.ACTION
    assert settled.state.hands[0] == hand(wool=1, ore=1)
    assert settled.state.hands[1] == hand(wood=2)
    assert settled.state.bank == state.bank, "a trade with a player never touches the bank"
    assert GAME.check_invariants(settled.state) == []
    assert [event.type for event in settled.events] == [
        "trade_responded",
        "trade_completed",
        "phase_started",
    ]
    assert dict(settled.events[1].payload) == {
        "offerer": 0,
        "partner": 1,
        "give": {"wood": 2},
        "want": {"wool": 1},
    }


def test_the_round_resolves_the_same_way_whatever_order_the_answers_arrive_in() -> None:
    """FR-9.3 and RULES.md 4.4: resolution is seat order, and only seat order.

    The two orders below are the same three answers delivered in different sequences. The trade
    lands in a different action - the one that completes the round - but it leaves the same
    position, byte for byte, which is what makes a record independent of delivery order.
    """
    state = _table({"wood": 2, "ore": 1}, {"wool": 1}, {"wheat": 2}, {"brick": 1})
    opened = _open(state, {"wood": 2}, {"wool": 1})

    accept_last = _applied(opened, _answer(2, DECLINE)).state
    accept_last = _applied(accept_last, _answer(3, DECLINE)).state
    accept_last = _applied(accept_last, _answer(1, ACCEPT)).state

    accept_first = _applied(opened, _answer(1, ACCEPT)).state
    accept_first = _applied(accept_first, _answer(3, DECLINE)).state
    accept_first = _applied(accept_first, _answer(2, DECLINE)).state

    assert to_canonical_json(GAME.encode_state(accept_last)) == to_canonical_json(
        GAME.encode_state(accept_first)
    )


def test_the_trade_moves_both_sides_in_one_event() -> None:
    """FR-14.8: the transfer is atomic, and the record shows the whole exchange or none of it.

    One action carries the transfer, and it names both sides: an engine that moved the cards in
    two steps would leave a position in between that the rules never allow, and a record of half
    a trade.
    """
    state = _table({"wood": 2, "ore": 1}, {"wool": 1}, {"wheat": 2}, {"brick": 1})
    opened = _open(state, {"wood": 2}, {"wool": 1})
    running = _applied(opened, _answer(2, DECLINE)).state
    running = _applied(running, _answer(3, DECLINE)).state

    settled = _applied(running, _answer(1, ACCEPT))

    transfers = [event for event in settled.events if event.type == "trade_completed"]
    assert len(transfers) == 1, "one event, whatever moved"
    moved = dict(transfers[0].payload)
    assert moved["give"] == {"wood": 2}
    assert moved["want"] == {"wool": 1}
    assert sum(settled.state.hands[1]) == 2, "seat 1 gave one and took two"
    assert sum(settled.state.hands[0]) == 2, "seat 0 gave two and took one"
    for index in range(len(RESOURCE_ORDER)):
        assert settled.state.bank[index] + sum(hand_[index] for hand_ in settled.state.hands) == (
            state.bank[index] + sum(hand_[index] for hand_ in state.hands)
        ), "no card is created or destroyed"


def test_several_acceptors_leave_the_choice_to_the_offerer() -> None:
    """FR-14.5: with more than one acceptor the engine never picks; the offer waits for the offerer.

    The offerer's request carries what they may do about the offer as a list, exactly as the turn's
    own request carries the actions of the turn.
    """
    standing = _two_acceptors()

    assert standing.phase is Phase.TRADE_RESPONSE
    assert standing.offer is not None, "the offer stands until the offerer decides"
    assert standing.responses == (0, 1, 1, 2)
    assert standing.hands[0] == hand(wood=2, ore=1), "and no card has moved"
    decisions = GAME.pending_decisions(standing)
    assert [request.player for request in decisions] == [0], "only the offerer is asked"
    assert decisions[0].context["actions"] == [phases.CANCEL_TRADE, phases.CHOOSE_PARTNER]
    assert trading.accepted(standing) == (1, 2)


def test_the_offerer_picks_the_partner_and_the_trade_executes() -> None:
    standing = _two_acceptors()

    settled = _applied(standing, _bound(0, 2))

    assert settled.state.offer is None
    assert settled.state.phase is Phase.ACTION
    assert settled.state.hands[0] == hand(wool=1, ore=1)
    assert settled.state.hands[2] == hand(wood=2, wheat=1)
    assert settled.state.hands[1] == hand(wool=1), "the other acceptor keeps their cards"
    assert [event.type for event in settled.events] == ["trade_completed", "phase_started"]
    assert settled.events[0].payload["partner"] == 2


def test_a_player_who_did_not_accept_cannot_be_chosen() -> None:
    standing = _two_acceptors()

    refused = _step(standing, _bound(0, 3))

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NOT_AN_ACCEPTOR
    assert refused.rejection.details == {"partner": 3, "acceptors": [1, 2]}
    assert standing.offer is not None


def test_only_the_offerer_chooses() -> None:
    standing = _two_acceptors()

    refused = _step(standing, _bound(1, 2))

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NOT_YOUR_DECISION
    assert refused.rejection.details == {"offerer": 0}


def test_a_choice_that_names_nobody_is_refused() -> None:
    standing = _two_acceptors()

    refused = _step(standing, Action(player=0, type=phases.CHOOSE_PARTNER, params={}))

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == BAD_PARAMS


def test_the_offerer_can_still_withdraw_when_several_accepted() -> None:
    """RULES.md 4.12.2 item 6: withdrawal is available while the offer is open, before a partner is
    picked - and picking is the only thing that ends it.
    """
    standing = _two_acceptors()

    settled = _applied(standing, Action(player=0, type=phases.CANCEL_TRADE, params={}))

    assert settled.state.offer is None
    assert settled.state.phase is Phase.ACTION
    assert settled.state.hands == standing.hands, "no card moved"
    assert settled.events[0].payload == {"reason": "cancelled"}


def test_the_choice_is_enumerated_and_described_like_every_other_action() -> None:
    """FR-17.4 and FR-17.5: the offerer's choices are an enumeration and a description of one set.

    A choice the enumeration offers must be accepted, and the description of the partner parameter
    must name exactly the players who accepted - not the ones the offerer might have wished for.
    """
    standing = _two_acceptors()
    offered = GAME.legal_actions(standing, 0)
    domains = {domain.type: domain for domain in GAME.action_domains(standing, 0)}

    assert {action.type for action in offered} == {phases.CANCEL_TRADE, phases.CHOOSE_PARTNER}
    for action in offered:
        assert isinstance(_step(standing, action), Applied), action
    partner = domains[phases.CHOOSE_PARTNER].params[trading.PARTNER]
    assert partner.kind == "id_set"
    assert partner.values == [
        action.params[trading.PARTNER] for action in offered if action.type == phases.CHOOSE_PARTNER
    ]
    assert domains[phases.CHOOSE_PARTNER].cost is None, "completing a trade costs nothing extra"


def test_a_completed_trade_replays_from_its_own_encoding() -> None:
    """The state after a trade is a state like any other: encoded, decoded, and continued.

    This is the small form of the replay FR-14.8 asks for - the fixture game with a completed trade
    lands with the slice's golden (K-053) - and it is what catches a transfer that is remembered
    somewhere other than the state.
    """
    standing = _two_acceptors()
    settled = _applied(standing, _bound(0, 1)).state

    restored = GAME.decode_state(GAME.encode_state(settled))
    assert restored == settled

    end = Action(player=0, type=phases.END_TURN, params={})
    assert to_canonical_json(GAME.encode_state(_applied(settled, end).state)) == to_canonical_json(
        GAME.encode_state(_applied(restored, end).state)
    )
