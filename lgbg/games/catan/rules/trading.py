"""Ports, and what they are worth to a player (RULES.md 4.12.1; PRD-v1 FR-14.1).

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

from dataclasses import replace
from typing import Final

from lgbg.core.errors import BAD_PARAMS, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, Event
from lgbg.games.catan import phases
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import (
    BANK_LACKS_RESOURCE,
    NOT_ENOUGH_RESOURCES,
    SAME_RESOURCE_TRADE,
    WRONG_TRADE_RATIO,
)
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState, Phase

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
