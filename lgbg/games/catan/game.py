"""Catan: the plugin itself (ARCHITECTURE.md section 7.1).

This is the reference implementation of the game plugin interface, and it is deliberately the
awkward game: setup is a phase, discards are concurrent, trading addresses players who are out
of turn, and some information is asymmetric rather than merely private. An interface that only
works for a simple game is not an interface.

What this file does is *declaration and dispatch*, and nothing else. The board, the state, the
projection, the phases and each rule area live in their own modules; this one says what the
game is called, what versions it implements, and where each protocol member is answered.

The modules a card has not reached yet answer honestly for the slice that exists: the action
schema declares the actions that exist, the benchmark profile is the shape Catan has, the
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
from lgbg.games.catan.rules import production, robber, setup
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

RULES_VERSION: Final[str] = "catan-rules-4"
"""Bumped whenever a pinned rule changes (RULES.md section 1.2), which invalidates the corpus.

Also bumped when the engine is corrected to a rule the document already pinned and the encoded
state changes with it: a record made by a corrected engine is not comparable with one made by the
engine it corrects, even though the rule was never in doubt.
"""

SCHEMA_VERSION: Final[str] = "catan-actions-1"
"""Bumped whenever the action or observation schema changes."""

BOARD_OPTION: Final[str] = "board"
NUMBER_PLACEMENT_OPTION: Final[str] = "number_placement"
DEFAULT_BOARD: Final[str] = "fixed:standard_a"

RuleFunction = Callable[[CatanState, Action, RandomSource], ApplyResult]

ACTIONS: Final[dict[str, RuleFunction]] = {
    phases.PLACE_SETTLEMENT: setup.place_settlement,
    phases.PLACE_ROAD: setup.place_road,
    phases.ROLL_DICE: production.roll_dice,
    phases.END_TURN: phases.end_turn,
    phases.DISCARD_RESOURCES: robber.discard_resources,
    phases.MOVE_ROBBER: robber.move_robber,
    phases.CHOOSE_ROBBER_VICTIM: robber.choose_robber_victim,
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

        Filtered by the rules that will judge it: an enumeration that offers an action the
        engine then refuses is worse than none, because a driver that trusts it records a
        rejection it did not choose. The action phase is filled in by K-030 onwards.
        """
        return [
            action
            for request in phases.pending_decisions(state)
            if request.player == player
            for action in _legal_actions_for(state, request)
        ]

    def action_domains(self, state: CatanState, player: PlayerId) -> list[ActionDomain]:
        """What the player may do, cross-product free (ARCHITECTURE.md section 7.2)."""
        return [
            ActionDomain(type=request.schema_ref, cost=None, params={})
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
        rule = ACTIONS.get(action.type)
        if rule is None:
            return Rejected(
                Rejection(
                    code=UNKNOWN_ACTION,
                    message=f"{action.type!r} is not an action this game declares",
                    details={"action_type": action.type, "known": sorted(ACTIONS)},
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
        return state.phase is Phase.TERMINAL

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
            phases.ROLL_DICE: _no_parameters(),
            phases.END_TURN: _no_parameters(),
            phases.DISCARD_RESOURCES: _resource_counts(),
            phases.MOVE_ROBBER: {
                "type": "object",
                "properties": {"hex": {"type": "integer", "minimum": 0, "maximum": 18}},
                "required": ["hex"],
                "additionalProperties": False,
            },
            phases.CHOOSE_ROBBER_VICTIM: {
                "type": "object",
                "properties": {"victim": {"type": "integer", "minimum": 0, "maximum": 3}},
                "required": ["victim"],
                "additionalProperties": False,
            },
        }

    def observation_schema(self) -> JsonSchema:
        return {
            "type": "object",
            "required": [
                "awards",
                "bank",
                "board",
                "hand_counts",
                "phase",
                "pieces",
                "robber",
                "supply",
                "turn",
            ],
            "additionalProperties": True,
            "properties": {
                "hand": {
                    "type": ["object", "null"],
                    "description": "the observer's own hand, exact; absent for the spectator, "
                    "which sees every hand as 'hands'",
                },
                "hand_counts": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "description": "how many resource cards each seat holds, in seat order",
                },
            },
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


def _no_parameters() -> JsonSchema:
    """An action that takes no parameters, declared rather than left to inference."""
    return {"type": "object", "properties": {}, "additionalProperties": False}


def _resource_counts() -> JsonSchema:
    """A composition of resource cards: each resource, optionally, as a whole number."""
    return {
        "type": "object",
        "properties": {
            resource.value: {"type": "integer", "minimum": 0} for resource in RESOURCE_ORDER
        },
        "additionalProperties": False,
    }


def _legal_actions_for(state: CatanState, request: DecisionRequest) -> list[Action]:
    """The actions one request admits, filtered by the rules that will judge them."""
    player = request.player
    if request.kind == phases.PLACE_SETTLEMENT:
        return [
            Action(player=player, type=phases.PLACE_SETTLEMENT, params={"vertex": vertex})
            for vertex in _legal_settlement_vertices(state)
        ]
    if request.kind == phases.PLACE_ROAD:
        return [
            Action(player=player, type=phases.PLACE_ROAD, params={"edge": edge})
            for edge in _legal_setup_road_edges(state)
        ]
    if request.kind == phases.TAKE_TURN:
        # The request names the action that answers it; the rest of the action phase arrives
        # with K-030 onwards.
        return [Action(player=player, type=request.schema_ref, params={})]
    if request.kind == phases.DISCARD_RESOURCES:
        return [
            Action(player=player, type=phases.DISCARD_RESOURCES, params=composition)
            for composition in _legal_discards(state, player)
        ]
    if request.kind == phases.MOVE_ROBBER:
        return [
            Action(player=player, type=phases.MOVE_ROBBER, params={"hex": hex_id})
            for hex_id in robber.destinations(state)
        ]
    if request.kind == phases.CHOOSE_ROBBER_VICTIM:
        return [
            Action(player=player, type=phases.CHOOSE_ROBBER_VICTIM, params={"victim": victim})
            for victim in robber.robber_victims(state)
        ]
    return []


def _legal_discards(state: CatanState, player: int) -> list[dict[str, JsonValue]]:
    """Every composition of exactly the forced amount, out of the cards the player holds.

    FR-12.2 allows any composition, so the enumeration is the whole cross product *at the
    forced total*: the free cross product would advertise discards the rule then refuses, and a
    driver that trusts an enumeration must be able to trust it (FR-17.5).
    """
    if not 0 <= player < state.players:
        return []
    owed = state.discards_pending[player]
    hand = state.hands[player]
    found: list[dict[str, JsonValue]] = []
    taken: dict[str, JsonValue] = {}

    def walk(index: int, left: int) -> None:
        if index == len(RESOURCE_ORDER):
            if left == 0:
                found.append(dict(taken))
            return
        resource = RESOURCE_ORDER[index]
        for count in range(min(hand[index], left) + 1):
            if count:
                taken[resource.value] = count
            walk(index + 1, left - count)
            taken.pop(resource.value, None)

    walk(0, owed)
    return found


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
