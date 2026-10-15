"""Maritime trade (PRD-v1 FR-14.2, FR-14.3; RULES.md 4.12.1, A-7).

Three ratios, one shape: a player gives some of one resource and takes one of another, at the rate
their harbours give them. The tests walk all three ratios through the same action - 4:1 with no
harbour, 3:1 with a generic port, 2:1 with the port printed for the resource they are giving away
- because the difference between them is the whole rule and the code path is the same.

Two refusals carry the weight. A trade that offers a number other than the ratio is refused
rather than quietly accepted, because a ratio the player negotiated for themselves is not in the
rules. And a bank that holds none of the wanted resource refuses the trade (A-7), so the exchange
never drives the bank negative.
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
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import (
    BANK_LACKS_RESOURCE,
    NOT_ENOUGH_RESOURCES,
    SAME_RESOURCE_TRADE,
    WRONG_TRADE_RATIO,
)
from lgbg.games.catan.rules.trading import GENERAL, ratio, trades
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    RESOURCE_ORDER,
    CatanState,
    Phase,
)
from tests.games.catan_boards import hand, holding, layout, vertices_of

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260223
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _at_harbour(
    state: CatanState, resource: Resource | None, *, seats: tuple[int, ...] = (0,)
) -> CatanState:
    """A position with a settlement on the harbour printed for this resource, or a generic one."""
    edge = next(
        port.edge
        for port in state.board.ports
        if (port.resource is resource) and (port.resource is None or resource is not None)
    )
    vertex = vertices_of(state, edge)[0]
    return layout(state, settlements=[(vertex, seat) for seat in seats])


def _stocked(state: CatanState, seat: int = 0, **counts: int) -> CatanState:
    return holding(state, seat, **counts)


def _trade(state: CatanState, give: str, count: int, want: str, seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(
            player=seat,
            type=phases.MARITIME_TRADE,
            params={"give_resource": give, "give_count": count, "want_resource": want},
        ),
        NullRandomSource(),
    )


def _refusal(state: CatanState, give: str, count: int, want: str, seat: int = 0) -> Rejection:
    result = _trade(state, give, count, want, seat)
    assert isinstance(result, Rejected), "an illegal trade must be refused"
    return result.rejection


def test_a_player_without_a_harbour_trades_four_to_one() -> None:
    state = _stocked(layout(_opening()), 0, wood=4)

    traded = _trade(state, "wood", GENERAL, "ore")

    assert isinstance(traded, Applied)
    assert traded.state.hands[0] == hand(ore=1)
    assert traded.state.bank[SLOT["wood"]] == BANK_PER_RESOURCE, "the four cards went back"
    assert traded.state.bank[SLOT["ore"]] == BANK_PER_RESOURCE - 1
    assert [event.type for event in traded.events] == ["traded_with_bank"]
    assert dict(traded.events[0].payload) == {
        "player": 0,
        "gave": "wood",
        "count": 4,
        "took": "ore",
    }
    assert GAME.check_invariants(traded.state) == []


def test_a_generic_harbour_trades_three_to_one() -> None:
    state = _stocked(_at_harbour(_opening(), None), 0, wool=3)

    traded = _trade(state, "wool", 3, "brick")

    assert ratio(state, 0, Resource.WOOL) == 3
    assert isinstance(traded, Applied)
    assert traded.state.hands[0] == hand(brick=1)


def test_a_specific_harbour_trades_two_to_one_for_its_own_resource() -> None:
    state = _stocked(_at_harbour(_opening(), Resource.ORE), 0, ore=2)

    traded = _trade(state, "ore", 2, "wheat")

    assert ratio(state, 0, Resource.ORE) == 2
    assert isinstance(traded, Applied)
    assert traded.state.hands[0] == hand(wheat=1)


def test_a_ratio_the_player_does_not_have_is_refused() -> None:
    """A player may not offer three for one when their rate is four: the ratio is not negotiable."""
    state = _stocked(layout(_opening()), 0, wood=4)

    refusal = _refusal(state, "wood", 3, "ore")

    assert refusal.code == WRONG_TRADE_RATIO
    assert dict(refusal.details) == {"give_resource": "wood", "ratio": 4, "offered": 3}
    assert state.hands[0] == hand(wood=4), "and nothing moved"


def test_a_better_ratio_is_not_taken_for_granted_either() -> None:
    """The gate cuts both ways: four cards for one, when the rate is three, is refused too."""
    state = _stocked(_at_harbour(_opening(), None), 0, wool=4)

    refusal = _refusal(state, "wool", 4, "brick")

    assert refusal.code == WRONG_TRADE_RATIO
    assert dict(refusal.details)["ratio"] == 3


def test_trading_a_resource_for_itself_is_refused() -> None:
    """RULES.md 4.12.1 item 2, and S2 Almanac p.14: "You may not trade like resources"."""
    state = _stocked(layout(_opening()), 0, wood=4)

    refusal = _refusal(state, "wood", 4, "wood")

    assert refusal.code == SAME_RESOURCE_TRADE
    assert state.bank[SLOT["wood"]] == BANK_PER_RESOURCE - 4, "the four cards stayed in hand"


def test_the_bank_must_hold_the_wanted_resource() -> None:
    """A-7: if the bank holds none of it, the trade is unavailable rather than allowed."""
    state = _stocked(layout(_opening()), 0, wood=4)
    bank = list(state.bank)
    bank[SLOT["ore"]] = 0
    starved = replace(state, bank=tuple(bank))

    refusal = _refusal(starved, "wood", 4, "ore")

    assert refusal.code == BANK_LACKS_RESOURCE
    assert dict(refusal.details) == {"want_resource": "ore", "bank": 0}
    assert starved.hands[0] == hand(wood=4)
    assert set(trades(starved, 0)) == {
        (Resource.WOOD, 4, Resource.BRICK),
        (Resource.WOOD, 4, Resource.WOOL),
        (Resource.WOOD, 4, Resource.WHEAT),
    }, "and the offer no longer contains the resource the bank cannot pay"


def test_a_player_who_cannot_pay_the_ratio_is_refused() -> None:
    state = _stocked(layout(_opening()), 0, wood=3)

    refusal = _refusal(state, "wood", 4, "ore")

    assert refusal.code == NOT_ENOUGH_RESOURCES
    assert dict(refusal.details)["held"] == 3


def test_an_unknown_resource_is_a_parameter_error() -> None:
    state = _stocked(layout(_opening()), 0, wood=4)

    assert _refusal(state, "gold", 4, "ore").code is not SAME_RESOURCE_TRADE
    assert _refusal(state, "wood", 0, "ore").code is not WRONG_TRADE_RATIO


def test_a_trade_is_not_made_out_of_turn_or_out_of_phase() -> None:
    state = _stocked(layout(_opening()), 0, wood=4)

    elsewhere = _refusal(replace(state, phase=Phase.TURN_PRODUCTION), "wood", 4, "ore")
    other_seat = _refusal(state, "wood", 4, "ore", seat=1)

    assert elsewhere.code == WRONG_PHASE
    assert other_seat.code == NOT_YOUR_DECISION


@pytest.mark.parametrize("detail", ["3", "2"])
def test_the_offered_ratios_are_the_ones_the_harbours_give(detail: str) -> None:
    """FR-17.5: every trade the engine offers is accepted, at the ratio the port implies."""
    resource = None if detail == "3" else Resource.BRICK
    count = 3 if detail == "3" else 2
    state = _stocked(_at_harbour(_opening(), resource), 0, brick=4, wood=4, wool=4, wheat=4)

    offered = [
        action for action in GAME.legal_actions(state, 0) if action.type == phases.MARITIME_TRADE
    ]

    assert offered, "the fixture must offer something"
    assert {dict(action.params)["give_count"] for action in offered} <= {count, GENERAL}
    for action in offered:
        assert isinstance(GAME.apply(state, action, NullRandomSource()), Applied)


def test_the_domain_describes_the_trade_without_enumerating_it() -> None:
    state = _stocked(layout(_opening()), 0, wood=4)

    domains = {domain.type: domain for domain in GAME.action_domains(state, 0)}
    trade = domains[phases.MARITIME_TRADE]

    assert set(trade.params) == {"give_resource", "want_resource", "give_count"}
    assert trade.cost is None, "the bank takes cards, not coins"
    assert trade.params["give_count"].lo == 2
    assert trade.params["give_count"].hi == 4
