"""A trivial game used as the permanent test canary (kanban card K-007).

This is a test asset, not a game. It is never shipped, never scored, and never appears in a
result. Its whole purpose is to isolate machinery defects from rules defects: when a hash
mismatch or a replay divergence shows up here, the fault is in the machinery, because there
are no rules to be wrong. PRD-v1 M2 is sequenced before any Catan work for exactly this
reason.

It exercises the full plugin protocol with the smallest surface that still has teeth: three
action types, one random draw, a limited supply shared between players, hidden per-player
holdings, a conservation law, and a terminal condition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.errors import (
    GAME_OVER,
    NOT_YOUR_DECISION,
    UNKNOWN_ACTION,
    Rejection,
    RejectionCode,
)
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
from lgbg.core.rng import Purpose, RandomSource
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

PLAYERS: Final[int] = 2
INITIAL_BANK: Final[int] = 12
COST_TOKENS: Final[int] = 4
TARGET_SCORE: Final[int] = 2
GAMBLE_MAX: Final[int] = 3

GAMBLE_PURPOSE: Final[Purpose] = "gamble_bonus"
"""The one random draw this game performs. A named constant, per FR-2.3."""

TOKENS_UNAVAILABLE: Final[RejectionCode] = RejectionCode(
    code="TOKENS_UNAVAILABLE", description="the bank or the player cannot cover the tokens"
)

ACTION_TYPES: Final[tuple[str, ...]] = ("take", "gamble", "spend")
PHASE_PLAY: Final[str] = "play"


@dataclass(frozen=True, slots=True)
class FixtureState:
    """The god view: every player's holding is here, and the projection is what hides it."""

    tokens: tuple[int, ...]
    scores: tuple[int, ...]
    bank: int
    turn: int
    rounds: int
    decisions: int


@register_game
class FixtureGame:
    """Three actions, one draw, one supply limit, one way to win."""

    name = "fixture"
    rules_version = "fixture-rules-1"
    schema_version = "fixture-actions-1"

    # --- lifecycle ---
    def initial_state(self, cfg: GameConfig, rng: RandomSource) -> FixtureState:
        del cfg, rng  # the fixture has no configuration and no opening randomness
        return FixtureState(
            tokens=(0,) * PLAYERS,
            scores=(0,) * PLAYERS,
            bank=INITIAL_BANK,
            turn=0,
            rounds=0,
            decisions=0,
        )

    # --- decision surface ---
    def pending_decisions(self, state: FixtureState) -> list[DecisionRequest]:
        if self.is_terminal(state):
            return []
        return [
            DecisionRequest(
                request_id=f"d{state.decisions}",
                player=state.turn,
                kind="turn",
                schema_ref="turn",
                context={"turn": state.turn},
                phase=PHASE_PLAY,
            )
        ]

    def legal_actions(self, state: FixtureState, player: PlayerId) -> list[Action]:
        return [
            Action(player=player, type=type_, params={})
            for type_ in self._available_types(state, player)
        ]

    def action_domains(self, state: FixtureState, player: PlayerId) -> list[ActionDomain]:
        return [
            ActionDomain(
                type=type_,
                cost={"tokens": COST_TOKENS} if type_ == "spend" else None,
                params={},
            )
            for type_ in self._available_types(state, player)
        ]

    # --- transitions ---
    def apply(self, state: FixtureState, action: Action, rng: RandomSource) -> ApplyResult:
        if self.is_terminal(state):
            return Rejected(
                Rejection(code=GAME_OVER, message="the game is over", details={"turn": state.turn})
            )
        if action.type not in ACTION_TYPES:
            return Rejected(
                Rejection(
                    code=UNKNOWN_ACTION,
                    message=f"{action.type!r} is not an action this game declares",
                    details={"action_type": action.type},
                )
            )
        if action.player != state.turn:
            return Rejected(
                Rejection(
                    code=NOT_YOUR_DECISION,
                    message=f"player {action.player} has no open decision",
                    details={"turn": state.turn},
                )
            )
        if action.type == "spend":
            if state.tokens[state.turn] < COST_TOKENS:
                return Rejected(
                    Rejection(
                        code=TOKENS_UNAVAILABLE,
                        message="not enough tokens to score",
                        details={"requires": COST_TOKENS, "you_have": state.tokens[state.turn]},
                    )
                )
            return Applied(
                state=self._succeed(
                    state, token_delta=-COST_TOKENS, bank_delta=COST_TOKENS, score_delta=1
                ),
                events=[
                    Event(
                        type="tokens_spent", payload={"player": state.turn, "amount": COST_TOKENS}
                    ),
                    Event(type="score_gained", payload={"player": state.turn, "amount": 1}),
                ],
            )
        if state.bank < 1:
            return Rejected(
                Rejection(
                    code=TOKENS_UNAVAILABLE,
                    message="the bank is empty",
                    details={"requires": 1, "available": state.bank},
                )
            )
        gained = 1
        if action.type == "gamble":
            gained = min(rng.randint(1, GAMBLE_MAX, purpose=GAMBLE_PURPOSE), state.bank)
        return Applied(
            state=self._succeed(state, token_delta=gained, bank_delta=-gained, score_delta=0),
            events=[Event(type="tokens_gained", payload={"player": state.turn, "amount": gained})],
        )

    # --- observation ---
    def observe(self, state: FixtureState, player: PlayerId) -> Observation:
        return {
            "bank": state.bank,
            "opponents": {
                str(index): state.tokens[index] for index in range(PLAYERS) if index != player
            },
            "rounds": state.rounds,
            "scores": {str(index): score for index, score in enumerate(state.scores)},
            "tokens": state.tokens[player],
            "turn": state.turn,
        }

    def observe_spectator(self, state: FixtureState) -> Observation:
        return {
            "bank": state.bank,
            "rounds": state.rounds,
            "scores": {str(index): score for index, score in enumerate(state.scores)},
            "tokens": {str(index): tokens for index, tokens in enumerate(state.tokens)},
            "turn": state.turn,
        }

    # --- terminality ---
    def is_terminal(self, state: FixtureState) -> bool:
        return max(state.scores) >= TARGET_SCORE

    def outcome(self, state: FixtureState) -> Outcome:
        winner = next(
            (index for index, score in enumerate(state.scores) if score >= TARGET_SCORE), None
        )
        return Outcome(
            winner=winner,
            scores={str(index): score for index, score in enumerate(state.scores)},
            rounds=state.rounds,
        )

    # --- serialisation and declared schemas ---
    def encode_state(self, state: FixtureState) -> JsonValue:
        return {
            "bank": state.bank,
            "decisions": state.decisions,
            "rounds": state.rounds,
            "scores": list(state.scores),
            "tokens": list(state.tokens),
            "turn": state.turn,
        }

    def decode_state(self, blob: Any) -> FixtureState:
        # A test asset: the log reader owns record validation, so this trusts its input.
        fields: dict[str, Any] = dict(blob)
        return FixtureState(
            tokens=tuple(fields["tokens"]),
            scores=tuple(fields["scores"]),
            bank=fields["bank"],
            turn=fields["turn"],
            rounds=fields["rounds"],
            decisions=fields["decisions"],
        )

    def action_schema(self) -> JsonSchema:
        empty_params: JsonSchema = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        return {
            "take": dict(empty_params),
            "gamble": dict(empty_params),
            "spend": dict(empty_params),
            "turn": {"oneOf": [{"$ref": "#/take"}, {"$ref": "#/gamble"}, {"$ref": "#/spend"}]},
        }

    def observation_schema(self) -> JsonSchema:
        return {
            "type": "object",
            "required": ["bank", "rounds", "scores", "turn"],
            "additionalProperties": True,
        }

    def rejection_codes(self) -> list[RejectionCode]:
        return [TOKENS_UNAVAILABLE]

    # --- declarations the platform needs and must not guess ---
    def benchmark_profile(self) -> BenchmarkProfile:
        return BenchmarkProfile(
            positional_asymmetry=True,
            outcome_shape=OutcomeShape.SINGLE_WINNER,
            variance_class=VarianceClass.LOW,
            interaction_character=InteractionCharacter.ADVERSARIAL,
            typical_decisions=12,
            worst_case_decisions=60,
        )

    def check_invariants(self, state: FixtureState) -> list[InvariantViolation]:
        total = state.bank + sum(state.tokens)
        if total != INITIAL_BANK:
            return [
                InvariantViolation(
                    invariant="token_conservation",
                    detail=f"bank plus hands is {total}, expected {INITIAL_BANK}",
                )
            ]
        return []

    # --- internals ---
    def _available_types(self, state: FixtureState, player: PlayerId) -> list[str]:
        if self.is_terminal(state) or player != state.turn:
            return []
        available: list[str] = []
        if state.bank >= 1:
            available.extend(["take", "gamble"])
        if state.tokens[player] >= COST_TOKENS:
            available.append("spend")
        return available

    def _succeed(
        self, state: FixtureState, *, token_delta: int, bank_delta: int, score_delta: int
    ) -> FixtureState:
        tokens = list(state.tokens)
        tokens[state.turn] += token_delta
        scores = list(state.scores)
        scores[state.turn] += score_delta
        turn = (state.turn + 1) % PLAYERS
        return FixtureState(
            tokens=tuple(tokens),
            scores=tuple(scores),
            bank=state.bank + bank_delta,
            turn=turn,
            rounds=state.rounds + (1 if turn == 0 else 0),
            decisions=state.decisions + 1,
        )
