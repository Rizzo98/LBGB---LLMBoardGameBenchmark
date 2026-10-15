"""When a development card may be played (PRD-v1 FR-13.3, FR-13.4, FR-10.1; RULES.md 4.8).

Three rules, and they are all about *timing* rather than about any card's effect: one card a
turn, never a card bought this turn, and exactly two windows - the production phase before the
roll, or the action phase. There is no third window, which is why the test for it is written as
"a production phase whose dice are already rolled offers nothing": between the roll and its
resolution there is no state to play anything in.

The effects themselves arrive with K-042 to K-046, so this file installs one small double - a
card effect that records that it ran - and says so. Without it, no card is playable at all, which
is asserted too: a card whose effect has not landed is never offered, because an action that took
a card out of a hand and did nothing would be a rule missing silently.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action, Event
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import (
    CARD_BOUGHT_THIS_TURN,
    CARD_NOT_PLAYABLE,
    ONE_CARD_PER_TURN,
)
from lgbg.games.catan.rules import devcards
from lgbg.games.catan.rules.devcards import PLAYABLE, playable_cards
from lgbg.games.catan.state import CARD_ORDER, CatanState, DevCard, Phase
from tests.games.catan_boards import hand, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251222
KNIGHT: Final[int] = CARD_ORDER.index(DevCard.KNIGHT)


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _with_cards(
    state: CatanState,
    seat: int = 0,
    *,
    held: int = 0,
    bought: int = 0,
    played: int = 0,
    phase: Phase = Phase.ACTION,
    dice: tuple[int, int] | None = (3, 4),
) -> CatanState:
    """A position with knights in hand, in whichever window the test is about."""
    cards = [list(row) for row in state.dev_cards]
    cards[seat][KNIGHT] = held
    purchases = [list(row) for row in state.bought_this_turn]
    purchases[seat][KNIGHT] = bought
    turns = list(state.played_this_turn)
    turns[seat] = played
    return replace(
        layout(state, turn=seat),
        dev_cards=tuple(tuple(row) for row in cards),
        bought_this_turn=tuple(tuple(row) for row in purchases),
        played_this_turn=tuple(turns),
        phase=phase,
        dice=dice,
    )


def _play(state: CatanState, card: str = "knight", seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(player=seat, type=phases.PLAY_DEV_CARD, params={"card": card}),
        NullRandomSource(),
    )


def _refusal(state: CatanState, card: str = "knight", seat: int = 0) -> Rejection:
    result = _play(state, card, seat)
    assert isinstance(result, Rejected), "an illegal play must be refused"
    return result.rejection


@pytest.fixture
def an_effect(monkeypatch: pytest.MonkeyPatch) -> list[DevCard]:
    """The declared double: one card effect, which records that it ran.

    The real effects are K-042 to K-046. Until then this file tests the *timing*, and the
    double is the smallest thing that makes a card playable at all.
    """
    ran: list[DevCard] = []

    def effect(state: CatanState, player: int, rng: Any) -> tuple[CatanState, list[Event]]:
        del rng
        ran.append(DevCard.KNIGHT)
        return state, [Event(type="knight_effect_ran", payload={"player": player})]

    monkeypatch.setattr(devcards, "EFFECTS", {DevCard.KNIGHT: effect})
    return ran


def test_the_four_playable_cards_are_playable_and_the_fifth_is_not() -> None:
    """The set of playable kinds is the rule, not an accident of what has been implemented."""
    state = _with_cards(_opening(), held=3)

    assert playable_cards(state, 0) == (DevCard.KNIGHT,)

    cards = [list(row) for row in state.dev_cards]
    for kind in (DevCard.KNIGHT, DevCard.MONOPOLY, DevCard.YEAR_OF_PLENTY, DevCard.ROAD_BUILDING):
        cards[0][CARD_ORDER.index(kind)] = 1
    pending = replace(state, dev_cards=tuple(tuple(row) for row in cards))

    assert set(playable_cards(pending, 0)) == {
        DevCard.KNIGHT,
        DevCard.MONOPOLY,
        DevCard.YEAR_OF_PLENTY,
    }, "road building needs a road in supply and somewhere legal to put it"

    cards[0][CARD_ORDER.index(DevCard.VICTORY_POINT)] = 1
    with_points = replace(state, dev_cards=tuple(tuple(row) for row in cards))
    refusal = _refusal(with_points, card=DevCard.VICTORY_POINT.value)

    assert refusal.code == CARD_NOT_PLAYABLE
    assert DevCard.VICTORY_POINT not in PLAYABLE


def test_a_card_may_be_played_in_the_action_phase(an_effect: list[DevCard]) -> None:
    state = _with_cards(_opening(), held=1)

    played = _play(state)

    assert isinstance(played, Applied)
    assert played.state.dev_cards[0][KNIGHT] == 0, "the card left the hand"
    assert played.state.played_this_turn[0] == 1, "and the turn remembers it"
    assert [event.type for event in played.events] == ["dev_card_played", "knight_effect_ran"]
    assert an_effect == [DevCard.KNIGHT], "the effect of the card was run"
    assert dict(played.events[0].payload) == {"player": 0, "card": "knight"}


def test_a_card_may_be_played_before_the_roll(an_effect: list[DevCard]) -> None:
    """FR-10.1: the production phase offers the card until the dice are rolled."""
    state = _with_cards(_opening(), held=1, phase=Phase.TURN_PRODUCTION, dice=None)

    offered = dict(GAME.pending_decisions(state)[0].context)["actions"]
    played = _play(state)

    assert [str(name) for name in offered] == [phases.ROLL_DICE, phases.PLAY_DEV_CARD]
    assert isinstance(played, Applied)
    assert an_effect == [DevCard.KNIGHT]


def test_there_is_no_window_between_the_roll_and_its_resolution(an_effect: list[DevCard]) -> None:
    """A production phase whose dice are already rolled is not a place to play a card."""
    state = _with_cards(_opening(), held=1, phase=Phase.TURN_PRODUCTION, dice=(3, 4))

    assert playable_cards(state, 0) == ()
    assert _refusal(state).code == WRONG_PHASE


@pytest.mark.parametrize("phase", [Phase.DISCARD, Phase.SETUP_ROUND_1])
def test_a_card_is_not_played_in_another_phase(phase: Phase, an_effect: list[DevCard]) -> None:
    state = _with_cards(_opening(), held=1, phase=phase, dice=None)

    assert _refusal(state).code == WRONG_PHASE


def test_a_finished_game_refuses_a_card_as_finished(an_effect: list[DevCard]) -> None:
    """A terminal game is GAME_OVER, not a phase error: the distinction K-037 pinned."""
    from lgbg.core.errors import GAME_OVER

    state = _with_cards(_opening(), held=1, phase=Phase.TERMINAL, dice=None)

    assert _refusal(state).code == GAME_OVER


def test_only_one_card_a_turn(an_effect: list[DevCard]) -> None:
    """RULES.md 4.8, timing 1: one development card a turn, of any kind."""
    state = _with_cards(_opening(), held=2)

    first = _play(state)
    assert isinstance(first, Applied)
    second = _play(first.state)

    assert isinstance(second, Rejected)
    assert second.rejection.code == ONE_CARD_PER_TURN
    assert dict(second.rejection.details)["played"] == 1
    assert playable_cards(first.state, 0) == ()


def test_a_card_bought_this_turn_waits_for_the_next_one(an_effect: list[DevCard]) -> None:
    """RULES.md 4.8, timing 2: it may not be a card you bought this turn."""
    state = _with_cards(_opening(), held=1, bought=1)

    refusal = _refusal(state)

    assert refusal.code == CARD_BOUGHT_THIS_TURN
    assert playable_cards(state, 0) == ()
    assert state.dev_cards[0][KNIGHT] == 1, "the card is in hand, it simply may not be played yet"


def test_an_older_card_can_be_played_while_a_new_one_cannot(an_effect: list[DevCard]) -> None:
    """Two knights, one bought this turn: the counters are per card, not per turn."""
    state = _with_cards(_opening(), held=2, bought=1)

    assert playable_cards(state, 0) == (DevCard.KNIGHT,)
    played = _play(state)

    assert isinstance(played, Applied)
    assert played.state.dev_cards[0][KNIGHT] == 1


def test_a_victory_point_card_is_never_played(an_effect: list[DevCard]) -> None:
    """RULES.md 4.13 item 3: revealing a victory-point card is not an action, it is winning."""
    state = _with_cards(_opening())
    cards = [list(row) for row in state.dev_cards]
    cards[0][CARD_ORDER.index(DevCard.VICTORY_POINT)] = 1
    state = replace(state, dev_cards=tuple(tuple(row) for row in cards))

    refusal = _refusal(state, card=DevCard.VICTORY_POINT.value)

    assert refusal.code == CARD_NOT_PLAYABLE
    assert DevCard.VICTORY_POINT not in PLAYABLE


def test_a_card_the_player_does_not_hold_cannot_be_played(an_effect: list[DevCard]) -> None:
    state = _with_cards(_opening(), held=0)

    refusal = _refusal(state)

    assert refusal.code == CARD_NOT_PLAYABLE
    assert dict(refusal.details)["held"] == 0


def test_another_seat_cannot_play_the_card(an_effect: list[DevCard]) -> None:
    state = _with_cards(_opening(), held=1, seat=1)

    refusal = _refusal(state, seat=0)

    assert refusal.code == NOT_YOUR_DECISION
    assert playable_cards(state, 1) == (DevCard.KNIGHT,), "and seat 1 may play their own"


@pytest.mark.parametrize("card", ["dragon", "", None, 3])
def test_a_card_that_is_not_a_card_is_a_parameter_error(
    card: Any, an_effect: list[DevCard]
) -> None:
    state = _with_cards(_opening(), held=1)

    refusal = _refusal(state, card=card)

    assert refusal.code == BAD_PARAMS


def test_the_offer_and_the_domain_carry_the_playable_cards(an_effect: list[DevCard]) -> None:
    """FR-17.4 and FR-17.5 together: what is offered is what is playable, and it says so."""
    state = _with_cards(_opening(), held=1)

    offered = [
        dict(action.params)["card"]
        for action in GAME.legal_actions(state, 0)
        if action.type == phases.PLAY_DEV_CARD
    ]
    domains = {domain.type: domain for domain in GAME.action_domains(state, 0)}

    assert offered == [DevCard.KNIGHT.value]
    assert domains[phases.PLAY_DEV_CARD].params["card"].kind == "enum"
    assert list(domains[phases.PLAY_DEV_CARD].params["card"].values or []) == offered
    assert domains[phases.PLAY_DEV_CARD].cost is None, "playing a card costs nothing extra"


def test_the_turn_that_ends_clears_what_was_bought_and_played(an_effect: list[DevCard]) -> None:
    """The counters are the turn's, so a card bought last turn is playable this turn."""
    state = _with_cards(_opening(), held=1, bought=1, phase=Phase.ACTION)
    assert playable_cards(state, 0) == ()

    ended = GAME.apply(state, Action(player=0, type=phases.END_TURN, params={}), NullRandomSource())

    assert isinstance(ended, Applied)
    assert ended.state.bought_this_turn[0][KNIGHT] == 0
    assert ended.state.played_this_turn[0] == 0
    assert playable_cards(replace(ended.state, turn=0), 0) == (DevCard.KNIGHT,)
    assert hand() == (0, 0, 0, 0, 0)
