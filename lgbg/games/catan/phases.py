"""The phase machine (ARCHITECTURE.md 5.6, 7.7; PRD-v1 FR-9.1 to FR-9.4).

Phases here do not drive control flow. A phase *produces* decision requests, and it ends when
its request set is empty; the machine then advances and says so in the record. That inversion
is what lets a phase address several players at once, or a player who is out of turn, without a
special case: the request list is the primitive, and "whose turn is it" is an ordinary
consequence of it.

The phases and what ends each one are RULES.md section 4.4's table, and nothing else. Two rules
of the machine matter more than the rest.

- **Resolution order is seat order, and only seat order.** A record produced by four players
  deciding concurrently must be byte-identical to one produced by them deciding in turn, so
  the order cannot depend on arrival - and it cannot, because the machine can only see the state.
- **A phase whose card has not landed is an error, not an empty answer.** Returning no
  decisions from a phase nobody has implemented would stall a game silently, which is the worst
  way for a rule to be missing.
- **A phase that closes the moment it opens closes in the same action.** A seven nobody has to
  answer is over before it begins, and the turn moves on to the robber's decision in the record
  that made it so.

The machine also holds the two things that are statements about phases rather than about any one
rule: the refusal every action of a turn shares (right seat, right phase), and the action that is
nothing but a transition, which is ending the turn.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from lgbg.core.errors import NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import PHASE_STARTED_EVENT, Action, DecisionRequest, Event, JsonValue
from lgbg.games.catan.rules import building, robber
from lgbg.games.catan.state import NO_OWNER, CatanState, Phase

PLACE_SETTLEMENT: Final[str] = "place_settlement"
PLACE_ROAD: Final[str] = "place_road"
TAKE_TURN: Final[str] = "take_turn"
ROLL_DICE: Final[str] = "roll_dice"
END_TURN: Final[str] = "end_turn"
DISCARD_RESOURCES: Final[str] = "discard_resources"
"""The request a forced discard is answered with, one per eligible player (RULES.md 4.4)."""
BUILD_ROAD: Final[str] = "build_road"
MOVE_ROBBER: Final[str] = "move_robber"
CHOOSE_ROBBER_VICTIM: Final[str] = "choose_robber_victim"
"""The robber phase's two steps: it moves, and then somebody is robbed (RULES.md 4.9)."""


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


def begin(state: CatanState, phase: Phase) -> tuple[CatanState, list[Event]]:
    """Enter a phase. The only place a transition happens, and it always announces itself.

    One function, so a phase cannot be entered without a `phase_started` event and a phase
    record (FR-9.4) - not by advancing, and not by an action that moves the game on.
    """
    entered = replace(state, phase=phase, phase_index=state.phase_index + 1)
    return entered, [
        Event(
            type=PHASE_STARTED_EVENT,
            payload={
                "index": entered.phase_index,
                "phase": phase.value,
                "turn": entered.turn,
            },
        )
    ]


def advance(state: CatanState) -> tuple[CatanState, list[Event]]:
    """Move past every phase that is closed, announcing each transition (FR-9.4).

    A phase that still has open decisions is left alone: the game is waiting for a player, not
    for a transition. A phase can also be closed the moment it opens - a seven nobody has to
    answer - and then it is not a resting place either, so the walk continues into the next
    phase in the same action. A phase whose card has not landed ends the walk instead of ending
    the game: entering it is a transition like any other, and asking it for decisions is what
    fails loudly (see 'pending_decisions').
    """
    if state.phase is Phase.TERMINAL:
        return state, []
    _check_this_phase_can_move_on(state)

    events: list[Event] = []
    current = state
    while current.phase is not Phase.TERMINAL:
        rule = PHASE_RULES.get(current.phase)
        if rule is None or rule.successor is None or rule.requests(current):
            break
        current, announced = begin(current, rule.successor(current))
        events.extend(announced)
    return current, events


def _check_this_phase_can_move_on(state: CatanState) -> None:
    """An action may not leave the game in a phase that is closed and cannot be left.

    That is the shape of a missing card, and it is worth an error rather than a game that
    quietly waits for a transition nobody can make.
    """
    rule = PHASE_RULES.get(state.phase)
    if rule is None:
        raise PhaseError(
            f"phase {state.phase.value} has no decision rules: its card has not landed, so "
            "there is nothing sensible to answer with"
        )
    if rule.requests(state) or rule.successor is not None:
        return
    raise PhaseError(
        f"phase {state.phase.value} has no open decisions and nowhere to go: its successor "
        "belongs to a card that has not landed"
    )


def refuse_unless_acting(state: CatanState, action: Action, phase: Phase) -> Rejected | None:
    """The two refusals every action of a turn shares: the right seat, and the right phase.

    It lives with the machine rather than with any one rule because it is a statement about
    phases: an action belongs to one phase, and to the seat whose turn it is (FR-9.2).
    """
    if action.player != state.turn:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} is not to act; seat {state.turn} is",
                details={"turn": state.turn},
            )
        )
    if state.phase is not phase:
        return Rejected(
            Rejection(
                code=WRONG_PHASE,
                message=f"{action.type!r} is not legal in the {state.phase.value} phase",
                details={"phase": state.phase.value, "expected": phase.value},
            )
        )
    return None


def end_turn(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Close the turn and open the next seat's production phase (RULES.md 4.4 rule 1).

    The only action in the game that is nothing but a transition, which is why it is here and
    not in a rule module: it is the phase machine being asked to move on, and it says so with a
    turn_ended event beside the transition's own announcement.
    """
    del rng  # ending a turn decides nothing and draws nothing
    refusal = refuse_unless_acting(state, action, Phase.ACTION)
    if refusal is not None:
        return refusal

    following = (action.player + 1) % state.players
    closed = replace(
        state,
        turn=following,
        round=state.round + (1 if following == 0 else 0),
        dice=None,
        discards_pending=(0,) * state.players,
        played_this_turn=(0,) * state.players,
    )
    entered, announced = begin(closed, Phase.TURN_PRODUCTION)
    return Applied(
        state=entered,
        events=[
            Event(
                type="turn_ended",
                payload={"player": action.player, "next_player": following, "round": entered.round},
            ),
            *announced,
        ],
    )


def _setup_requests(state: CatanState) -> list[DecisionRequest]:
    """One seat at a time: a settlement, and then the road attached to it (RULES.md 4.3).

    Both rounds share this generator. The round is the phase's own name and the progress is the
    pieces on the board, so there is no second code path - and the phase closes when the round's
    steps are done, not after every placement.
    """
    limit = state.players if state.phase is Phase.SETUP_ROUND_1 else state.players * 2
    settlements = _placed(state.placed.settlements)
    roads = _placed(state.placed.roads)
    if settlements > roads:
        return [_request(state, state.turn, PLACE_ROAD)]
    if settlements >= limit:
        return []
    return [_request(state, state.turn, PLACE_SETTLEMENT)]


def _after_setup_round_one(state: CatanState) -> Phase:
    """Round one is over once every seat has one settlement and one road."""
    drafted = _placed(state.placed.settlements) >= state.players
    return Phase.SETUP_ROUND_2 if drafted else Phase.SETUP_ROUND_1


def _after_setup_round_two(state: CatanState) -> Phase:
    """The draft ends into the first seat's production phase (RULES.md 4.3 item 9)."""
    return Phase.TURN_PRODUCTION


def _turn_production_requests(state: CatanState) -> list[DecisionRequest]:
    """The roll, once the dice are still unrolled this turn (FR-10.1).

    `play_dev_card` is offered here too, before the roll, and its action arrives with K-042;
    until then the roll is the only thing the request can be answered with, and the context says
    so rather than leaving a model to guess.
    """
    if state.dice is not None:
        return []
    return [
        _request(
            state,
            state.turn,
            TAKE_TURN,
            schema_ref=ROLL_DICE,
            context={"actions": [ROLL_DICE]},
        )
    ]


def _after_turn_production(state: CatanState) -> Phase:
    """A seven skips production and opens the discard phase; anything else opens the turn."""
    if state.dice is None:
        raise PhaseError("the production phase ended without a roll")
    return Phase.DISCARD if sum(state.dice) == 7 else Phase.ACTION


def _action_requests(state: CatanState) -> list[DecisionRequest]:
    """The whole action phase, as one request that offers the actions which can be taken now.

    The offered list is built from the rules rather than written down: a build appears when the
    player has the piece, the price and somewhere to put it (FR-11.5). The complete enumeration
    of *targets*, and the parameter domains, belong to the action surface (K-034); what this
    request says is which actions are on the table.
    """
    offered = [name for name in (BUILD_ROAD, END_TURN) if _can_take(state, name)]
    return [
        _request(
            state,
            state.turn,
            TAKE_TURN,
            schema_ref=END_TURN,
            context={"actions": offered},
        )
    ]


def _can_take(state: CatanState, action: str) -> bool:
    """Whether one action of the action phase can be taken right now."""
    if action == BUILD_ROAD:
        return building.can_build_road(state, state.turn)
    return True


def _discard_requests(state: CatanState) -> list[DecisionRequest]:
    """Everybody over the limit is asked at once, in seat order (FR-9.5).

    The amount comes from the state and not from the hands, so the phase asks what the seven
    forced rather than what a shrinking hand could still afford (RULES.md 4.4 item 3).
    """
    return [
        _request(state, seat, DISCARD_RESOURCES, context={"must_discard": owed})
        for seat, owed in enumerate(state.discards_pending)
        if owed > 0
    ]


def _after_discard(state: CatanState) -> Phase:
    """The robber moves once everybody has returned their cards (RULES.md 4.5 item 5)."""
    del state
    return Phase.ROBBER


def _robber_requests(state: CatanState) -> list[DecisionRequest]:
    """The mover's two steps, in order: move the robber, then rob somebody (RULES.md 4.9).

    Which step is open is read from the state and not remembered by the machine: the move
    records the phase instance it happened in, so a fresh robber phase - after a seven or after
    a knight - asks for the move again, and the phase in which it has already moved asks for the
    victim. The two steps are one phase, because the phase ends when the robber has moved and
    the steal is resolved or skipped (RULES.md 4.4).
    """
    if state.robber_moved_at != state.phase_index:
        return [_request(state, state.turn, MOVE_ROBBER, context={"from": state.robber})]
    # One candidate is not a question: the move already robbed them (RULES.md 4.9 item 5). The
    # request exists only where there is a choice, and the phase closes when there is neither.
    candidates = robber.robber_victims(state)
    if len(candidates) < 2:
        return []
    return [
        _request(
            state,
            state.turn,
            CHOOSE_ROBBER_VICTIM,
            context={"candidates": list(candidates)},
        )
    ]


def _after_robber(state: CatanState) -> Phase:
    """The turn goes on to its action phase once the seven is fully resolved (RULES.md 4.4)."""
    del state
    return Phase.ACTION


PHASE_RULES: Final[Mapping[Phase, PhaseRule]] = MappingProxyType(
    {
        Phase.SETUP_ROUND_1: PhaseRule(_setup_requests, _after_setup_round_one),
        Phase.SETUP_ROUND_2: PhaseRule(_setup_requests, _after_setup_round_two),
        Phase.TURN_PRODUCTION: PhaseRule(_turn_production_requests, _after_turn_production),
        Phase.ACTION: PhaseRule(_action_requests, None),
        Phase.DISCARD: PhaseRule(_discard_requests, _after_discard),
        Phase.ROBBER: PhaseRule(_robber_requests, _after_robber),
    }
)
"""What each implemented phase asks, and where it goes. The rest arrive with their cards."""


def _request(
    state: CatanState,
    player: int,
    kind: str,
    *,
    schema_ref: str | None = None,
    context: Mapping[str, JsonValue] | None = None,
) -> DecisionRequest:
    """A decision addressed to one player, identified from the state rather than from a clock."""
    return DecisionRequest(
        request_id=f"d{state.phase_index}.{player}",
        player=player,
        kind=kind,
        schema_ref=kind if schema_ref is None else schema_ref,
        context=dict(context or {}),
        phase=state.phase.value,
    )


def _placed(occupancy: tuple[int, ...]) -> int:
    return sum(1 for seat in occupancy if seat != NO_OWNER)
