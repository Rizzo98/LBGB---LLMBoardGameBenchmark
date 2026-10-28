"""A six-seat simultaneous game, as the test asset for the unattended campaign (K-034).

The campaign must include every way the mock can behave - correct play, an illegal action, a
timeout, malformed arguments, prose and a runaway - in one table. That needs one seat per
behaviour, and the suite's concurrent asset has four. This one has six and is otherwise the same
shape: every seat marks once, no answer depends on another, and seat 0 may close the round so a
game can also complete before the failing seats are recorded.

It is test infrastructure and never shipped. It is not a game anyone would play; it is a table
big enough to hold every declared behaviour at once.
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

PLAYERS: Final[int] = 6
PHASE: Final[str] = "marking"
MARK: Final[str] = "mark"
CLOSE: Final[str] = "close"
REFUSE: Final[str] = "refuse"
"""A declared action the game never offers and always refuses.

It exists so a deliberately illegal agent can send an action the game *knows* and refuses, rather
than one the record cannot replay: a refused declared action replays as a refusal, an undeclared
one is a record the engine cannot read. That is the difference the campaign's failing seats need.
"""

ALREADY_MARKED: Final[RejectionCode] = RejectionCode(
    code="ALREADY_MARKED", description="this seat has already marked itself"
)
REFUSED: Final[RejectionCode] = RejectionCode(
    code="REFUSED", description="this action is declared but never offered"
)


@dataclass(frozen=True, slots=True)
class CampaignState:
    """Who has marked, and nothing else: arrival order is the log's business, not the state's."""

    marked: tuple[bool, ...]


def _no_params() -> JsonSchema:
    return {"type": "object", "properties": {}, "additionalProperties": False}


@register_game
class CampaignGame:
    """Six seats decide at once; each mark is independent and the last one ends the game."""

    name = "campaign"
    rules_version = "campaign-rules-1"
    schema_version = "campaign-actions-1"

    def initial_state(self, cfg: GameConfig, rng: RandomSource) -> CampaignState:
        del cfg, rng
        return CampaignState(marked=(False,) * PLAYERS)

    def pending_decisions(self, state: CampaignState) -> list[DecisionRequest]:
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

    def legal_actions(self, state: CampaignState, player: PlayerId) -> list[Action]:
        if self.is_terminal(state) or state.marked[player]:
            return []
        offered = [Action(player=player, type=MARK, params={})]
        if player == 0:
            offered.append(Action(player=player, type=CLOSE, params={}))
        return offered

    def action_domains(self, state: CampaignState, player: PlayerId) -> list[ActionDomain]:
        return [
            ActionDomain(type=action.type, cost=None, params={})
            for action in self.legal_actions(state, player)
        ]

    def apply(self, state: CampaignState, action: Action, rng: RandomSource) -> ApplyResult:
        del rng
        if self.is_terminal(state):
            return Rejected(Rejection(code=GAME_OVER, message="every seat has marked", details={}))
        if action.type == REFUSE:
            return Rejected(
                Rejection(
                    code=REFUSED,
                    message="this action is declared but never offered",
                    details={"player": action.player},
                )
            )
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
                state=CampaignState(marked=(True,) * PLAYERS),
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
            state=CampaignState(marked=tuple(marked)),
            events=[Event(type=MARK, payload={"player": action.player})],
        )

    def observe(self, state: CampaignState, player: PlayerId) -> Observation:
        del state, player
        return {"players": PLAYERS}

    def observe_spectator(self, state: CampaignState) -> Observation:
        del state
        return {"players": PLAYERS}

    def render(self, observation: Observation, *, detail: str = "full") -> str:
        del detail
        return to_canonical_json(observation)

    def is_terminal(self, state: CampaignState) -> bool:
        return all(state.marked)

    def outcome(self, state: CampaignState) -> Outcome:
        return Outcome(
            winner=None if not self.is_terminal(state) else 0,
            scores={str(seat): PLAYERS - seat for seat in range(PLAYERS)},
            rounds=1 if self.is_terminal(state) else 0,
        )

    def encode_state(self, state: CampaignState) -> JsonValue:
        return {"marked": list(state.marked)}

    def decode_state(self, blob: Any) -> CampaignState:
        fields: dict[str, Any] = dict(blob)
        return CampaignState(marked=tuple(fields["marked"]))

    def action_schema(self) -> JsonSchema:
        return {MARK: _no_params(), CLOSE: _no_params(), REFUSE: _no_params()}

    def observation_schema(self) -> JsonSchema:
        return {
            "type": "object",
            "required": ["players"],
            "additionalProperties": False,
            "properties": {"players": {"type": "integer"}},
        }

    def rejection_codes(self) -> list[RejectionCode]:
        return [ALREADY_MARKED, REFUSED]

    def benchmark_profile(self) -> BenchmarkProfile:
        return BenchmarkProfile(
            positional_asymmetry=True,
            configuration_is_variable=False,
            outcome_shape=OutcomeShape.SINGLE_WINNER,
            variance_class=VarianceClass.LOW,
            interaction_character=InteractionCharacter.ADVERSARIAL,
            typical_decisions=PLAYERS,
            worst_case_decisions=PLAYERS,
        )

    def check_invariants(self, state: CampaignState) -> list[InvariantViolation]:
        del state
        return []
