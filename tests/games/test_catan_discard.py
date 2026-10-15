"""The forced discard on a seven (PRD-v1 FR-9.5, FR-10.5, FR-12.1, FR-12.2; RULES.md 4.4, 4.9).

A seven is the first moment when several players decide at the same time: everybody over the
limit returns half their hand, and nobody may watch anybody else do it. The engine models that
as a phase with one request per eligible player, all opened at once, each carrying the amount
the seven forced - and not as a sequence of private turns, which would let a later player decide
against a board the earlier ones have already changed (RULES.md 4.4 item 3).

The amounts are computed once, when the seven is rolled, and stored in the state. That is what
makes the concurrency structural rather than a promise: a request says what it said when the
phase opened, whatever has been answered since.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify
from lgbg.core.rng import (
    KIND_RANDINT,
    NullRandomSource,
    ReplayRandomSource,
    RngDraw,
    SeededRandomSource,
)
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rejections import NOT_ENOUGH_RESOURCES, WRONG_DISCARD_TOTAL
from lgbg.games.catan.rules.turn import DICE_DIE_1, DICE_DIE_2
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState, Phase

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20250915

NOTHING: Final[tuple[int, ...]] = (0,) * len(RESOURCE_ORDER)
"""A hand holding no cards, in canonical resource order."""


def _hand(**counts: int) -> tuple[int, ...]:
    """A hand named resource by resource.

    The canonical order is pinned by the state tests and by the golden fixture; here the names
    are what the test is about, and a hand written positionally would quietly become a different
    hand the day that order changed (RULES.md section 3). The one naming the hand and the one
    reading it back cannot drift apart.
    """
    assert set(counts) <= {resource.value for resource in RESOURCE_ORDER}
    return tuple(counts.get(resource.value, 0) for resource in RESOURCE_ORDER)


def _opening() -> CatanState:
    """The board and the bank, with the hands to be set by hand: the draft is another card's."""
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _seven() -> ReplayRandomSource:
    """A roll of seven, as the engine itself records one: three and four, by purpose."""
    return ReplayRandomSource(
        [
            RngDraw(purpose=DICE_DIE_1, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=3),
            RngDraw(purpose=DICE_DIE_2, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=4),
        ],
        action="roll_dice",
    )


def _holding(state: CatanState, *hands: tuple[int, ...]) -> CatanState:
    """Deal these hands out of the bank, so the position conserves cards like a real one."""
    assert len(hands) == state.players
    bank = tuple(
        cards - sum(hand[index] for hand in hands) for index, cards in enumerate(state.bank)
    )
    assert min(bank) >= 0, "a hand cannot hold cards the bank does not have"
    return replace(state, hands=tuple(hands), bank=bank)


def _forced(hands: Sequence[tuple[int, ...]]) -> tuple[int, ...]:
    """How much a seven forces, derived here rather than imported (FR-12.1)."""
    return tuple(sum(hand) // 2 if sum(hand) > 7 else 0 for hand in hands)


def _at_the_roll(*hands: tuple[int, ...]) -> CatanState:
    """The position a turn opens from: the board, the hands, and the dice still to come."""
    return replace(_holding(_opening(), *hands), phase=Phase.TURN_PRODUCTION, turn=0)


def _discarding(*hands: tuple[int, ...]) -> CatanState:
    """A rolled seven, with the discards still owed: the position this card is about."""
    return replace(
        _at_the_roll(*hands), phase=Phase.DISCARD, dice=(3, 4), discards_pending=_forced(hands)
    )


def _discard(state: CatanState, seat: int, **counts: int) -> Applied:
    result = GAME.apply(
        state,
        Action(player=seat, type=phases.DISCARD_RESOURCES, params=dict(counts)),
        NullRandomSource(),
    )
    assert isinstance(result, Applied), "a legal discard must be applied, not refused"
    return result


def _refusal(state: CatanState, seat: int, params: dict[str, Any]) -> Rejection:
    result = GAME.apply(
        state, Action(player=seat, type=phases.DISCARD_RESOURCES, params=params), NullRandomSource()
    )
    assert isinstance(result, Rejected), "an illegal discard must be refused"
    return result.rejection


def _roll(state: CatanState) -> Applied:
    result = GAME.apply(state, Action(player=state.turn, type="roll_dice", params={}), _seven())
    assert isinstance(result, Applied)
    return result


def test_a_seven_forces_every_hand_over_the_limit_to_discard() -> None:
    """FR-9.5, FR-10.5: a seven produces nothing, and everybody over seven cards discards."""
    state = _at_the_roll(
        _hand(wood=3, brick=2, ore=4), _hand(wood=4, brick=4), _hand(wood=7), NOTHING
    )

    rolled = _roll(state)

    assert rolled.state.phase is Phase.DISCARD
    assert rolled.state.dice == (3, 4)
    assert rolled.state.discards_pending == (4, 4, 0, 0)
    assert rolled.state.hands == state.hands, "a seven pays no production at all"
    assert [event.type for event in rolled.events] == ["dice_rolled", "phase_started"], (
        "the roll, then the phase that resolves it"
    )
    assert [request.player for request in GAME.pending_decisions(rolled.state)] == [0, 1]


def test_a_hand_of_exactly_seven_cards_is_left_alone() -> None:
    """RULES.md 4.9: more than seven means eight or more, and half is rounded down."""
    hands = (
        _hand(wood=7),
        _hand(brick=8),
        _hand(wool=9),
        _hand(ore=15),
    )

    rolled = _roll(_at_the_roll(*hands))

    assert rolled.state.discards_pending == (0, 4, 4, 7)
    assert rolled.state.hands[3] == (0, 0, 0, 0, 15), "the bank is not a hand limit"
    assert [request.player for request in GAME.pending_decisions(rolled.state)] == [1, 2, 3]


def test_the_requests_open_together_in_seat_order() -> None:
    """One request per eligible player, all at once, each naming its own amount (FR-9.5)."""
    state = _discarding(
        _hand(wood=3, brick=2, ore=4), _hand(wood=4, brick=4), _hand(wood=7), NOTHING
    )

    requests = GAME.pending_decisions(state)

    assert [request.player for request in requests] == [0, 1]
    assert [request.kind for request in requests] == [phases.DISCARD_RESOURCES] * 2
    assert [request.schema_ref for request in requests] == [phases.DISCARD_RESOURCES] * 2
    assert [dict(request.context)["must_discard"] for request in requests] == [4, 4]
    assert len({request.request_id for request in requests}) == 2, "each decision is its own"


def test_the_phase_is_not_a_sequence_of_private_turns() -> None:
    """Both questions are open at once, and the answers may arrive in either order.

    A sequential implementation would open one request, wait for it, and only then open the
    next. Here seat 2 is asked before seat 0 has answered, and its answer is applied against the
    state the phase opened with - the state the rules say it is decided against (RULES.md 4.4
    item 3). The resolution *order* is still seat order, and the engine states it: that is the
    order pending_decisions returns, so a driver that follows it produces the record a game of
    four simultaneous clients produces (item 4).
    """
    state = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, _hand(wood=4, brick=4), NOTHING)

    assert [request.player for request in GAME.pending_decisions(state)] == [0, 2]

    later = _discard(state, 2, wood=2, brick=2)

    assert [request.player for request in GAME.pending_decisions(later.state)] == [0]
    assert later.state.discards_pending == (4, 0, 0, 0)


def test_answering_one_discard_does_not_change_what_the_next_player_owes() -> None:
    """RULES.md 4.4 item 3: every request is answered against the state the phase opened with."""
    state = _discarding(_hand(wood=3, brick=2, ore=4), _hand(wood=4, brick=4), NOTHING, NOTHING)
    before = next(r for r in GAME.pending_decisions(state) if r.player == 1)

    later = _discard(state, 0, wood=3, ore=1)

    after = next(r for r in GAME.pending_decisions(later.state) if r.player == 1)
    assert after == before, "seat 1 answers the question the seven asked, not a later one"
    assert later.state.discards_pending == (0, 4, 0, 0)
    assert later.state.hands[1] == state.hands[1], "and nobody else has moved"


def test_the_phase_closes_only_when_every_request_is_answered() -> None:
    """The phase ends when its request set is empty, and then the robber moves (RULES.md 4.5)."""
    state = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, _hand(wood=4, brick=4), NOTHING)

    halfway = _discard(state, 0, wood=3, ore=1)

    assert halfway.state.phase is Phase.DISCARD, "one answer is not the end of the phase"
    assert [event.type for event in halfway.events] == ["discarded"]

    last = _discard(halfway.state, 2, wood=4)

    assert last.state.phase is Phase.ROBBER
    assert last.state.discards_pending == (0, 0, 0, 0)
    assert [event.type for event in last.events] == ["discarded", "phase_started"]
    assert dict(last.events[-1].payload)["phase"] == "robber"


def test_any_composition_of_the_hand_may_be_returned() -> None:
    """FR-12.2: the player chooses which cards leave, as long as the count is right."""
    hand = _hand(wood=3, brick=2, wheat=3, ore=1)
    state = _discarding(hand, NOTHING, NOTHING, NOTHING)

    spread = _discard(state, 0, wood=1, brick=1, wheat=1, ore=1)
    hoarded = _discard(state, 0, wheat=3, ore=1)
    single = _discard(state, 0, wood=3, wheat=1)

    assert spread.state.hands[0] == _hand(wood=2, brick=1, wheat=2)
    assert hoarded.state.hands[0] == _hand(wood=3, brick=2)
    assert single.state.hands[0] == _hand(brick=2, wheat=2, ore=1)
    for result in (spread, hoarded, single):
        assert sum(result.state.hands[0]) == sum(hand) - 4


def test_a_discard_of_the_wrong_size_is_refused() -> None:
    state = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, NOTHING, NOTHING)

    short = _refusal(state, 0, {"wood": 3})
    long = _refusal(state, 0, {"wood": 3, "brick": 2, "ore": 1})

    assert short.code == WRONG_DISCARD_TOTAL
    assert long.code == WRONG_DISCARD_TOTAL
    assert dict(long.details)["must_discard"] == 4
    assert state.hands[0] == _hand(wood=3, brick=2, ore=4), "a refusal changes nothing"


def test_a_discard_of_cards_the_player_does_not_hold_is_refused() -> None:
    state = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, NOTHING, NOTHING)

    refusal = _refusal(state, 0, {"wood": 3, "wool": 1})

    assert refusal.code == NOT_ENOUGH_RESOURCES
    assert dict(refusal.details)["missing"] == ["wool"]


@pytest.mark.parametrize(
    "params",
    [
        {"gold": 4},
        {"wood": "four"},
        {"wood": True},
        {"wood": -1, "brick": 5},
        {"wood": 4.0},
    ],
)
def test_a_malformed_discard_is_a_parameter_error(params: dict[str, Any]) -> None:
    """FR-18.2: the declared schema is what judges the shape, before any rule logic."""
    state = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, NOTHING, NOTHING)

    refusal = _refusal(state, 0, params)

    assert refusal.code == BAD_PARAMS


def test_a_seat_with_nothing_to_discard_is_refused() -> None:
    state = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, NOTHING, NOTHING)

    refusal = _refusal(state, 1, {"wood": 1})

    assert refusal.code == NOT_YOUR_DECISION
    assert dict(refusal.details)["must_discard"] == 0


def test_a_discard_outside_the_discard_phase_is_refused() -> None:
    once = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, NOTHING, NOTHING)
    state = replace(once, phase=Phase.ACTION)

    refusal = _refusal(state, 0, {"wood": 3, "ore": 1})

    assert refusal.code == WRONG_PHASE
    assert dict(refusal.details)["phase"] == Phase.ACTION.value


def test_the_returned_cards_go_back_to_the_bank() -> None:
    """FR-6.9: a discard moves cards, it does not destroy them."""
    state = _discarding(_hand(wood=3, brick=2, ore=4), NOTHING, NOTHING, NOTHING)
    before = sum(state.bank)

    result = _discard(state, 0, wood=3, ore=1)

    returned = _hand(wood=3, ore=1)
    assert result.state.bank == tuple(
        cards + taken for cards, taken in zip(state.bank, returned, strict=True)
    )
    assert sum(result.state.bank) == before + 4
    assert GAME.check_invariants(result.state) == []


def test_every_enumerated_discard_is_accepted_and_every_other_one_refused() -> None:
    """FR-17.5, for this action: the offered set is exactly the set the rule accepts."""
    hand = _hand(wood=3, brick=2, ore=4)
    state = _discarding(hand, NOTHING, NOTHING, NOTHING)

    offered = GAME.legal_actions(state, 0)

    expected = {
        tuple(counts)
        for counts in itertools.product(*[range(min(held, 4) + 1) for held in hand])
        if sum(counts) == 4
    }
    assert {tuple(action.params.get(r.value, 0) for r in RESOURCE_ORDER) for action in offered} == (
        expected
    ), "every composition of the forced amount, and nothing else"
    for action in offered:
        assert isinstance(GAME.apply(state, action, NullRandomSource()), Applied)
    nobody_owes = replace(state, discards_pending=(0, 0, 0, 0))
    assert GAME.legal_actions(nobody_owes, 0) == [], "and nothing at all when no seven forced it"


def test_the_discard_action_is_declared_in_the_schema() -> None:
    """FR-18.1, FR-18.5: the declared surface and the implementation cannot drift."""
    schema = GAME.action_schema()

    assert phases.DISCARD_RESOURCES in schema
    declared = dict(schema[phases.DISCARD_RESOURCES])
    assert dict(declared["properties"]) == {
        resource.value: {"type": "integer", "minimum": 0} for resource in RESOURCE_ORDER
    }
    assert declared["additionalProperties"] is False


def test_a_seven_through_the_runtime_records_the_transitions(tmp_path: Any) -> None:
    """FR-10.5 end to end: the roll, the empty discard phase, and the robber's turn to wait."""
    run = GameRun(
        GAME,
        RunConfig(
            seed=SEED,
            players=PLAYERS,
            interaction_protocol="decline_only",
            game_config=GameConfig({"board": "fixed:standard_a"}),
        ),
        game_id="g-0001",
        directory=tmp_path,
    )
    for _ in range(16):
        request = run.pending[0]
        assert isinstance(run.submit(GAME.legal_actions(run.state, request.player)[0]), Applied)
    seven = False
    for _ in range(60):
        assert isinstance(
            run.submit(Action(player=run.state.turn, type="roll_dice", params={})), Applied
        )
        if run.state.phase is Phase.ROBBER:
            seven = True
            break
        assert isinstance(
            run.submit(Action(player=run.state.turn, type="end_turn", params={})), Applied
        )
    assert seven, "this seed rolls a seven within sixty turns, and the draft hands nobody eight"
    run.finish()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()
    phases_seen = [record.phase for record in log.phases]

    assert phases_seen[-2:] == ["discard", "robber"], (
        "nobody was over the limit, so the discard phase closed the moment it opened"
    )
    assert verify(log, GAME).rejections == 0
