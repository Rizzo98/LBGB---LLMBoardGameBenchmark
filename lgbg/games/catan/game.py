"""Catan: the plugin itself (ARCHITECTURE.md section 7.1).

This is the reference implementation of the game plugin interface, and it is deliberately the
awkward game: setup is a phase, discards are concurrent, trading addresses players who are out
of turn, and some information is asymmetric rather than merely private. An interface that only
works for a simple game is not an interface.

What this file does is *declaration and dispatch*, and nothing else. The board, the state, the
projection, the phases and each rule area live in their own modules; this one says what the
game is called, what versions it implements, and where each protocol member is answered.

The modules a card has not reached yet answer honestly for the slice that exists: the action
schema declares the two setup actions, the benchmark profile is the shape Catan has, the
invariants are the two conservation laws that hold from the first placement. Each is complete
for what the game can currently do, and each grows with the card that needs it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.errors import GAME_OVER, UNKNOWN_ACTION, Rejection, RejectionCode
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
    JsonSchema,
    JsonValue,
    Observation,
    Outcome,
    PlayerId,
)
from lgbg.games.catan import notation, phases
from lgbg.games.catan.board.generation import (
    NUMBER_PLACEMENTS,
    NUMBER_SPIRAL_NO_ADJACENT_RED,
    board_from_selector,
)
from lgbg.games.catan.notation import Detail
from lgbg.games.catan.projection import observe as project
from lgbg.games.catan.projection import observe_spectator as project_spectator
from lgbg.games.catan.rejections import DECLARED_CODES
from lgbg.games.catan.rules import setup
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    NO_OWNER,
    PIECES_PER_PLAYER,
    RESOURCE_ORDER,
    VICTORY_TARGET,
    CatanState,
    Phase,
    decode_state,
    encode_state,
    initial_state,
)

RULES_VERSION: Final[str] = "catan-rules-1"
"""Bumped whenever a pinned rule changes (RULES.md section 1.2), which invalidates the corpus."""

SCHEMA_VERSION: Final[str] = "catan-actions-1"
"""Bumped whenever the action or observation schema changes."""

BOARD_OPTION: Final[str] = "board"
NUMBER_PLACEMENT_OPTION: Final[str] = "number_placement"
DEFAULT_BOARD: Final[str] = "fixed:standard_a"

RuleFunction = Callable[[CatanState, Action, RandomSource], ApplyResult]

SETUP_ACTIONS: Final[dict[str, RuleFunction]] = {
    phases.PLACE_SETTLEMENT: setup.place_settlement,
    phases.PLACE_ROAD: setup.place_road,
}
"""The action types the game accepts, and the rule function each one runs."""


@register_game
class CatanGame:
    """Settlers of Catan, base game, four players (PRD-v1 deliverable D3)."""

    name = "catan"
    rules_version = RULES_VERSION
    schema_version = SCHEMA_VERSION

    # --- lifecycle ---
    def initial_state(self, cfg: GameConfig, rng: RandomSource) -> CatanState:
        """Build the opening position: board from the configuration, deck from draw D5."""
        board = board_from_selector(
            _option(cfg, BOARD_OPTION, DEFAULT_BOARD),
            rng=rng,
            number_placement=_number_placement(cfg),
        )
        return initial_state(board, players=_players(cfg), rng=rng)

    # --- decision surface ---
    def pending_decisions(self, state: CatanState) -> list[DecisionRequest]:
        return phases.pending_decisions(state)

    def legal_actions(self, state: CatanState, player: PlayerId) -> list[Action]:
        """Every action this player could take now.

        Slice 2 knows the two setup placements. The slice that adds building fills this in for
        the action phase (K-034).
        """
        return [
            Action(player=request.player, type=_action_for(request.kind, state), params=params)
            for request in phases.pending_decisions(state)
            if request.player == player
            for params in _setup_parameters(state, request)
        ]

    def action_domains(self, state: CatanState, player: PlayerId) -> list[ActionDomain]:
        """What the player may do, cross-product free (ARCHITECTURE.md section 7.2)."""
        return [
            ActionDomain(type=_action_for(request.kind, state), cost=None, params={})
            for request in phases.pending_decisions(state)
            if request.player == player
        ]

    # --- transitions ---
    def apply(self, state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
        """Validate, apply, then let the phase machine close the phase if it is closed."""
        if self.is_terminal(state):
            return Rejected(
                Rejection(
                    code=GAME_OVER,
                    message="the game has already terminated",
                    details={"phase": state.phase.value},
                )
            )
        rule = SETUP_ACTIONS.get(action.type)
        if rule is None:
            return Rejected(
                Rejection(
                    code=UNKNOWN_ACTION,
                    message=f"{action.type!r} is not an action this game declares",
                    details={"action_type": action.type, "known": sorted(SETUP_ACTIONS)},
                )
            )
        result = rule(state, action, rng)
        if not isinstance(result, Applied):
            return result
        advanced, announced = phases.advance(result.state)
        return Applied(state=advanced, events=[*result.events, *announced])

    # --- observation ---
    def observe(self, state: CatanState, player: PlayerId) -> Observation:
        return project(state, player)

    def observe_spectator(self, state: CatanState) -> Observation:
        return project_spectator(state)

    def render(self, observation: Observation, *, detail: str = "full") -> str:
        """The game's own notation, and the only renderer: the CLI and the prompt share it."""
        return notation.render(observation, detail=Detail(detail))

    # --- terminality ---
    def is_terminal(self, state: CatanState) -> bool:
        return state.phase is Phase.OVER

    def outcome(self, state: CatanState) -> Outcome:
        scores = {str(seat): self.victory_points(state, seat) for seat in range(state.players)}
        winner = next(
            (
                seat
                for seat in range(state.players)
                if self.victory_points(state, seat) >= VICTORY_TARGET
            ),
            None,
        )
        return Outcome(winner=winner, scores=scores, rounds=state.round)

    def victory_points(self, state: CatanState, player: PlayerId) -> int:
        """Settlements and cities, so far.

        Development cards (FR-13.8), Longest Road and Largest Army (FR-13.9) arrive with K-036;
        this is the part of the total that the board already knows.
        """
        settlements = sum(1 for seat in state.placed.settlements if seat == player)
        cities = sum(1 for seat in state.placed.cities if seat == player)
        return settlements + 2 * cities

    # --- serialisation and declared schemas ---
    def encode_state(self, state: CatanState) -> JsonValue:
        return encode_state(state)

    def decode_state(self, blob: Any) -> CatanState:
        return decode_state(blob)

    def action_schema(self) -> JsonSchema:
        """The declared action surface, as data, so tools and prompts can be generated."""
        return {
            phases.PLACE_SETTLEMENT: {
                "type": "object",
                "properties": {"vertex": {"type": "integer", "minimum": 0, "maximum": 53}},
                "required": ["vertex"],
                "additionalProperties": False,
            },
            phases.PLACE_ROAD: {
                "type": "object",
                "properties": {"edge": {"type": "integer", "minimum": 0, "maximum": 71}},
                "required": ["edge"],
                "additionalProperties": False,
            },
        }

    def observation_schema(self) -> JsonSchema:
        return {
            "type": "object",
            "required": ["awards", "bank", "board", "pieces", "robber", "supply", "turn", "phase"],
            "additionalProperties": True,
        }

    def rejection_codes(self) -> list[RejectionCode]:
        return list(DECLARED_CODES)

    # --- declarations the platform needs and must not guess ---
    def benchmark_profile(self) -> BenchmarkProfile:
        """The facts the runner needs to design a valid experiment (FR-6.7, ARCHITECTURE 7.10).

        The decision counts are provisional estimates; the fuzz campaign of K-067 is what
        measures the real distribution, and K-062 audits this declaration.
        """
        return BenchmarkProfile(
            positional_asymmetry=True,
            outcome_shape=OutcomeShape.SINGLE_WINNER,
            variance_class=VarianceClass.HIGH,
            interaction_character=InteractionCharacter.MIXED,
            typical_decisions=250,
            worst_case_decisions=1500,
        )

    def check_invariants(self, state: CatanState) -> list[InvariantViolation]:
        """The conservation laws a generic harness can check without knowing the game (7.11)."""
        violations: list[InvariantViolation] = []
        for index, resource in enumerate(RESOURCE_ORDER):
            held = sum(hand[index] for hand in state.hands)
            total = state.bank[index] + held
            if total != BANK_PER_RESOURCE:
                violations.append(
                    InvariantViolation(
                        invariant="resource_conservation",
                        detail=(
                            f"{resource.value}: bank {state.bank[index]} plus hands {held} is "
                            f"{total}, expected {BANK_PER_RESOURCE}"
                        ),
                    )
                )
        for seat in range(state.players):
            supply = state.supply[seat]
            for name, remaining, on_board in (
                ("roads", supply.roads, sum(1 for owner in state.placed.roads if owner == seat)),
                (
                    "settlements",
                    supply.settlements,
                    sum(1 for owner in state.placed.settlements if owner == seat),
                ),
                ("cities", supply.cities, sum(1 for owner in state.placed.cities if owner == seat)),
            ):
                expected = PIECES_PER_PLAYER[("roads", "settlements", "cities").index(name)]
                if remaining + on_board != expected:
                    violations.append(
                        InvariantViolation(
                            invariant="piece_conservation",
                            detail=(
                                f"seat {seat} {name}: {remaining} in supply plus {on_board} on "
                                f"the board is not {expected}"
                            ),
                        )
                    )
        return violations


def _option(cfg: GameConfig, key: str, default: str) -> str:
    value = cfg.options.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"the {key!r} option must be a string, got {value!r}")
    return value


def _players(cfg: GameConfig) -> int:
    value = cfg.options.get("players", 4)
    if not isinstance(value, int) or isinstance(value, bool) or value < 2:
        raise ValueError(f"the 'players' option must be an integer of at least 2, got {value!r}")
    return value


def _number_placement(cfg: GameConfig) -> str:
    placement = _option(cfg, NUMBER_PLACEMENT_OPTION, NUMBER_SPIRAL_NO_ADJACENT_RED)
    if placement not in NUMBER_PLACEMENTS:
        raise ValueError(
            f"unknown number placement {placement!r}; expected one of {list(NUMBER_PLACEMENTS)}"
        )
    return placement


def _action_for(kind: str, state: CatanState) -> str:
    """Which action type answers a decision kind: the same name, for the actions that exist."""
    del state
    return kind


def _setup_parameters(state: CatanState, request: DecisionRequest) -> list[dict[str, JsonValue]]:
    """The parameters a request admits, filtered by the rules that will judge them.

    An enumeration that offers an action the rules then refuse is worse than none: a driver
    that trusts it records a rejection it did not choose. So the filter here is the rule, and
    a test asserts every enumerated action is accepted.
    """
    if request.kind == phases.PLACE_SETTLEMENT:
        return [{"vertex": vertex} for vertex in _legal_settlement_vertices(state)]
    if request.kind == phases.PLACE_ROAD:
        return [{"edge": edge} for edge in _legal_setup_road_edges(state)]
    return []


def _legal_settlement_vertices(state: CatanState) -> list[int]:
    """Empty vertices clear of every building: the distance rule, during setup."""
    if state.supply[state.turn].settlements < 1:
        return []
    return [
        vertex
        for vertex in range(len(state.placed.settlements))
        if state.placed.settlements[vertex] == NO_OWNER
        and state.placed.cities[vertex] == NO_OWNER
        and all(
            state.placed.settlements[site] == NO_OWNER and state.placed.cities[site] == NO_OWNER
            for site in setup.neighbouring_vertices(state, vertex)
        )
    ]


def _legal_setup_road_edges(state: CatanState) -> list[int]:
    """Empty edges incident to the settlement this step placed, which is where a road goes."""
    if state.setup_vertex == NO_OWNER or state.supply[state.turn].roads < 1:
        return []
    return [
        edge
        for edge in state.board.topology.edges_at(state.setup_vertex)
        if state.placed.roads[edge] == NO_OWNER
    ]
