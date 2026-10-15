"""Production: what the dice pay (RULES.md 4.5; PRD-v1 FR-10.2, FR-10.3).

Every hex whose number was rolled, and which does not hold the robber, pays: one resource card
per settlement on it and two per city. The distribution is computed for **all players at once
and then applied** (RULES.md 4.5 item 4), which is what makes the bank-shortage rule of 4.6
well defined - a rule about "the players affected" only means something if the demand is known
before anything is handed out.

When the bank cannot cover a resource, the shortage is decided per resource and independently
(RULES.md 4.6, A-5): everyone is paid in full if the bank can cover the whole demand; if only
one player earns that resource, that player takes everything that is left and loses the rest;
and if two or more players earn it, none of them is paid - a reduced amount would silently rank
one settlement above another, and the rulebook gives the shortage no priority order to rank them
by. A shortage of one resource never touches another (FR-10.4; RULES.md correction D-2).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Final

from lgbg.core.errors import WRONG_PHASE, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import Purpose, RandomSource
from lgbg.core.types import Action, Event
from lgbg.games.catan import phases
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rules import robber
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState, Phase

SEVEN: Final[int] = 7
SETTLEMENT_YIELD: Final[int] = 1
CITY_YIELD: Final[int] = 2

DICE_DIE_1: Final[Purpose] = "dice_die_1"
DICE_DIE_2: Final[Purpose] = "dice_die_2"
"""Draws D6 and D7 of RULES.md section 3.1: two independent dice, in that order."""

DIE_FACES: Final[int] = 6


def roll_dice(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Roll the two dice and pay what they produced (FR-10.1, FR-10.2).

    The roll lives here rather than beside the turn's other action because this module is where
    RULES.md 4.5 and draws D6 and D7 belong: the dice are not a fact about a turn, they are the
    input production is a function of. The two draws are independent, never one draw of a total,
    because the distributions differ and a recorded draw has to be replayable semantically.
    """
    refusal = phases.refuse_unless_acting(state, action, Phase.TURN_PRODUCTION)
    if refusal is not None:
        return refusal
    if state.dice is not None:
        return Rejected(
            Rejection(
                code=WRONG_PHASE,
                message="the dice have already been rolled this turn",
                details={"dice": list(state.dice)},
            )
        )

    first = rng.randint(1, DIE_FACES, purpose=DICE_DIE_1)
    second = rng.randint(1, DIE_FACES, purpose=DICE_DIE_2)
    total = first + second
    rolled = replace(state, dice=(first, second))
    paid, production_events = produce(rolled, total)
    # A seven forces the discards. The amounts are computed here, once, and stored: the phase
    # then asks each player for what the seven asked them, rather than recomputing the question
    # against hands that have already shrunk (RULES.md 4.4 item 3).
    ready = replace(paid, discards_pending=robber.forced_discards(paid)) if total == SEVEN else paid
    return Applied(
        state=ready,
        events=[
            Event(
                type="dice_rolled",
                payload={"player": action.player, "dice": [first, second], "total": total},
            ),
            *production_events,
        ],
    )


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
    for index, resource in enumerate(RESOURCE_ORDER):
        owed = {
            seat: owed for seat, counts in sorted(demand.items()) if (owed := counts[resource]) > 0
        }
        if not owed:
            continue
        paid = _distribution(owed, bank[index])
        for seat in sorted(paid):
            amount = paid[seat]
            if amount:
                bank[index] -= amount
                hands[seat][index] += amount
                granted.setdefault(str(seat), {})[resource.value] = amount
        for seat in sorted(owed):
            missing = owed[seat] - paid.get(seat, 0)
            if missing:
                shortfall.setdefault(str(seat), {})[resource.value] = missing

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


def _distribution(owed: dict[int, int], available: int) -> dict[int, int]:
    """What each affected player receives of one resource (RULES.md 4.6 item 2).

    Only the players who earn this resource are affected by its shortage, and the decision is
    taken for all of them at once: full payment, the whole remainder to a lone claimant, or
    nothing at all. There is no third answer that hands out part of a demand.
    """
    if available >= sum(owed.values()):
        return dict(owed)
    if len(owed) == 1:
        return {next(iter(owed)): available}
    return {}


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
