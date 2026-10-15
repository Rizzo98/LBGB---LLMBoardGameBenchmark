"""What a build costs, and paying for it (RULES.md 4.7; PRD-v1 FR-11.1, FR-11.7).

Every build in this game has the same two halves: a target the rules judge, and a price paid
from the player's hand to the bank. The price is not spread across the four build actions - it
lives here as a table that reads like the rulebook, and paying is one function, so a cost can
only be wrong in one place and a payment can only be atomic in one place.

Paying is atomic by construction: the shortfall is computed before a card moves, so a player who
cannot afford something loses nothing and the rejection carries exactly what was missing. That
is what makes "insufficient resources" a measurable rejection (FR-11.7) rather than a
half-applied position somebody has to unwind.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Final

from lgbg.core.errors import Rejection
from lgbg.core.game import Rejected
from lgbg.core.types import Event
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import NOT_ENOUGH_RESOURCES
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState

ROAD: Final[str] = "road"
SETTLEMENT: Final[str] = "settlement"
CITY: Final[str] = "city"
DEVELOPMENT_CARD: Final[str] = "development_card"
"""The four things a hand can pay for, named the way the actions and the rules name them."""

COSTS: Final[Mapping[str, Mapping[str, int]]] = MappingProxyType(
    {
        ROAD: MappingProxyType({Resource.BRICK.value: 1, Resource.WOOD.value: 1}),
        SETTLEMENT: MappingProxyType(
            {
                Resource.BRICK.value: 1,
                Resource.WOOD.value: 1,
                Resource.WOOL.value: 1,
                Resource.WHEAT.value: 1,
            }
        ),
        CITY: MappingProxyType({Resource.WHEAT.value: 2, Resource.ORE.value: 3}),
        DEVELOPMENT_CARD: MappingProxyType(
            {
                Resource.WOOL.value: 1,
                Resource.WHEAT.value: 1,
                Resource.ORE.value: 1,
            }
        ),
    }
)
"""The prices of RULES.md 4.7 and PRD-v1 Appendix A, written resource by resource.

A price is a *mapping* rather than a five-count tuple so that it can be read, diffed and printed
without knowing the canonical resource order - and it is turned into a hand by cost_of, which is
the one place that order is applied to a price.
"""


def cost_of(build: str) -> tuple[int, ...]:
    """A price as a hand: counts in canonical resource order, which is how a hand is held."""
    wanted = COSTS.get(build)
    if wanted is None:
        raise KeyError(f"{build!r} is not something this game sells; it sells {sorted(COSTS)}")
    return tuple(wanted.get(resource.value, 0) for resource in RESOURCE_ORDER)


def shortfall(state: CatanState, player: int, build: str) -> dict[str, int]:
    """What this player is missing for this build, by resource. Empty when they can afford it."""
    wanted = cost_of(build)
    hand = state.hands[player]
    return {
        resource.value: wanted[index] - hand[index]
        for index, resource in enumerate(RESOURCE_ORDER)
        if wanted[index] > hand[index]
    }


def affordable(state: CatanState, player: int, build: str) -> bool:
    """Whether this player can pay for this build, asked without moving anything."""
    return not shortfall(state, player, build)


def pay(state: CatanState, player: int, build: str) -> tuple[CatanState, Event] | Rejected:
    """Move a build's price from one hand to the bank, or refuse with what is missing (FR-11.7).

    The two halves of the answer are the position and the event: a build that was paid for is a
    fact the record should state, not something a reader has to infer from a smaller hand.
    """
    missing = shortfall(state, player, build)
    if missing:
        return Rejected(
            Rejection(
                code=NOT_ENOUGH_RESOURCES,
                message=(
                    f"seat {player} cannot afford a {build}: short of "
                    + ", ".join(f"{count} {name}" for name, count in missing.items())
                ),
                details={
                    "player": player,
                    "build": build,
                    "missing": missing,
                    "cost": dict(COSTS[build]),
                },
            )
        )

    hand = list(state.hands[player])
    bank = list(state.bank)
    for index, wanted in enumerate(cost_of(build)):
        hand[index] -= wanted
        bank[index] += wanted
    hands = list(state.hands)
    hands[player] = tuple(hand)
    return (
        replace(state, bank=tuple(bank), hands=tuple(hands)),
        Event(
            type="resources_spent",
            payload={"player": player, "build": build, "cost": dict(COSTS[build])},
        ),
    )
