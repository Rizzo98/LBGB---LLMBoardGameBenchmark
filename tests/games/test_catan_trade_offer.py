"""Player-to-player offers (PRD-v1 FR-14.2, FR-14.3, FR-14.4, FR-14.7; RULES.md 4.12.2).

An offer is the only decision in the game that several players are asked at once, and the only
one that is answered out of turn. What these tests hold it to is the shape of that: validated
before it is broadcast, addressed to everybody holding a card and to nobody else, public to the
table, and over the moment it is withdrawn.

The protocol is *closed*, and FR-14.9 is asserted here as the absence of a channel: an offer
names cards and amounts, and there is nowhere in it to say anything else.
"""

from __future__ import annotations

from typing import Any, Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import GameConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import OFFER_NOT_BACKED, SAME_RESOURCE_TRADE, TRADE_ALREADY_OPEN
from lgbg.games.catan.rules import trading
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState, Phase
from tests.games.catan_boards import holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260404
TABLE: Final[tuple[dict[str, int], ...]] = (
    {"wood": 2, "ore": 1},
    {"wool": 1},
    {"wheat": 2},
    {"brick": 1},
)
"""What each seat holds in the standard fixture: every seat holds something, so every seat
is asked to answer an offer made at this table.
"""


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _table(*hands: dict[str, int]) -> CatanState:
    """The action phase, seat 0 to act, with the named hands dealt out of the bank."""
    state = layout(_opening())
    for seat, cards in enumerate(hands or TABLE):
        state = holding(state, seat, **cards)
    return state


def _action(give: dict[str, int], want: dict[str, int], seat: int = 0) -> Action:
    return Action(
        player=seat,
        type=phases.OFFER_TRADE,
        params={trading.OFFER_GIVE: dict(give), trading.OFFER_WANT: dict(want)},
    )


def _open(state: CatanState, give: dict[str, int], want: dict[str, int], seat: int = 0) -> Any:
    return GAME.apply(state, _action(give, want, seat), NullRandomSource())


def _requests(state: CatanState, kind: str) -> list[int]:
    return [r.player for r in GAME.pending_decisions(state) if r.kind == kind]


def test_only_the_current_player_may_open_an_offer() -> None:
    """FR-14.3: an offer belongs to the turn, and a player out of turn cannot make one."""
    state = _table()

    for seat in (1, 2, 3):
        refused = _open(state, {"wood": 1}, {"ore": 1}, seat=seat)
        assert isinstance(refused, Rejected)
        assert refused.rejection.code == NOT_YOUR_DECISION
        assert phases.OFFER_TRADE not in {a.type for a in GAME.legal_actions(state, seat)}

    opened = _open(state, {"wood": 1}, {"ore": 1})
    assert isinstance(opened, Applied)


def test_an_offer_is_validated_before_it_is_broadcast() -> None:
    """FR-14.7: cards the offerer does not hold are refused, and nobody is asked anything.

    Nothing is opened by a refused offer, so the table never sees a request it could only answer
    with a refusal of its own - which is the difference between one wasted decision and three.
    """
    state = _table()
    before = GAME.pending_decisions(state)

    refused = _open(state, {"ore": 2}, {"wheat": 1})

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == OFFER_NOT_BACKED
    assert refused.rejection.details["unbacked"] == ["ore"]
    assert state.offer is None
    assert trading.responders(state) == ()
    assert GAME.pending_decisions(state) == before, "no request was opened"


def test_an_offer_that_gives_nothing_or_wants_nothing_is_refused() -> None:
    """RULES.md 4.12.2 item 3: an empty side, and an exchange of a card for itself."""
    state = _table()

    for give, want in (({}, {"ore": 1}), ({"wood": 1}, {})):
        refused = _open(state, give, want)
        assert isinstance(refused, Rejected)
        assert refused.rejection.code == BAD_PARAMS

    same = _open(state, {"wood": 2}, {"wood": 2})
    assert isinstance(same, Rejected)
    assert same.rejection.code == SAME_RESOURCE_TRADE


def test_an_offer_that_is_not_backed_by_the_whole_hand_is_refused() -> None:
    """The validation reads the whole hand: a mixed offer is refused if any part is missing."""
    state = _table()

    refused = _open(state, {"wood": 2, "ore": 1, "wool": 1}, {"wheat": 1})

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == OFFER_NOT_BACKED
    assert refused.rejection.details["held"] == {"wood": 2, "ore": 1}


def test_the_offer_reaches_everybody_holding_a_card_and_nobody_else() -> None:
    """FR-14.4: the seats holding a card answer; an empty hand is not asked.

    The offerer is asked something else - how the offer ends - which is why they appear in the
    request list with a different kind rather than not appearing at all.
    """
    state = _table({"wood": 2}, {"wool": 1}, {}, {"brick": 1})

    opened = _open(state, {"wood": 2}, {"ore": 1})

    assert isinstance(opened, Applied)
    assert opened.state.phase is Phase.TRADE_RESPONSE
    assert _requests(opened.state, phases.RESPOND_TRADE) == [1, 3]
    assert _requests(opened.state, phases.CANCEL_TRADE) == [0]
    assert opened.state.turn == state.turn, "the turn is where the offer left it"


def test_the_open_requests_are_addressed_one_to_each_player() -> None:
    """RULES.md 4.4: a request is addressed to one player, and it carries its own identifier.

    A single broadcast request answered by three players would make the record depend on which
    answer arrived first (FR-9.3).
    """
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    assert isinstance(opened, Applied)
    requests = GAME.pending_decisions(opened.state)
    assert [r.player for r in requests] == [0, 1, 2, 3]
    assert len({r.request_id for r in requests}) == len(requests)
    for request in requests:
        assert request.phase == Phase.TRADE_RESPONSE.value
        assert request.schema_ref == request.kind


def test_the_offer_is_public_to_the_table_and_the_answers_are_not() -> None:
    """FR-14.4 and FR-9.6: what was announced is common knowledge; what was answered is private.

    A trade is announced out loud, so an *offer* is information every player has - a responder who
    could not read it could not answer it. The answers go the other way: they are concurrent, so
    seeing them would let a later responder ride on an earlier one.
    """
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    assert isinstance(opened, Applied)
    for seat in range(PLAYERS):
        view = GAME.observe(opened.state, seat)
        assert view["offer"] == {"offerer": 0, "give": {"wood": 2}, "want": {"ore": 1}}
        assert "responses" not in view
    assert GAME.observe_spectator(opened.state)["responses"] == [0, 0, 0, 0]


def test_the_offer_is_announced_and_rendered_as_the_table_would_say_it() -> None:
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    assert isinstance(opened, Applied)
    events = [(event.type, dict(event.payload)) for event in opened.events]
    assert events[0] == (
        "trade_offered",
        {"player": 0, "give": {"wood": 2}, "want": {"ore": 1}},
    )
    assert ("phase_started", {"index": 1, "phase": "trade_response", "turn": 0}) in events
    for seat in range(PLAYERS):
        assert "p0 gives wood 2 for ore 1" in GAME.render(GAME.observe(opened.state, seat))


def test_opening_an_offer_draws_nothing() -> None:
    """FR-2.6: an offer is a decision, and NullRandomSource refuses every draw there is."""
    state = _table()

    assert isinstance(_open(state, {"wood": 2}, {"ore": 1}), Applied)


def test_a_second_offer_is_refused_while_one_is_open() -> None:
    """RULES.md 4.12.2 item 3: one offer at a time, and the refusal says so.

    The refusal is worth its own code because the phase is the response phase by then: the generic
    answer would be 'wrong phase', which is true and tells the player nothing.
    """
    state = _table()
    opened = _open(state, {"wood": 2}, {"ore": 1})

    assert isinstance(opened, Applied)
    again = GAME.apply(opened.state, _action({"wood": 1}, {"wool": 1}), NullRandomSource())

    assert isinstance(again, Rejected)
    assert again.rejection.code == TRADE_ALREADY_OPEN
    assert again.rejection.details == {"offerer": 0}


def test_an_offer_may_only_be_opened_in_the_action_phase() -> None:
    """A trade is an action of the turn, not something done between the roll and the dice."""
    state = _table()
    waiting = layout(_opening(), phase=Phase.TURN_PRODUCTION)
    for seat, cards in enumerate(TABLE):
        waiting = holding(waiting, seat, **cards)

    refused = _open(waiting, {"wood": 2}, {"ore": 1})

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == WRONG_PHASE
    assert refused.rejection.details == {"phase": "turn_production", "expected": "action"}
    assert isinstance(_open(state, {"wood": 2}, {"ore": 1}), Applied)


def test_an_offer_nobody_can_answer_closes_in_the_action_that_made_it() -> None:
    """RULES.md 4.12.2 item 5 read at its limit: with no responders, the round is already over.

    Such an offer is not offered to a driver - there is no decision in it for anybody else - but
    the rule stays total, and leaves the turn exactly where it found it rather than opening a
    phase whose request set nobody can empty.
    """
    state = _table({"wood": 1}, {}, {}, {})

    assert phases.OFFER_TRADE not in {a.type for a in GAME.legal_actions(state, 0)}

    opened = _open(state, {"wood": 1}, {"ore": 1})

    assert isinstance(opened, Applied)
    assert opened.state.offer is None
    assert opened.state.phase is Phase.ACTION
    assert [event.type for event in opened.events] == ["trade_offered", "trade_closed"]
    assert opened.events[1].payload == {"reason": "no_responders"}


def test_the_enumerated_offers_are_accepted_and_the_domain_describes_exactly_them() -> None:
    """FR-17.4 and FR-17.5: the enumeration is a promise, and the description is the same set.

    An offer's parameters are structures rather than identifiers, so the description lists the
    compositions themselves - one set for what is given and one for what is wanted - and this is the
    test that the two views of the surface cannot drift apart.
    """
    state = _table()
    actions = [a for a in GAME.legal_actions(state, 0) if a.type == phases.OFFER_TRADE]

    assert actions, "the fixture must offer offers"
    for action in actions:
        assert isinstance(GAME.apply(state, action, NullRandomSource()), Applied)

    domain = next(d for d in GAME.action_domains(state, 0) if d.type == phases.OFFER_TRADE)
    assert domain.cost is None, "a trade costs the cards it gives, not a price"
    for side in (trading.OFFER_GIVE, trading.OFFER_WANT):
        described = domain.params[side]
        assert described.kind == "id_set"
        assert described.values is not None
        assert [to_canonical_json(v) for v in described.values] == sorted(
            {to_canonical_json(a.params[side]) for a in actions}
        )


def test_every_enumerated_offer_gives_a_kind_the_player_holds() -> None:
    """The enumeration is bounded by the hand, which is what makes it acceptable."""
    state = _table()
    held = state.hands[0]
    slot = {resource.value: index for index, resource in enumerate(RESOURCE_ORDER)}

    offered = [a for a in GAME.legal_actions(state, 0) if a.type == phases.OFFER_TRADE]

    assert offered
    for action in offered:
        give = action.params[trading.OFFER_GIVE]
        assert isinstance(give, dict)
        for name, count in give.items():
            assert 1 <= count <= held[slot[name]]


def test_an_open_offer_is_carried_by_the_encoded_state() -> None:
    """The offer is in the state and not in the machine's head, so a record can be replayed.

    The encoding is part of the corpus: a reader of a record sees the offer in the same words the
    engine used, and the response tally it was answered into.
    """
    opened = _open(_table(), {"wood": 2}, {"ore": 1})

    assert isinstance(opened, Applied)
    blob = GAME.encode_state(opened.state)

    assert blob["offer"] == {"give": [0, 2, 0, 0, 0], "offerer": 0, "want": [0, 0, 0, 0, 1]}
    assert blob["responses"] == [0, 0, 0, 0]
    assert GAME.decode_state(blob) == opened.state
