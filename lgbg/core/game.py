"""The game plugin interface and its registry (ARCHITECTURE.md sections 7.1 to 7.4).

The core knows nothing about any game; everything game-specific reaches it as a
*declaration* from a plugin. This module is that contract, and the only place the core
learns that games exist at all.

The interface is stated over 'Any' for state, and that is a deliberate boundary rather
than laziness: state is game-specific, so a core that named its type would not be
game-agnostic (P11). Plugins state their own state type, and the conformance of a plugin
to this protocol is checked by the type checker at every call site the plugin itself
controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata
from typing import Any, Final, Protocol

from lgbg.core.config import GameConfig
from lgbg.core.errors import Rejection, RejectionCode
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
    State,
)

ENTRY_POINT_GROUP: Final[str] = "lgbg.games"
"""Entry point group used to discover games installed as separate distributions."""


class GamePluginError(Exception):
    """A plugin cannot be registered or used as a game."""


class UnknownGameError(GamePluginError):
    """No game is registered under that name."""


class OutcomeShape(StrEnum):
    """What a result looks like, which decides which statistics mean anything."""

    SINGLE_WINNER = "single_winner"
    RANKED = "ranked"
    SCORED = "scored"


class VarianceClass(StrEnum):
    """How many games a pairing needs before a signal is usable."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InteractionCharacter(StrEnum):
    """Whether a shared score means one thing: adversarial, cooperative, or mixed."""

    ADVERSARIAL = "adversarial"
    COOPERATIVE = "cooperative"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class BenchmarkProfile:
    """The facts the platform needs to choose a valid experimental design (7.10).

    None of these can be inferred from code, and hardcoding them in the runner would make
    the runner game-specific.
    """

    positional_asymmetry: bool
    outcome_shape: OutcomeShape
    variance_class: VarianceClass
    interaction_character: InteractionCharacter
    typical_decisions: int
    worst_case_decisions: int


@dataclass(frozen=True, slots=True)
class InvariantViolation:
    """One conservation law broken by one state, reported by the plugin (7.11)."""

    invariant: str
    detail: str


@dataclass(frozen=True, slots=True)
class Applied:
    """A successful application: a whole new state, and the events that describe it."""

    state: State
    events: list[Event]


@dataclass(frozen=True, slots=True)
class Rejected:
    """A refused application. The state is untouched, so its hash cannot change."""

    rejection: Rejection


type ApplyResult = Applied | Rejected


class Game(Protocol):
    """One game, implemented by one self-contained plugin (ARCHITECTURE.md section 7.1).

    Implementations MUST be stateless: no instance state may survive across 'apply' calls,
    so that one instance can drive many concurrent games.
    """

    name: str
    rules_version: str
    schema_version: str

    # --- lifecycle ---
    def initial_state(self, cfg: GameConfig, rng: RandomSource) -> State: ...

    # --- decision surface ---
    def pending_decisions(self, state: State) -> list[DecisionRequest]: ...

    def legal_actions(self, state: State, player: PlayerId) -> list[Action]: ...

    def action_domains(self, state: State, player: PlayerId) -> list[ActionDomain]: ...

    # --- transitions ---
    def apply(self, state: State, action: Action, rng: RandomSource) -> ApplyResult: ...

    # --- observation ---
    def observe(self, state: State, player: PlayerId) -> Observation: ...

    def observe_spectator(self, state: State) -> Observation: ...

    # --- terminality ---
    def is_terminal(self, state: State) -> bool: ...

    def outcome(self, state: State) -> Outcome: ...

    # --- serialisation and declared schemas ---
    def encode_state(self, state: State) -> JsonValue: ...

    def decode_state(self, blob: Any) -> State: ...

    def action_schema(self) -> JsonSchema: ...

    def observation_schema(self) -> JsonSchema: ...

    def rejection_codes(self) -> list[RejectionCode]: ...

    # --- declarations the platform needs and must not guess ---
    def benchmark_profile(self) -> BenchmarkProfile: ...

    def check_invariants(self, state: State) -> list[InvariantViolation]: ...


_GAME_CLASSES: dict[str, type[Any]] = {}
_GAME_INSTANCES: dict[str, Game] = {}


def register_game[G](plugin: type[G]) -> type[G]:
    """Register a plugin under its declared name. Usable as a decorator.

    A plugin that cannot say what rules and schema it implements cannot be measured, so a
    missing declaration is refused here rather than discovered later in a record.
    """
    name = getattr(plugin, "name", None)
    if not isinstance(name, str) or not name:
        raise GamePluginError(f"{plugin.__name__} must declare a non-empty 'name'")
    for declaration in ("rules_version", "schema_version"):
        value = getattr(plugin, declaration, None)
        if not isinstance(value, str) or not value:
            raise GamePluginError(f"game {name!r} must declare a non-empty {declaration!r}")
    existing = _GAME_CLASSES.get(name)
    if existing is not None and existing is not plugin:
        raise GamePluginError(f"game name {name!r} is already registered by {existing.__name__}")
    _GAME_CLASSES[name] = plugin
    return plugin


def registered_games() -> list[str]:
    """Every registered game name, sorted, so the order never depends on registration."""
    return sorted(_GAME_CLASSES)


def get_game(name: str) -> Game:
    """The one shared instance of a registered game.

    Shared because plugins are stateless (FR-6.5); a per-call instance would hide a plugin
    that keeps state, and the record would then depend on who called first.
    """
    if name not in _GAME_CLASSES:
        raise UnknownGameError(f"unknown game {name!r}; registered games are {registered_games()}")
    instance = _GAME_INSTANCES.get(name)
    if instance is None:
        instance = _GAME_CLASSES[name]()
        _GAME_INSTANCES[name] = instance
    return instance


def discover_entry_point_games(group: str = ENTRY_POINT_GROUP) -> list[str]:
    """Register games installed as separate distributions (FR-6.4).

    In-repo games use the decorator; this is the path for a game that lives in its own
    package, which is the point of a plugin interface.
    """
    registered: list[str] = []
    for entry_point in metadata.entry_points(group=group):
        try:
            loaded = entry_point.load()
        except Exception as error:
            raise GamePluginError(
                f"entry point {entry_point.name!r} in group {group!r} failed to load: {error}"
            ) from error
        if not isinstance(loaded, type):
            raise GamePluginError(
                f"entry point {entry_point.name!r} in group {group!r} must name a class"
            )
        plugin: type[Any] = loaded
        register_game(plugin)
        registered.append(plugin.name)
    return registered
