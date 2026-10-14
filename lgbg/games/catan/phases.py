"""The phase machine (ARCHITECTURE.md 5.6, 7.7; PRD-v1 FR-9.1 to FR-9.4).

Phases here do not drive control flow. A phase *produces* decision requests, and it ends when
its request set is empty; the machine then advances and says so in the record. That inversion
is what lets a phase address several players at once, or a player who is out of turn, without
a special case: the request list is the primitive, and "whose turn is it" is an ordinary
consequence of it.

Two rules of the machine matter more than the rest.

- **Resolution order is seat order, and only seat order.** A record produced by four players
  deciding concurrently must be byte-identical to one produced by them deciding in turn, so
  the order cannot depend on arrival - and it cannot, because the machine can only see the
  state.
- **A phase whose card has not landed is an error, not an empty answer.** Returning no
  decisions from a phase nobody has implemented would stall a game silently, which is the
  worst way for a rule to be missing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from lgbg.core.types import PHASE_STARTED_EVENT, DecisionRequest, Event, JsonValue
from lgbg.games.catan.state import NO_OWNER, CatanState, Phase

PLACE_SETTLEMENT: Final[str] = "place_settlement"
PLACE_ROAD: Final[str] = "place_road"
TAKE_TURN: Final[str] = "take_turn"
DISCARD: Final[str] = "discard"


class PhaseError(Exception):
    """The machine was asked for something the current phase cannot give."""


@dataclass(frozen=True, slots=True)
class PhaseRule:
    """One phase: who is asked, and where the game goes once nobody is."""

    requests: Callable[[CatanState], list[DecisionRequest]]
    successor: Callable[[CatanState], Phase] | None
    """None while the transition out of the phase belongs to a card that has not landed."""


def pending_decisions(state: CatanState) -> list[DecisionRequest]:
    """Every open decision, in the order they must be resolved (FR-9.1, FR-9.3)."""
    rule = PHASE_RULES.get(state.phase)
    if rule is None:
        raise PhaseError(
            f"phase {state.phase.value} has no decision rules: its card has not landed, so "
            "there is nothing sensible to answer with"
        )
    return resolution_order(rule.requests(state))


def resolution_order(requests: Sequence[DecisionRequest]) -> list[DecisionRequest]:
    """Seat order, then request identifier: the same order whatever the arrival order was."""
    return sorted(requests, key=lambda request: (request.player, request.request_id))


def advance(state: CatanState) -> tuple[CatanState, list[Event]]:
    """Move to the next phase if this one is closed, announcing the transition (FR-9.4).

    A phase that still has open decisions is left alone: the game is waiting for a player, not
    for a transition.
    """
    if state.phase is Phase.OVER:
        return state, []
    if pending_decisions(state):
        return state, []

    rule = PHASE_RULES.get(state.phase)
    if rule is None or rule.successor is None:
        raise PhaseError(
            f"phase {state.phase.value} has no open decisions and nowhere to go: its "
            "successor belongs to a card that has not landed"
        )
    following = rule.successor(state)
    advanced = replace(state, phase=following, phase_index=state.phase_index + 1)
    return advanced, [
        Event(
            type=PHASE_STARTED_EVENT,
            payload={
                "index": advanced.phase_index,
                "phase": following.value,
                "turn": advanced.turn,
            },
        )
    ]


def _setup_settlement_requests(state: CatanState) -> list[DecisionRequest]:
    """Asked until this selection's settlement is down, which is when settlements lead roads."""
    if _placed(state.placed.settlements) > _placed(state.placed.roads):
        return []
    return [_request(state, state.turn, PLACE_SETTLEMENT)]


def _setup_road_requests(state: CatanState) -> list[DecisionRequest]:
    """Asked while the settlement placed this selection has no road yet."""
    if _placed(state.placed.settlements) == _placed(state.placed.roads):
        return []
    return [_request(state, state.turn, PLACE_ROAD)]


def _turn_requests(state: CatanState) -> list[DecisionRequest]:
    return [_request(state, state.turn, TAKE_TURN)]


def _discard_requests(state: CatanState) -> list[DecisionRequest]:
    """Everybody over the limit is asked at once, in seat order (FR-9.5)."""
    return [
        _request(state, seat, DISCARD, context={"must_discard": owed})
        for seat, owed in enumerate(state.discards_pending)
        if owed > 0
    ]


def _after_setup_road(state: CatanState) -> Phase:
    """After a selection the draft continues until everybody has placed twice."""
    drafted = _placed(state.placed.settlements) >= state.players * 2
    return Phase.TURN_START if drafted else Phase.SETUP_SETTLEMENT


PHASE_RULES: Final[Mapping[Phase, PhaseRule]] = MappingProxyType(
    {
        Phase.SETUP_SETTLEMENT: PhaseRule(
            _setup_settlement_requests, lambda state: Phase.SETUP_ROAD
        ),
        Phase.SETUP_ROAD: PhaseRule(_setup_road_requests, _after_setup_road),
        Phase.TURN_START: PhaseRule(_turn_requests, None),
        Phase.DISCARD: PhaseRule(_discard_requests, None),
    }
)
"""What each implemented phase asks, and where it goes. The rest arrive with their cards."""


def _request(
    state: CatanState,
    player: int,
    kind: str,
    *,
    context: Mapping[str, JsonValue] | None = None,
) -> DecisionRequest:
    """A decision addressed to one player, identified from the state rather than from a clock."""
    return DecisionRequest(
        request_id=f"d{state.phase_index}.{player}",
        player=player,
        kind=kind,
        schema_ref=kind,
        context=dict(context or {}),
        phase=state.phase.value,
    )


def _placed(occupancy: tuple[int, ...]) -> int:
    return sum(1 for seat in occupancy if seat != NO_OWNER)
