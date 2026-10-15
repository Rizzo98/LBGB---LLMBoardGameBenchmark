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

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
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
    ParamDomain,
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
from lgbg.games.catan.rules import (
    building,
    devcards,
    production,
    robber,
    setup,
    trading,
    victory,
)
from lgbg.games.catan.rules.trading import GENERAL, SPECIFIC
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    NO_OWNER,
    PIECES_PER_PLAYER,
    RESOURCE_ORDER,
    CatanState,
    Phase,
    decode_state,
    encode_state,
    initial_state,
)

RULES_VERSION: Final[str] = "catan-rules-6"
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
    phases.BUILD_ROAD: building.build_road,
    phases.BUILD_SETTLEMENT: building.build_settlement,
    phases.BUILD_CITY: building.build_city,
    phases.BUY_DEV_CARD: devcards.buy_dev_card,
    phases.PLAY_DEV_CARD: devcards.play_dev_card,
    phases.PLACE_FREE_ROAD: building.place_free_road,
    phases.MARITIME_TRADE: trading.maritime_trade,
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
        """What the player may do, cross-product free (ARCHITECTURE.md section 7.2).

        One entry per action type the open requests offer, carrying the price the rule table
        declares and the permitted values of each parameter - read from the same table the
        enumeration reads, so the description and the enumeration are one fact stated twice.
        """
        return [
            _domain_of(state, player, name)
            for request in phases.pending_decisions(state)
            if request.player == player
            for name in _offered(request)
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
        # The win is tested after every transition, and it is tested on the player *whose turn
        # it is*: reaching ten during somebody else's turn wins at the start of your own, which
        # is the state the next turn produces (RULES.md 4.13 items 5 and 6).
        won, ended = victory.check(advanced)
        return Applied(state=won, events=[*result.events, *announced, *ended])

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
        """The game's own verdict: true totals, the winner, the round (RULES.md 4.13 item 10)."""
        scores = {str(seat): self.victory_points(state, seat) for seat in range(state.players)}
        winner = state.turn if self.is_terminal(state) else None
        return Outcome(winner=winner, scores=scores, rounds=state.round)

    def victory_points(self, state: CatanState, player: PlayerId) -> int:
        """Every point this player has: pieces, cards and both special cards (RULES.md 4.13)."""
        return victory.victory_points(state, player)

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
            phases.MARITIME_TRADE: {
                "type": "object",
                "properties": {
                    "give_resource": {"type": "string"},
                    "give_count": {"type": "integer", "minimum": 2, "maximum": 4},
                    "want_resource": {"type": "string"},
                },
                "required": ["give_resource", "give_count", "want_resource"],
                "additionalProperties": False,
            },
            phases.PLACE_FREE_ROAD: {
                "type": "object",
                "properties": {"edge": {"type": "integer", "minimum": 0, "maximum": 71}},
                "required": ["edge"],
                "additionalProperties": False,
            },
            phases.BUILD_ROAD: {
                "type": "object",
                "properties": {"edge": {"type": "integer", "minimum": 0, "maximum": 71}},
                "required": ["edge"],
                "additionalProperties": False,
            },
            phases.BUILD_SETTLEMENT: {
                "type": "object",
                "properties": {"vertex": {"type": "integer", "minimum": 0, "maximum": 53}},
                "required": ["vertex"],
                "additionalProperties": False,
            },
            phases.BUY_DEV_CARD: _no_parameters(),
            phases.PLAY_DEV_CARD: {
                "type": "object",
                "properties": {
                    "card": {"type": "string", "enum": [kind.value for kind in devcards.PLAYABLE]}
                },
                "required": ["card"],
                "additionalProperties": False,
            },
            phases.BUILD_CITY: {
                "type": "object",
                "properties": {"vertex": {"type": "integer", "minimum": 0, "maximum": 53}},
                "required": ["vertex"],
                "additionalProperties": False,
            },
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
    """The actions one request admits, enumerated from the rules that will judge them.

    Every request answers the same two questions - which action types it offers, and which
    targets each of those may name right now - so this is a fold over one table rather than a
    branch per phase, and a phase that offers nothing new needs no new code here.
    """
    player = request.player
    return [
        action for name in _offered(request) for action in _actions_of_type(state, player, name)
    ]


def _offered(request: DecisionRequest) -> list[str]:
    """Which actions one request offers: the list it carries, or the one that answers it."""
    names = request.context.get("actions")
    if isinstance(names, str) or not isinstance(names, Sequence):
        return [request.schema_ref]
    return [str(name) for name in names]


PARAMETER: Final[Mapping[str, str]] = MappingProxyType(
    {
        phases.PLACE_SETTLEMENT: "vertex",
        phases.PLACE_ROAD: "edge",
        phases.BUILD_ROAD: "edge",
        phases.PLACE_FREE_ROAD: "edge",
        phases.BUILD_SETTLEMENT: "vertex",
        phases.BUILD_CITY: "vertex",
        phases.MOVE_ROBBER: "hex",
        phases.CHOOSE_ROBBER_VICTIM: "victim",
    }
)
"""Which parameter carries the board identifier an action names, for the actions that name one.

One table, read by the enumeration *and* by the domain description, because those two are the
same fact stated twice: an action that names a target has exactly one such parameter, and the
values it may take are the targets the rule will accept. Two lists that had to be kept in step
by hand would eventually disagree, and the disagreement would be a promise the engine breaks.
"""


COST_OF: Final[Mapping[str, str]] = MappingProxyType(
    {
        phases.BUILD_ROAD: building.ROAD,
        phases.BUILD_SETTLEMENT: building.SETTLEMENT,
        phases.BUILD_CITY: building.CITY,
        phases.BUY_DEV_CARD: building.DEVELOPMENT_CARD,
    }
)
"""Which price an action pays.

An action is named for what it does and a price for what it buys, and the two are not always the
same word - which is exactly the kind of difference that turns into a silently free build.
Purchasing a development card joins this table with the card that implements it.
"""


def _targets(state: CatanState, player: int, name: str) -> list[int]:
    """The identifiers this action may name right now, in a stable order."""
    if name == phases.PLACE_SETTLEMENT:
        return _legal_settlement_vertices(state)
    if name == phases.PLACE_ROAD:
        return _legal_setup_road_edges(state)
    if name in (phases.BUILD_ROAD, phases.PLACE_FREE_ROAD):
        return list(building.road_targets(state, player))
    if name == phases.BUILD_SETTLEMENT:
        return list(building.settlement_targets(state, player))
    if name == phases.BUILD_CITY:
        return list(building.city_targets(state, player))
    if name == phases.MOVE_ROBBER:
        return list(robber.destinations(state))
    if name == phases.CHOOSE_ROBBER_VICTIM:
        return list(robber.robber_victims(state))
    return []


def _actions_of_type(state: CatanState, player: int, name: str) -> list[Action]:
    """Every action of one offered type, enumerated from the rule that will judge it."""
    if name == phases.DISCARD_RESOURCES:
        return [
            Action(player=player, type=phases.DISCARD_RESOURCES, params=composition)
            for composition in _legal_discards(state, player)
        ]
    if name == phases.PLAY_DEV_CARD:
        return [
            Action(
                player=player,
                type=phases.PLAY_DEV_CARD,
                params={"card": card.value, **told},
            )
            for card in devcards.playable_cards(state, player)
            for told in devcards.choices(state, card)
        ]
    if name == phases.MARITIME_TRADE:
        return [
            Action(
                player=player,
                type=phases.MARITIME_TRADE,
                params={
                    "give_resource": give.value,
                    "give_count": count,
                    "want_resource": want.value,
                },
            )
            for give, count, want in trading.trades(state, player)
        ]
    parameter = PARAMETER.get(name)
    if parameter is None:
        return [Action(player=player, type=name, params={})]
    return [
        Action(player=player, type=name, params={parameter: target})
        for target in _targets(state, player, name)
    ]


def _domain_of(state: CatanState, player: int, name: str) -> ActionDomain:
    """One action type as L1 describes it: what it costs, and what each parameter may be.

    The description is deliberately *not* an enumeration (ARCHITECTURE.md 7.2): a build is one
    entry with a set of edges, not one entry per edge. Two things are worth saying out loud.
    The discard is five counts with a sum the domain shape cannot express, so it is described as
    the range each count may take and the sum is left to the rule - a description may be
    permissive, but it may not promise a value the rule refuses, which is why every other set is
    built from the rule's own target list.
    """
    bought = COST_OF.get(name)
    cost = dict(building.COSTS[bought]) if bought is not None else None
    if name == phases.MARITIME_TRADE:
        available = trading.trades(state, player)
        return ActionDomain(
            type=name,
            cost=None,
            params={
                "give_resource": ParamDomain(
                    kind="id_set",
                    values=sorted({give.value for give, _count, _want in available}),
                ),
                "want_resource": ParamDomain(
                    kind="id_set",
                    values=sorted({want.value for _give, _count, want in available}),
                ),
                "give_count": ParamDomain(kind="int_range", lo=SPECIFIC, hi=GENERAL),
            },
        )
    if name == phases.DISCARD_RESOURCES:
        hand = state.hands[player]
        return ActionDomain(
            type=name,
            cost=cost,
            params={
                resource.value: ParamDomain(kind="int_range", lo=0, hi=hand[index])
                for index, resource in enumerate(RESOURCE_ORDER)
            },
        )
    if name == phases.PLAY_DEV_CARD:
        return ActionDomain(
            type=name,
            cost=cost,
            params={
                "card": ParamDomain(
                    kind="enum",
                    values=[card.value for card in devcards.playable_cards(state, player)],
                )
            },
        )
    parameter = PARAMETER.get(name)
    if parameter is None:
        return ActionDomain(type=name, cost=cost, params={})
    return ActionDomain(
        type=name,
        cost=cost,
        params={parameter: ParamDomain(kind="id_set", values=list(_targets(state, player, name)))},
    )


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
            for site in building.neighbouring_vertices(state, vertex)
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
