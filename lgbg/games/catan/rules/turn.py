"""The turn: rolling, and ending it (RULES.md 4.4; PRD-v1 FR-10.1, FR-10.2).

A turn is two phases, not one: production, in which the player rolls (or plays a development
card first, from K-042), and the action phase, in which they build and trade and then end the
turn. The dice are two independent draws, never one draw of a total, because the distributions
differ and because a recorded draw has to be replayable semantically (ARCHITECTURE.md 5.4).

Production itself - which hexes pay, and what the bank can cover - arrives with K-023. What is
here is the shape of the turn: the roll is asked for, it consumes the two draws RULES.md 3.1
pins, the dice become visible, the phase closes, and a seven opens the discard phase instead.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from lgbg.core.errors import NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import Purpose, RandomSource
from lgbg.core.types import Action, Event
from lgbg.games.catan import phases
from lgbg.games.catan.state import CatanState, Phase

DICE_DIE_1: Final[Purpose] = "dice_die_1"
DICE_DIE_2: Final[Purpose] = "dice_die_2"
"""Draws D6 and D7 of RULES.md section 3.1: two independent dice, in that order."""

DIE_FACES: Final[int] = 6
SEVEN: Final[int] = 7


def roll_dice(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Roll the two dice, which closes the production phase (FR-10.1, FR-10.2)."""
    refusal = _refuse_unless_acting(state, action, Phase.TURN_PRODUCTION)
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
    rolled = replace(state, dice=(first, second))
    return Applied(
        state=rolled,
        events=[
            Event(
                type="dice_rolled",
                payload={
                    "player": action.player,
                    "dice": [first, second],
                    "total": first + second,
                },
            )
        ],
    )


def end_turn(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Close the turn and open the next seat's production phase (RULES.md 4.4 rule 1)."""
    del rng
    refusal = _refuse_unless_acting(state, action, Phase.ACTION)
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
    entered, announced = phases.begin(closed, Phase.TURN_PRODUCTION)
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


def _refuse_unless_acting(state: CatanState, action: Action, phase: Phase) -> Rejected | None:
    """The two refusals every turn action shares: right seat, right phase."""
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
