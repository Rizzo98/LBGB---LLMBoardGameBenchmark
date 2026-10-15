"""The forced discard, and the state a seven needs (RULES.md 4.9, 4.4; FR-12.1, FR-12.2).

A seven has three consequences, in a fixed order: no hex produces, every player holding more
than seven cards returns half their hand, and then the robber moves and may steal. This module
owns the middle step, and the position the roll leaves behind for it.

The discards are concurrent, and that is a property of the state rather than a promise in this
docstring. The roll computes every amount once and stores it; the phase then asks each eligible
player for *that* amount, so an answer given after another player has already answered is still
an answer to the question the seven asked. Resolving the seats one after another instead would
let a later player decide against a board an earlier one had already changed, which is a
different game (RULES.md 4.4 item 3; ARCHITECTURE.md 7.7).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, Event, JsonValue
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import NOT_ENOUGH_RESOURCES, WRONG_DISCARD_TOTAL
from lgbg.games.catan.state import HAND_LIMIT, RESOURCE_ORDER, CatanState, Phase

NOTHING: Final[int] = 0
"""No cards: the amount a hand within the limit owes, and the amount left after a discard."""


def forced_discards(state: CatanState) -> tuple[int, ...]:
    """What each seat owes on a seven: half its hand, rounded down, above the limit (FR-12.1).

    Computed from the hands exactly once, when the seven is rolled. Every later question about
    the discard phase is answered from the result, which is what makes the phase concurrent
    rather than merely claimed to be.
    """
    return tuple(
        total // 2 if (total := sum(hand)) > HAND_LIMIT else NOTHING for hand in state.hands
    )


def discard_resources(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Return part of a hand to the bank: the forced amount, in any composition (FR-12.1, FR-12.2).

    The composition is the player's own and nobody else's business: the count is public and the
    identities are not (RULES.md 4.9). The event records both, because the record is the god
    view - it is the projection, not the log, that decides what a player may see.
    """
    del rng  # a discard is a decision, not a draw
    if state.phase is not Phase.DISCARD:
        return Rejected(
            Rejection(
                code=WRONG_PHASE,
                message=f"{action.type!r} is only legal while a seven is being resolved",
                details={"phase": state.phase.value},
            )
        )
    if not 0 <= action.player < state.players:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} does not exist in this game",
                details={"players": state.players},
            )
        )
    owed = state.discards_pending[action.player]
    if owed == NOTHING:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} holds no more cards than the limit allows",
                details={"must_discard": NOTHING, "limit": HAND_LIMIT},
            )
        )

    counts = _composition(action)
    if isinstance(counts, Rejected):
        return counts
    total = sum(counts.values())
    if total != owed:
        return Rejected(
            Rejection(
                code=WRONG_DISCARD_TOTAL,
                message=f"this hand returns {owed} cards, not {total}",
                details={"must_discard": owed, "returned": total},
            )
        )
    hand = state.hands[action.player]
    missing = sorted(
        resource.value
        for resource, count in counts.items()
        if count > hand[RESOURCE_ORDER.index(resource)]
    )
    if missing:
        return Rejected(
            Rejection(
                code=NOT_ENOUGH_RESOURCES,
                message="the player does not hold that many of those cards",
                details={"missing": missing, "must_discard": owed},
            )
        )

    returned = list(hand)
    bank = list(state.bank)
    for index, resource in enumerate(RESOURCE_ORDER):
        count = counts.get(resource, NOTHING)
        returned[index] -= count
        bank[index] += count
    hands = list(state.hands)
    hands[action.player] = tuple(returned)
    awaiting = tuple(
        NOTHING if seat == action.player else outstanding
        for seat, outstanding in enumerate(state.discards_pending)
    )
    return Applied(
        state=replace(state, bank=tuple(bank), hands=tuple(hands), discards_pending=awaiting),
        events=[
            Event(
                type="discarded",
                payload={
                    "player": action.player,
                    "count": total,
                    "discarded": {
                        resource.value: counts[resource]
                        for resource in RESOURCE_ORDER
                        if counts.get(resource, NOTHING)
                    },
                },
            )
        ],
    )


def _composition(action: Action) -> dict[Resource, int] | Rejected:
    """Read a discard out of the action, refusing what the declared schema would not carry."""
    counts: dict[Resource, int] = {}
    for name, value in action.params.items():
        resource = _named(name)
        if resource is None:
            return Rejected(
                Rejection(
                    code=BAD_PARAMS,
                    message=f"{name!r} is not a resource of this game",
                    details={"resource": name, "known": _resource_names()},
                )
            )
        if not isinstance(value, int) or isinstance(value, bool) or value < NOTHING:
            return Rejected(
                Rejection(
                    code=BAD_PARAMS,
                    message=f"the count of {name} must be a whole number of cards",
                    details={"resource": name, "count": _json(value)},
                )
            )
        counts[resource] = value
    return counts


def _named(name: str) -> Resource | None:
    return next((resource for resource in RESOURCE_ORDER if resource.value == name), None)


def _resource_names() -> list[JsonValue]:
    return [resource.value for resource in RESOURCE_ORDER]


def _json(value: JsonValue) -> JsonValue:
    """A parameter as the record may carry it: anything else is described, not echoed."""
    if isinstance(value, bool | int | str):
        return value
    return repr(value)
