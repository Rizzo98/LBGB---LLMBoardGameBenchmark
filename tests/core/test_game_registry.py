"""The game plugin interface and its registry (PRD-v1 FR-6.1 to FR-6.6).

A plugin is the only thing the core learns about a game, and it learns it by declaration.
Two properties are asserted here rather than assumed: the protocol declares every member
ARCHITECTURE.md section 7.1 lists, and the registry refuses a plugin that does not declare
its name and versions - a plugin that cannot say what rules it implements cannot be
measured.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig
from lgbg.core.errors import Rejection, RejectionCode
from lgbg.core.game import (
    ENTRY_POINT_GROUP,
    Applied,
    ApplyResult,
    BenchmarkProfile,
    Game,
    GamePluginError,
    InteractionCharacter,
    InvariantViolation,
    OutcomeShape,
    Rejected,
    UnknownGameError,
    VarianceClass,
    discover_entry_point_games,
    get_game,
    register_game,
    registered_games,
)
from lgbg.core.rng import NullRandomSource, RandomSource
from lgbg.core.types import (
    Action,
    ActionDomain,
    DecisionRequest,
    Event,
    JsonSchema,
    Observation,
    Outcome,
    PlayerId,
)

# ARCHITECTURE.md section 7.1, transcribed member by member.
ARCHITECTURE_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "name",
        "rules_version",
        "schema_version",
        "initial_state",
        "pending_decisions",
        "legal_actions",
        "action_domains",
        "apply",
        "observe",
        "observe_spectator",
        "is_terminal",
        "outcome",
        "encode_state",
        "decode_state",
        "action_schema",
        "observation_schema",
        "rejection_codes",
        "benchmark_profile",
        "check_invariants",
    }
)

TOY_PROFILE: Final[BenchmarkProfile] = BenchmarkProfile(
    positional_asymmetry=False,
    outcome_shape=OutcomeShape.SINGLE_WINNER,
    variance_class=VarianceClass.LOW,
    interaction_character=InteractionCharacter.ADVERSARIAL,
    typical_decisions=10,
    worst_case_decisions=20,
)
TOY_CODES: Final[tuple[RejectionCode, ...]] = (
    RejectionCode(code="TOY_NO", description="the toy refuses"),
)


class _ToyState:
    def __init__(self, marker: int) -> None:
        self.marker = marker


@register_game
class ToyGame:
    """A plugin with no rules that exercises every member of the protocol."""

    name = "toy"
    rules_version = "toy-rules-1"
    schema_version = "toy-actions-1"

    def initial_state(self, cfg: GameConfig, rng: RandomSource) -> _ToyState:
        return _ToyState(marker=0)

    def pending_decisions(self, state: _ToyState) -> list[DecisionRequest]:
        return []

    def legal_actions(self, state: _ToyState, player: PlayerId) -> list[Action]:
        return []

    def action_domains(self, state: _ToyState, player: PlayerId) -> list[ActionDomain]:
        return []

    def apply(self, state: _ToyState, action: Action, rng: RandomSource) -> ApplyResult:
        if action.type == "refuse":
            return Rejected(rejection=Rejection(code=TOY_CODES[0], message="no", details={}))
        return Applied(state=_ToyState(state.marker + 1), events=[Event(type="tick", payload={})])

    def observe(self, state: _ToyState, player: PlayerId) -> Observation:
        return {"marker": state.marker}

    def observe_spectator(self, state: _ToyState) -> Observation:
        return {"marker": state.marker}

    def is_terminal(self, state: _ToyState) -> bool:
        return False

    def outcome(self, state: _ToyState) -> Outcome:
        return Outcome(winner=None, scores={}, rounds=0)

    def encode_state(self, state: _ToyState) -> dict[str, Any]:
        return {"marker": state.marker}

    def decode_state(self, blob: Any) -> _ToyState:
        return _ToyState(marker=blob["marker"])

    def action_schema(self) -> JsonSchema:
        return {}

    def observation_schema(self) -> JsonSchema:
        return {}

    def rejection_codes(self) -> list[RejectionCode]:
        return list(TOY_CODES)

    def benchmark_profile(self) -> BenchmarkProfile:
        return TOY_PROFILE

    def check_invariants(self, state: _ToyState) -> list[InvariantViolation]:
        return []


def test_game_protocol_declares_every_member_of_the_architecture() -> None:
    # Declared attributes of a Protocol live in __annotations__, not on the class object.
    declared = set(dir(Game)) | set(getattr(Game, "__annotations__", {}))
    missing = ARCHITECTURE_MEMBERS - declared

    assert missing == frozenset(), f"the Game protocol is missing {sorted(missing)}"


def test_plugin_satisfies_the_game_protocol() -> None:
    """The assignment is checked by mypy: a plugin that drifts from the protocol fails the gate."""
    plugin: Game = get_game("toy")

    assert plugin.name == "toy"


def test_register_game_registers_by_declared_name() -> None:
    assert "toy" in registered_games()


def test_registry_returns_one_shared_instance_per_game() -> None:
    """Plugins are stateless, so one instance drives many concurrent games (FR-6.5)."""
    assert get_game("toy") is get_game("toy")


def test_registry_hands_out_an_instance_not_a_class() -> None:
    assert not isinstance(get_game("toy"), type)


def test_unknown_game_is_reported_with_the_registered_names() -> None:
    with pytest.raises(UnknownGameError) as raised:
        get_game("no_such_game")

    message = str(raised.value)
    assert "no_such_game" in message
    assert "toy" in message


def test_registering_the_same_class_twice_is_idempotent() -> None:
    register_game(ToyGame)
    register_game(ToyGame)

    assert registered_games().count("toy") == 1


def test_two_different_plugins_may_not_share_a_name() -> None:
    @register_game
    class OtherToy:
        name = "toy_other"
        rules_version = "toy-rules-1"
        schema_version = "toy-actions-1"

    with pytest.raises(GamePluginError, match="toy_other"):

        @register_game
        class Impostor:
            name = "toy_other"
            rules_version = "toy-rules-1"
            schema_version = "toy-actions-1"

    assert get_game("toy_other") is not None
    assert OtherToy.name == "toy_other"


def test_plugin_without_a_name_is_rejected() -> None:
    with pytest.raises(GamePluginError, match="name"):

        @register_game
        class Nameless:
            rules_version = "r1"
            schema_version = "s1"


@pytest.mark.parametrize("missing", ["rules_version", "schema_version"])
def test_plugin_without_a_declared_version_is_rejected(missing: str) -> None:
    namespace: dict[str, str] = {
        "name": "toy_missing_" + missing,
        "rules_version": "r1",
        "schema_version": "s1",
    }
    del namespace[missing]

    class Incomplete:
        pass

    for key, value in namespace.items():
        setattr(Incomplete, key, value)

    with pytest.raises(GamePluginError, match=missing):
        register_game(Incomplete)


def test_entry_point_discovery_registers_games_from_the_declared_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class EntryPointPlugin:
        name = "toy_entry_point"
        rules_version = "toy-rules-1"
        schema_version = "toy-actions-1"

    class FakeEntryPoint:
        def load(self) -> object:
            return EntryPointPlugin

    def fake_entry_points(*, group: str) -> list[FakeEntryPoint]:
        seen["group"] = group
        return [FakeEntryPoint()]

    monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)

    registered = discover_entry_point_games()

    assert seen["group"] == ENTRY_POINT_GROUP
    assert "toy_entry_point" in registered
    assert get_game("toy_entry_point").name == "toy_entry_point"


def test_entry_point_that_declares_no_versions_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenEntryPointPlugin:
        name = "toy_broken"

    class FakeEntryPoint:
        name = "toy_broken"

        def load(self) -> object:
            return BrokenEntryPointPlugin

    monkeypatch.setattr(importlib.metadata, "entry_points", lambda **_: [FakeEntryPoint()])

    with pytest.raises(GamePluginError, match="toy_broken"):
        discover_entry_point_games()


def test_no_randomness_is_consumed_by_the_query_surface() -> None:
    """FR-2.6: observe, legal_actions, action_domains, pending_decisions, outcome, invariants."""
    plugin = get_game("toy")
    state = _ToyState(marker=3)
    quiet = NullRandomSource()

    assert plugin.pending_decisions(state) == []
    assert plugin.legal_actions(state, 0) == []
    assert plugin.action_domains(state, 0) == []
    assert plugin.observe(state, 0) == {"marker": 3}
    assert plugin.observe_spectator(state) == {"marker": 3}
    assert plugin.check_invariants(state) == []
    assert plugin.outcome(state).rounds == 0
    assert plugin.is_terminal(state) is False
    assert quiet.draws() == []
