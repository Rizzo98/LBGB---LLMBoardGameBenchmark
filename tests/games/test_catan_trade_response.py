"""Answers to an offer (PRD-v1 FR-14.4, FR-14.6, FR-14.9; RULES.md 4.12.2).

Three players are asked at once and each answers into their own slot, so what one of them says
cannot move what another one says - asserted here by showing that a responder's view of the game
does not change when somebody else answers it.

The round ends in one of two ways this card owns: everybody declined, and nothing moved; or the
offerer withdrew the offer, and the requests went with it. What happens when somebody *accepts*
belongs to the next card - choosing the partner and moving the cards are one rule (FR-14.5,
FR-14.8) - and until it lands an accepted offer is a loud error rather than a trade that
quietly evaporates.
"""

from __future__ import annotations

from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import (
    ALREADY_RESPONDED,
    INSUFFICIENT_RESOURCES,
    NO_OPEN_OFFER,
    NOT_A_RESPONDER,
)
from lgbg.games.catan.rules import trading
from lgbg.games.catan.rules.trading import ACCEPT, DECLINE, RESPONSE
from lgbg.games.catan.state import (
    RESPONSE_ACCEPT,
    RESPONSE_DECLINE,
    RESPONSE_PENDING,
    CatanState,
    Phase,
)
from tests.games.catan_boards import hand, holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260405
TABLE: Final[tuple[dict[str, int], ...]] = (
    {"wood": 2, "ore": 1},
    {"wool": 1},
    {"wheat": 2},
    {"brick": 1},
)


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _table(*hands: dict[str, int]) -> CatanState:
    state = layout(_opening())
    for seat, cards in enumerate(hands or TABLE):
        state = holding(state, seat, **cards)
    return state


def _open(state: CatanState, give: dict[str, int], want: dict[str, int]) -> CatanState:
    """The table with an offer standing on it: two wood for one ore unless told otherwise."""
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


def _spoken(state: CatanState, seat: int, answer: str) -> Any:
    """Answer as the *rule* sees it, without the machine advancing the phase afterwards.

    The phase has no rule yet for what an accept leads to (see the boundary test below), so the
    recording of an answer is asserted through the rule that records it.
    """
    return trading.respond_trade(state, _answer(seat, answer), NullRandomSource())


def _asked(state: CatanState) -> list[int]:
    return [r.player for r in GAME.pending_decisions(state) if r.kind == phases.RESPOND_TRADE]


def test_every_responder_is_asked_once_and_answers_into_their_own_slot() -> None:
    """FR-14.4: the requests open together, and one player's answer is only their own."""
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    assert _asked(opened) == [1, 2, 3]

    answered = _spoken(opened, 1, DECLINE)

    assert isinstance(answered, Applied)
    assert answered.state.responses == (RESPONSE_PENDING, RESPONSE_DECLINE, 0, 0)
    assert answered.events[0].type == "trade_responded"
    assert dict(answered.events[0].payload) == {"player": 1, "offerer": 0, "response": DECLINE}
    assert _asked(answered.state) == [2, 3], "the answers are concurrent, not turns"


def test_answering_an_offer_does_not_change_what_another_responder_sees() -> None:
    """FR-9.6: a response is made against the position the offer opened in.

    The state does move - the answer is in it - but another responder's *view* of it does not,
    which is the whole content of 'concurrent': no free ride for whoever answers last.
    """
    opened = _open(_table(), {"wood": 2}, {"ore": 1})
    before = GAME.observe(opened, 2)

    answered = _spoken(opened, 1, DECLINE)

    assert isinstance(answered, Applied)
    assert GAME.observe(answered.state, 2) == before
    assert GAME.encode_state(answered.state) != GAME.encode_state(opened)
    assert GAME.observe_spectator(answered.state)["responses"] == [0, 2, 0, 0]


def test_the_offerer_does_not_answer_their_own_offer() -> None:
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    refused = GAME.apply(opened, _answer(0, ACCEPT), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NOT_A_RESPONDER
    assert refused.rejection.details == {"player": 0, "offerer": 0}


def test_a_player_holding_no_cards_is_not_asked_and_cannot_answer() -> None:
    """FR-14.4: the request goes to a player who holds a card, and an empty hand has no answer.

    The engine reads the *count* of a hand, which is public, and not its kinds, which are not: a
    player holding nothing has nothing to trade with.
    """
    state = _table({"wood": 2, "ore": 1}, {"wool": 1}, {}, {"brick": 1})
    opened = _open(state, {"wood": 2}, {"ore": 1})

    assert _asked(opened) == [1, 3]

    refused = GAME.apply(opened, _answer(2, ACCEPT), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NOT_A_RESPONDER


def test_a_responder_who_cannot_pay_for_the_offer_is_still_asked() -> None:
    """FR-14.4 and B-13: the request is not a promise that the trade can be completed.

    Every other seat holds cards and every one of them is asked about an offer that wants a
    resource none of them holds: they may decline, and the accept they cannot honour is refused
    rather than recorded. The request is opened for them all the same, which is what the rules
    pin - the request set is a fact about who holds *cards*, not about who holds the right ones.
    """
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    assert _asked(opened) == [1, 2, 3]
    for seat in (1, 2, 3):
        assert GAME.legal_actions(opened, seat) == [_answer(seat, DECLINE)]
        view = GAME.observe(opened, seat)
        assert view["offer"] == {"offerer": 0, "give": {"wood": 2}, "want": {"ore": 1}}
        assert view["hand"] is not None, "and they can see their own hand to judge it"

    refused = GAME.apply(opened, _answer(2, ACCEPT), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == INSUFFICIENT_RESOURCES


def test_answering_twice_is_refused() -> None:
    """One answer per player per offer: a second one is refused and changes nothing."""
    opened = _open(_table(), {"wood": 2}, {"ore": 1})
    answered = _spoken(opened, 1, DECLINE)

    assert isinstance(answered, Applied)
    refused = GAME.apply(answered.state, _answer(1, ACCEPT), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == ALREADY_RESPONDED


def test_answering_or_withdrawing_with_no_offer_open_is_refused() -> None:
    """An answer needs something to answer: the refusal says what is missing."""
    state = _table()

    for action in (_answer(1, ACCEPT), Action(player=0, type=phases.CANCEL_TRADE, params={})):
        refused = GAME.apply(state, action, NullRandomSource())
        assert isinstance(refused, Rejected)
        assert refused.rejection.code == NO_OPEN_OFFER


def test_an_answer_that_is_neither_accept_nor_decline_is_refused() -> None:
    """FR-14.2 and FR-14.9: two answers, and nowhere to put a sentence."""
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    refused = GAME.apply(opened, _answer(1, "maybe later"), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == BAD_PARAMS
    assert refused.rejection.details == {RESPONSE: "maybe later"}


def test_everybody_declining_closes_the_offer_and_moves_no_cards() -> None:
    """RULES.md 4.12.2 item 5: zero accepts closes the offer, and nothing changes hands.

    The last answer is what closes it - a phase rule reads the state, so the state has to say the
    offer is gone - and closing it is what sends the game back to the turn that was interrupted.
    """
    state = _table()
    opened = _open(state, {"wood": 2}, {"ore": 1})
    running = opened
    for seat in (1, 2):
        step = GAME.apply(running, _answer(seat, DECLINE), NullRandomSource())
        assert isinstance(step, Applied)
        assert step.state.phase is Phase.TRADE_RESPONSE, "the round is not over yet"
        running = step.state

    closed = GAME.apply(running, _answer(3, DECLINE), NullRandomSource())

    assert isinstance(closed, Applied)
    assert closed.state.offer is None
    assert closed.state.responses == (RESPONSE_PENDING,) * PLAYERS, "the tally is forgotten"
    assert closed.state.phase is Phase.ACTION
    assert closed.state.turn == 0, "the turn is the one the offer interrupted"
    assert closed.state.hands == state.hands
    assert closed.state.bank == state.bank
    assert [event.type for event in closed.events] == [
        "trade_responded",
        "trade_closed",
        "phase_started",
    ]
    assert closed.events[1].payload == {"reason": "declined"}
    assert [r.kind for r in GAME.pending_decisions(closed.state)] == [phases.TAKE_TURN]


def test_the_offerer_withdraws_the_offer_and_the_requests_go_with_it() -> None:
    """FR-14.6: an offer is cancellable before it resolves, and cancelling is its own action.

    Nothing is cleaned up by hand: the requests are derived from the state, so the offer being gone
    *is* the requests being withdrawn.
    """
    state = _table()
    opened = _open(state, {"wood": 2}, {"ore": 1})

    cancelled = GAME.apply(
        opened, Action(player=0, type=phases.CANCEL_TRADE, params={}), NullRandomSource()
    )

    assert isinstance(cancelled, Applied)
    assert cancelled.state.offer is None
    assert cancelled.state.phase is Phase.ACTION
    assert [event.type for event in cancelled.events] == ["trade_closed", "phase_started"]
    assert cancelled.events[0].payload == {"reason": "cancelled"}
    assert [r.player for r in GAME.pending_decisions(cancelled.state)] == [0]
    assert GAME.legal_actions(cancelled.state, 1) == [], "seat 1 has nothing to decide"
    assert cancelled.state.hands == state.hands
    assert cancelled.state.bank == state.bank


def test_a_player_who_did_not_make_the_offer_cannot_withdraw_it() -> None:
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    refused = GAME.apply(
        opened, Action(player=2, type=phases.CANCEL_TRADE, params={}), NullRandomSource()
    )

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NOT_YOUR_DECISION
    assert refused.rejection.details == {"offerer": 0}


def test_the_turn_can_offer_again_once_an_offer_is_over() -> None:
    """A closed offer is gone from the state, so the next offer starts from a clean slate."""
    state = _table()
    opened = _open(state, {"wood": 2}, {"ore": 1})
    cancelled = GAME.apply(
        opened, Action(player=0, type=phases.CANCEL_TRADE, params={}), NullRandomSource()
    )
    assert isinstance(cancelled, Applied)
    assert phases.OFFER_TRADE in {a.type for a in GAME.legal_actions(cancelled.state, 0)}

    again = GAME.apply(
        cancelled.state,
        Action(
            player=0,
            type=phases.OFFER_TRADE,
            params={trading.OFFER_GIVE: {"ore": 1}, trading.OFFER_WANT: {"wheat": 1}},
        ),
        NullRandomSource(),
    )

    assert isinstance(again, Applied)
    assert again.state.phase is Phase.TRADE_RESPONSE
    assert again.state.responses == (RESPONSE_PENDING,) * PLAYERS
    assert {r.player for r in GAME.pending_decisions(again.state)} == {0, 1, 2, 3}


def test_an_answer_out_of_the_response_phase_is_refused() -> None:
    state = _table()

    refused = GAME.apply(state, _answer(1, DECLINE), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NO_OPEN_OFFER


def test_an_accept_that_does_not_close_the_round_leaves_the_offer_standing() -> None:
    """One accept is not a resolution: the round ends when the last responder has answered."""
    state = _table({"wood": 2, "ore": 1}, {"wool": 1, "ore": 1}, {"wheat": 2}, {"brick": 1})
    opened = _open(state, {"wood": 2}, {"ore": 1})
    accepted_once = _spoken(opened, 1, ACCEPT)

    assert isinstance(accepted_once, Applied)
    assert accepted_once.state.offer is not None, "the offer waits for the other answers"
    assert accepted_once.state.responses[1] == RESPONSE_ACCEPT
    assert _asked(accepted_once.state) == [2, 3]
    assert accepted_once.state.hands == opened.hands, "and no card has moved yet"

    running = GAME.apply(accepted_once.state, _answer(2, DECLINE), NullRandomSource())
    assert isinstance(running, Applied)
    settled = GAME.apply(running.state, _answer(3, DECLINE), NullRandomSource())

    assert isinstance(settled, Applied)
    assert settled.state.offer is None, "the last answer resolves the round"
    assert settled.state.hands[1] == hand(wood=2, wool=1), "and the trade went through"
