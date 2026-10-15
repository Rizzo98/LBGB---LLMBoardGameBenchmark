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
from typing import Any, Final

from lgbg.core.errors import (
    BAD_PARAMS,
    NO_SUCH_REQUEST,
    NOT_YOUR_DECISION,
    WRONG_PHASE,
    Rejection,
)
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import Purpose, RandomSource
from lgbg.core.types import Action, Event, JsonValue
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import (
    NOT_ENOUGH_RESOURCES,
    ROBBER_ALREADY_MOVED,
    ROBBER_SAME_HEX,
    ROBBER_VICTIM_NOT_ADJACENT,
    WRONG_DISCARD_TOTAL,
)
from lgbg.games.catan.state import HAND_LIMIT, NO_OWNER, RESOURCE_ORDER, CatanState, Phase

NOTHING: Final[int] = 0
"""No cards: the amount a hand within the limit owes, and the amount left after a discard."""

ROBBER_STEAL: Final[Purpose] = "robber_steal"
"""Draw D8 of RULES.md section 3.1: which card of the victim's hand is taken."""


def forced_discards(state: CatanState) -> tuple[int, ...]:
    """What each seat owes on a seven: half its hand, rounded down, above the limit (FR-12.1).

    Computed from the hands exactly once, when the seven is rolled. Every later question about
    the discard phase is answered from the result, which is what makes the phase concurrent
    rather than merely claimed to be.
    """
    return tuple(
        total // 2 if (total := sum(hand)) > HAND_LIMIT else NOTHING for hand in state.hands
    )


def move_robber(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Put the robber on a different hex (FR-12.3; RULES.md 4.9 item 4).

    Every hex is a legal destination, the desert included, and the one it is already on is the
    single exception: the rules offer no way to leave the robber where it is, so an engine that
    accepted its current hex would quietly make "move" optional.
    """
    if state.phase is not Phase.ROBBER:
        return Rejected(
            Rejection(
                code=WRONG_PHASE,
                message=f"{action.type!r} is only legal while the robber is being moved",
                details={"phase": state.phase.value},
            )
        )
    if not 0 <= action.player < state.players or action.player != state.turn:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} is not the player who rolled the seven; "
                f"seat {state.turn} is",
                details={"turn": state.turn},
            )
        )
    if state.robber_moved_at == state.phase_index:
        return Rejected(
            Rejection(
                code=ROBBER_ALREADY_MOVED,
                message="the robber has already been moved in this phase",
                details={"to": state.robber, "phase": state.phase.value},
            )
        )
    destination = _destination(action, len(state.board.topology.hexes))
    if isinstance(destination, Rejected):
        return destination
    if destination == state.robber:
        return Rejected(
            Rejection(
                code=ROBBER_SAME_HEX,
                message="the robber must be placed on a different hex",
                details={"from": state.robber},
            )
        )
    moved = replace(state, robber=destination, robber_moved_at=state.phase_index)
    events = [
        Event(
            type="robber_moved",
            payload={"player": action.player, "from": state.robber, "to": destination},
        )
    ]
    candidates = robber_victims(moved)
    if len(candidates) == 1:
        # RULES.md 4.9 item 5: one candidate settles the choice, so the engine does not ask a
        # question whose answer is already determined - it robs them as part of the move.
        moved, stolen = steal(moved, action.player, candidates[0], rng)
        events.append(stolen)
    return Applied(state=moved, events=events)


def choose_robber_victim(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Rob one of the neighbours the mover is choosing between (FR-12.4; RULES.md 4.9 item 5).

    The choice is only open when there is one to make and the robber has already moved: with a
    single candidate the move itself resolved the steal, and naming that candidate here would
    take a second card out of the same hand.
    """
    if state.phase is not Phase.ROBBER:
        return Rejected(
            Rejection(
                code=WRONG_PHASE,
                message=f"{action.type!r} is only legal while the robber is being resolved",
                details={"phase": state.phase.value},
            )
        )
    if not 0 <= action.player < state.players or action.player != state.turn:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} is not the player who moved the robber; "
                f"seat {state.turn} is",
                details={"turn": state.turn},
            )
        )
    candidates = robber_victims(state)
    if state.robber_moved_at != state.phase_index or len(candidates) < 2:
        return Rejected(
            Rejection(
                code=NO_SUCH_REQUEST,
                message="no victim is being chosen: the move settled it, or has not happened yet",
                details={"phase": state.phase.value, "candidates": list(candidates)},
            )
        )
    victim = _victim(action, state)
    if isinstance(victim, Rejected):
        return victim
    if victim not in candidates:
        return Rejected(
            Rejection(
                code=ROBBER_VICTIM_NOT_ADJACENT,
                message=f"seat {victim} has no building on the hex the robber occupies",
                details={"victim": victim, "candidates": list(candidates)},
            )
        )
    robbed, stolen = steal(state, action.player, victim, rng)
    return Applied(state=robbed, events=[stolen])


def steal(
    state: CatanState, thief: int, victim: int, rng: RandomSource
) -> tuple[CatanState, Event]:
    """Take one card, uniformly, out of the victim's hand (RULES.md 4.9 item 6, draw D8).

    The draw is over the *cards*, materialised in canonical resource order and repeated by count,
    not over the resource types: a player holding three wood and one ore loses wood three times
    in four, which is what drawing one card out of a hand physically means. A player holding
    nothing gives nothing and no draw is made - the rules let the mover name such a victim, and
    they get nothing.
    """
    hand = state.hands[victim]
    cards = [
        resource.value for index, resource in enumerate(RESOURCE_ORDER) for _ in range(hand[index])
    ]
    # The card is a resource *name* rather than the enum member, so that the value a replay
    # returns - which is whatever the record holds, and a record holds JSON - is the same kind
    # of thing the live draw returned (FR-2.4).
    taken = rng.choice(cards, purpose=ROBBER_STEAL) if cards else None
    hands = [list(row) for row in state.hands]
    if taken is not None:
        index = next(
            index for index, resource in enumerate(RESOURCE_ORDER) if resource.value == taken
        )
        hands[victim][index] -= 1
        hands[thief][index] += 1
    return (
        replace(state, hands=tuple(tuple(row) for row in hands)),
        Event(
            type="robber_stole",
            payload={"player": thief, "victim": victim, "resource": taken},
        ),
    )


def destinations(state: CatanState) -> tuple[int, ...]:
    """Every hex but the one the robber occupies: the only legal move is a different hex."""
    return tuple(hex_.id for hex_ in state.board.topology.hexes if hex_.id != state.robber)


def robber_victims(state: CatanState) -> tuple[int, ...]:
    """The seats the mover may rob, derived from the board every time it is asked (4.9 item 5).

    The candidates are the players other than the mover who have a settlement or a city on a
    vertex of the hex the robber now occupies. Nothing here is authored and nothing is stored:
    the hex knows its vertices, the vertices know who built on them, and a board that moved a
    hex would move this answer with it. Holding cards is deliberately not part of it - the rules
    let the mover name a victim who holds nothing and get nothing (item 6).
    """
    seats = {
        seat
        for vertex in state.board.topology.vertices_of_hex(state.robber)
        for occupancy in (state.placed.cities, state.placed.settlements)
        if (seat := occupancy[vertex]) != NO_OWNER and seat != state.turn
    }
    return tuple(sorted(seats))


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


def _victim(action: Action, state: CatanState) -> int | Rejected:
    """Read the chosen victim, refusing anything that is not a seat at this table (FR-18.2)."""
    value: Any = action.params.get("victim")
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < state.players:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message="victim must be the seat of one of the players",
                details={"victim": _json(value), "players": state.players},
            )
        )
    return value


def _destination(action: Action, hexes: int) -> int | Rejected:
    """Read the robber's destination, refusing anything the board does not have (FR-18.2)."""
    value: Any = action.params.get("hex")
    if not isinstance(value, int) or isinstance(value, bool):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message="hex must be an integer identifying a hex of this board",
                details={"hex": _json(value)},
            )
        )
    if not 0 <= value < hexes:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"hex {value} is not on this board, which has {hexes}",
                details={"hex": value, "hexes": hexes},
            )
        )
    return value


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
