"""What a build costs, and paying for it (PRD-v1 FR-11.1, FR-11.7; RULES.md 4.7).

The prices are pinned in two documents - RULES.md 4.7 and PRD-v1 Appendix A - and the test below
writes them out a third time, by hand, from the rulebook rather than from the table. A table
asserted against itself proves nothing.

Paying is one function for every build, and it is atomic: the shortfall is computed before a
single card moves, so a player who cannot afford something loses nothing and the rejection says
exactly what was missing. Half-paying is not a failure mode that can be observed, because it is
not a state the code can reach.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig
from lgbg.core.game import Rejected, get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.games.catan.rejections import NOT_ENOUGH_RESOURCES
from lgbg.games.catan.rules.building import (
    CITY,
    COSTS,
    DEVELOPMENT_CARD,
    ROAD,
    SETTLEMENT,
    affordable,
    cost_of,
    pay,
    shortfall,
)
from lgbg.games.catan.state import BANK_PER_RESOURCE, RESOURCE_ORDER, CatanState

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251013
NOTHING: Final[tuple[int, ...]] = (0,) * len(RESOURCE_ORDER)
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _hand(**counts: int) -> tuple[int, ...]:
    """A hand named by resource, so the test cannot be wrong about the canonical order."""
    assert set(counts) <= set(SLOT), f"unknown resource in {sorted(counts)}"
    row = [0] * len(RESOURCE_ORDER)
    for name, count in counts.items():
        row[SLOT[name]] = count
    return tuple(row)


def _holding(state: CatanState, seat: int, **counts: int) -> CatanState:
    """Deal that hand out of the bank, so the position conserves cards like a real one."""
    hand = _hand(**counts)
    bank = tuple(cards - hand[index] for index, cards in enumerate(state.bank))
    assert min(bank) >= 0, "a hand cannot hold cards the bank does not have"
    hands = list(state.hands)
    hands[seat] = hand
    return replace(state, hands=tuple(tuple(row) for row in hands), bank=bank)


def test_the_prices_are_the_ones_the_two_documents_pin() -> None:
    """FR-11.1: written out from RULES.md 4.7 and Appendix A, not from the table under test."""
    assert COSTS[ROAD] == {"brick": 1, "wood": 1}
    assert COSTS[SETTLEMENT] == {"brick": 1, "wood": 1, "wool": 1, "wheat": 1}
    assert COSTS[CITY] == {"wheat": 2, "ore": 3}
    assert COSTS[DEVELOPMENT_CARD] == {"wool": 1, "wheat": 1, "ore": 1}
    assert set(COSTS) == {ROAD, SETTLEMENT, CITY, DEVELOPMENT_CARD}


def test_a_price_is_a_hand_and_is_read_in_the_canonical_order() -> None:
    """A cost and a hand are the same shape, in the same order, or paying would be a reshuffle."""
    assert cost_of(ROAD) == _hand(brick=1, wood=1)
    assert cost_of(SETTLEMENT) == _hand(brick=1, wood=1, wool=1, wheat=1)
    assert cost_of(CITY) == _hand(wheat=2, ore=3)
    assert cost_of(DEVELOPMENT_CARD) == _hand(wool=1, wheat=1, ore=1)
    assert all(len(cost_of(build)) == len(RESOURCE_ORDER) for build in COSTS)


def test_something_the_game_does_not_sell_has_no_price() -> None:
    with pytest.raises(KeyError):
        cost_of("castle")


def test_a_player_with_the_cards_can_afford_it_and_a_player_without_cannot() -> None:
    state = _holding(_opening(), 0, wood=1, brick=1)

    assert affordable(state, 0, ROAD)
    assert not affordable(state, 0, SETTLEMENT)
    assert shortfall(state, 0, ROAD) == {}
    assert shortfall(state, 0, SETTLEMENT) == {"wool": 1, "wheat": 1}


@pytest.mark.parametrize(
    ("build", "short"),
    [
        (ROAD, {"brick": 1, "wood": 1}),
        (SETTLEMENT, {"brick": 1, "wood": 1, "wool": 1, "wheat": 1}),
        (CITY, {"wheat": 2, "ore": 3}),
        (DEVELOPMENT_CARD, {"wool": 1, "wheat": 1, "ore": 1}),
    ],
)
def test_an_empty_hand_is_short_of_exactly_the_price(build: str, short: dict[str, int]) -> None:
    """The shortfall is the price itself when nothing is held, which pins the price twice."""
    assert shortfall(_opening(), 0, build) == short


def test_paying_moves_the_price_from_the_hand_to_the_bank() -> None:
    state = _holding(_opening(), 0, wood=2, brick=2, wool=2, wheat=2, ore=2)
    before = sum(state.bank)

    paid = pay(state, 0, SETTLEMENT)

    assert not isinstance(paid, Rejected)
    after, event = paid
    assert after.hands[0] == _hand(wood=1, brick=1, wool=1, wheat=1, ore=2)
    assert sum(after.bank) == before + 4
    assert event.type == "resources_spent"
    assert dict(event.payload) == {
        "player": 0,
        "build": SETTLEMENT,
        "cost": {"brick": 1, "wood": 1, "wool": 1, "wheat": 1},
    }


def test_paying_exactly_the_price_leaves_an_empty_hand() -> None:
    """The boundary: a hand that holds exactly the cost is a hand that can pay it."""
    state = _holding(_opening(), 2, wheat=2, ore=3)
    assert affordable(state, 2, CITY)

    paid = pay(state, 2, CITY)

    assert not isinstance(paid, Rejected)
    assert paid[0].hands[2] == NOTHING


def test_a_player_who_cannot_afford_it_loses_nothing() -> None:
    """FR-11.7: the rejection names what is missing, and the position is untouched."""
    state = _holding(_opening(), 1, wheat=2, ore=2)
    bank = state.bank

    refused = pay(state, 1, CITY)

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == NOT_ENOUGH_RESOURCES
    assert dict(refused.rejection.details) == {
        "player": 1,
        "build": CITY,
        "missing": {"ore": 1},
        "cost": {"wheat": 2, "ore": 3},
    }
    assert state.hands[1] == _hand(wheat=2, ore=2), "the refusal moved no cards"
    assert state.bank == bank
    for index in range(len(RESOURCE_ORDER)):
        held = sum(hand[index] for hand in state.hands)
        assert state.bank[index] + held == BANK_PER_RESOURCE


def test_paying_never_touches_anybody_elses_hand_or_the_invariants() -> None:
    state = _holding(_holding(_opening(), 0, wood=1, brick=1), 3, wool=4)
    untouched = (state.hands[1], state.hands[2])

    paid = pay(state, 0, ROAD)

    assert not isinstance(paid, Rejected)
    assert (paid[0].hands[1], paid[0].hands[2]) == untouched
    assert GAME.check_invariants(paid[0]) == []
    for index in range(len(RESOURCE_ORDER)):
        held = sum(hand[index] for hand in paid[0].hands)
        assert paid[0].bank[index] + held == BANK_PER_RESOURCE


def test_paying_is_a_pure_function_of_the_position() -> None:
    """FR-2.6: the same position and the same build give the same answer, twice, unchanged."""
    state = _holding(_opening(), 0, wood=1, brick=1)
    before = state

    first = pay(state, 0, ROAD)
    second = pay(state, 0, ROAD)

    assert first == second
    assert state == before, "paying reads the state it was given and does not edit it"
