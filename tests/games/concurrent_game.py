"""A game whose players decide at the same time, as a test asset for concurrent dispatch.

The fixture game is deliberately sequential: one decision at a time is enough to exercise the
machinery, and it keeps the canary small. The runner's concurrency path needs a different shape - a
phase in which several seats are open at once and every answer is legal without seeing the others -
so this asset provides it. It is not a game and is never shipped: four players each mark their seat
once, in whatever order the runner resolves them, and the game ends when all four have marked. The
observation is intentionally constant, so a serial and a parallel run see exactly the same prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import GameConfig
from lgbg.core.errors import GAME_OVER, NOT_YOUR_DECISION, UNKNOWN_ACTION, Rejection, RejectionCode
from lgbg.core.game import (
    Applied,
    ApplyResult,
    BenchmarkProfile,
    InteractionCharacter,
    InvariantViolation,
    OutcomeShape,
    Rejected,
    VarianceClass,
    register_game,
)
from lgbg.core.rng import RandomSource
from lgbg.core.types import (
    Action,
    ActionDomain,
    DecisionRequest,
    Event,
    JsonSchema,
    JsonValue,
    Observation,
    Outcome,
    PlayerId,
)

PLAYERS: Final[int] = 4
PHASE: Final[str] = "marking"
MARK: Final[str] = "mark"
CLOSE: Final[str] = "close"

ALREADY_MARKED: Final[RejectionCode] = RejectionCode(
    code="ALREADY_MARKED", description="this seat has already marked itself"
)


@dataclass(frozen=True, slots=True)
class ConcurrentState:
    """Who has marked, and nothing else: the order the marks arrived in is the log's business."""

    marked: tuple[bool, ...]


def _no_params() -> JsonSchema:
    return {"type": "object", "properties": {}, "additionalProperties": False}


@register_game
class ConcurrentGame:
    """Four seats decide at once; each mark is independent and the last one ends the game."""

    name = "concurrent"
    rules_version = "concurrent-rules-1"
    schema_version = "concurrent-actions-1"

    def initial_state(self, cfg: GameConfig, rng: RandomSource) -> ConcurrentState:
        del cfg, rng
        return ConcurrentState(marked=(False,) * PLAYERS)

    def pending_decisions(self, state: ConcurrentState) -> list[DecisionRequest]:
        if self.is_terminal(state):
            return []
        return [
            DecisionRequest(
                request_id=f"d.{seat}",
                player=seat,
                kind=MARK,
                schema_ref=MARK,
                context={},
                phase=PHASE,
            )
            for seat in range(PLAYERS)
            if not state.marked[seat]
        ]

    def legal_actions(self, state: ConcurrentState, player: PlayerId) -> list[Action]:
        if self.is_terminal(state) or state.marked[player]:
            return []
        offered = [Action(player=player, type=MARK, params={})]
        if player == 0:
            # Seat 0 may close the round instead of marking, which closes every other
            # decision in the batch. It exists so the runner's closed-request path can be
            # tested without a full trade offer.
            offered.append(Action(player=player, type=CLOSE, params={}))
        return offered

    def action_domains(self, state: ConcurrentState, player: PlayerId) -> list[ActionDomain]:
        return [
            ActionDomain(type=action.type, cost=None, params={})
            for action in self.legal_actions(state, player)
        ]

    def apply(self, state: ConcurrentState, action: Action, rng: RandomSource) -> ApplyResult:
        del rng
        if self.is_terminal(state):
            return Rejected(Rejection(code=GAME_OVER, message="every seat has marked", details={}))
        if action.type == CLOSE:
            if action.player != 0:
                return Rejected(
                    Rejection(
                        code=NOT_YOUR_DECISION,
                        message="only seat 0 may close the round",
                        details={"player": action.player},
                    )
                )
            return Applied(
                state=ConcurrentState(marked=(True,) * PLAYERS),
                events=[Event(type=CLOSE, payload={"player": action.player})],
            )
        if action.type != MARK:
            return Rejected(
                Rejection(
                    code=UNKNOWN_ACTION,
                    message=f"{action.type!r} is not an action this game declares",
                    details={"action_type": action.type},
                )
            )
        if action.player < 0 or action.player >= PLAYERS or state.marked[action.player]:
            return Rejected(
                Rejection(
                    code=NOT_YOUR_DECISION,
                    message=f"seat {action.player} has no open mark",
                    details={"marked": list(state.marked)},
                )
            )
        marked = list(state.marked)
        marked[action.player] = True
        return Applied(
            state=ConcurrentState(marked=tuple(marked)),
            events=[Event(type=MARK, payload={"player": action.player})],
        )

    def observe(self, state: ConcurrentState, player: PlayerId) -> Observation:
        del state, player
        return {"players": PLAYERS}

    def observe_spectator(self, state: ConcurrentState) -> Observation:
        del state
        return {"players": PLAYERS}

    def render(self, observation: Observation, *, detail: str = "full") -> str:
        del detail
        return to_canonical_json(observation)

    def is_terminal(self, state: ConcurrentState) -> bool:
        return all(state.marked)

    def outcome(self, state: ConcurrentState) -> Outcome:
        return Outcome(
            winner=None if not self.is_terminal(state) else 0,
            scores={str(seat): PLAYERS - seat for seat in range(PLAYERS)},
            rounds=1 if self.is_terminal(state) else 0,
        )

    def encode_state(self, state: ConcurrentState) -> JsonValue:
        return {"marked": list(state.marked)}

    def decode_state(self, blob: Any) -> ConcurrentState:
        fields: dict[str, Any] = dict(blob)
        return ConcurrentState(marked=tuple(fields["marked"]))

    def action_schema(self) -> JsonSchema:
        return {MARK: _no_params(), CLOSE: _no_params()}

    def observation_schema(self) -> JsonSchema:
        return {
            "type": "object",
            "required": ["players"],
            "additionalProperties": False,
            "properties": {"players": {"type": "integer"}},
        }

    def rejection_codes(self) -> list[RejectionCode]:
        return [ALREADY_MARKED]

    def benchmark_profile(self) -> BenchmarkProfile:
        return BenchmarkProfile(
            positional_asymmetry=False,
            configuration_is_variable=False,
            outcome_shape=OutcomeShape.SINGLE_WINNER,
            variance_class=VarianceClass.LOW,
            interaction_character=InteractionCharacter.ADVERSARIAL,
            typical_decisions=PLAYERS,
            worst_case_decisions=PLAYERS,
        )

    def check_invariants(self, state: ConcurrentState) -> list[InvariantViolation]:
        del state
        return []
