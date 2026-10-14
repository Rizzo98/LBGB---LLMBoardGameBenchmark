"""Production: what the dice pay (RULES.md 4.5; PRD-v1 FR-10.2, FR-10.3).

Every hex whose number was rolled, and which does not hold the robber, pays: one resource card
per settlement on it and two per city. The distribution is computed for **all players at once
and then applied** (RULES.md 4.5 item 4), which is what makes the bank-shortage rule of 4.6
well defined - a rule about "the players affected" only means something if the demand is known
before anything is handed out.

K-024 replaces the simple cap used here with that rule: until then production never takes the
bank below zero, so conservation holds and no player is paid cards that do not exist.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Final

from lgbg.core.types import Event
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState

SEVEN: Final[int] = 7
SETTLEMENT_YIELD: Final[int] = 1
CITY_YIELD: Final[int] = 2


def produce(state: CatanState, total: int) -> tuple[CatanState, list[Event]]:
    """Pay everybody for the hexes showing this total, which the robber does not block.

    Returns the state and one event describing the whole distribution, so a record explains who
    was paid what rather than merely containing a different hand.
    """
    if total == SEVEN:
        return state, []
    paying = sorted(
        hex_.id
        for hex_ in state.board.topology.hexes
        if state.board.tokens[hex_.id] == total and hex_.id != state.robber
    )

    demand = _demand(state, paying)
    bank = list(state.bank)
    hands = [list(hand) for hand in state.hands]
    granted: dict[str, dict[str, int]] = {}
    shortfall: dict[str, dict[str, int]] = {}
    for seat in sorted(demand):
        for resource in RESOURCE_ORDER:
            wanted = demand[seat].get(resource, 0)
            if wanted == 0:
                continue
            index = RESOURCE_ORDER.index(resource)
            taken = min(wanted, bank[index])
            if taken:
                bank[index] -= taken
                hands[seat][index] += taken
                granted.setdefault(str(seat), {})[resource.value] = taken
            if taken < wanted:
                shortfall.setdefault(str(seat), {})[resource.value] = wanted - taken

    event = Event(
        type="production",
        payload={
            "total": total,
            "hexes": paying,
            "granted": granted,
            "shortfall": shortfall,
        },
    )
    return (
        replace(state, bank=tuple(bank), hands=tuple(tuple(hand) for hand in hands)),
        [event],
    )


def _demand(state: CatanState, paying: list[int]) -> dict[int, Counter[Resource]]:
    """What every player is owed, computed before a single card moves (RULES.md 4.5 item 4)."""
    demand: dict[int, Counter[Resource]] = {}
    for hex_id in paying:
        resource = state.board.resource_of_hex(hex_id)
        if resource is None:
            continue
        for vertex in state.board.topology.vertices_of_hex(hex_id):
            city = state.placed.cities[vertex]
            settlement = state.placed.settlements[vertex]
            seat = city if city != NO_OWNER else settlement
            if seat == NO_OWNER:
                continue
            owed = CITY_YIELD if city != NO_OWNER else SETTLEMENT_YIELD
            demand.setdefault(seat, Counter())[resource] += owed
    return demand
