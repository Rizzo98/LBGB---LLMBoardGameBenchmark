"""Run configuration (ARCHITECTURE.md sections 5.1, 8.3 and 9; PRD-v1 FR-5.1 to FR-5.4).

The configuration is part of the record, not a convenience: the header carries it and it
round-trips exactly, because a result whose configuration cannot be reconstructed is not
reproducible.

Two decisions worth stating:

- **Assist level and rejection detail are separate fields.** The detail tier defaults to the
  tier that matches the assist level, but is independently overridable, so an experiment can
  run "L1 enumeration, minimal errors" - a genuinely interesting condition - without
  pretending it is L0 (ARCHITECTURE.md section 9.4).
- **Game-declared configuration is opaque to the core.** The core stores the game's options
  and never interprets them (P11), so the wire shape stays flat while the core stays
  game-agnostic. A game option may not shadow a core key, and an undeclared key is an error
  rather than something silently ignored (FR-5.4).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from lgbg.core.types import JsonValue

CORE_KEYS: Final[frozenset[str]] = frozenset(
    {"seed", "players", "assist", "rejection_detail", "interaction_protocol", "prompt_hashes"}
)
"""Keys of the configuration that the core owns. Everything else is the game's."""

REQUIRED_KEYS: Final[tuple[str, ...]] = ("seed", "interaction_protocol")

DEFAULT_PLAYERS: Final[int] = 4
"""Seats in a run. Declared rather than guessed: the record states how many players there were."""


class ConfigError(ValueError):
    """The run configuration cannot be used."""


class AssistLevel(StrEnum):
    """How much help the renderer gives (ARCHITECTURE.md section 9.2). Never affects legality."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class RejectionDetail(StrEnum):
    """How much a rejection explains (ARCHITECTURE.md section 9.2)."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"


DEFAULT_DETAIL_FOR_ASSIST: Final[Mapping[AssistLevel, RejectionDetail]] = MappingProxyType(
    {
        AssistLevel.L0: RejectionDetail.MINIMAL,
        AssistLevel.L1: RejectionDetail.STANDARD,
        AssistLevel.L2: RejectionDetail.FULL,
    }
)


def _as_enum[E: StrEnum](value: JsonValue, enum_type: type[E], field_name: str) -> E:
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string, got {value!r}")
    try:
        return enum_type(value)
    except ValueError:
        accepted = ", ".join(repr(member.value) for member in enum_type)
        raise ConfigError(f"{field_name} {value!r} is not one of {accepted}") from None


def _as_prompt_hashes(value: JsonValue) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"prompt_hashes must be an object, got {value!r}")
    hashes: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise ConfigError(f"prompt_hashes[{key!r}] must be a string, got {item!r}")
        hashes[key] = item
    return hashes


@dataclass(frozen=True, slots=True)
class GameConfig:
    """Configuration declared by a game plugin and carried opaquely by the core (P11)."""

    options: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


@dataclass(frozen=True, slots=True, init=False)
class RunConfig:
    """Everything that describes how a game was run, as recorded in the header."""

    seed: int
    players: int
    assist: AssistLevel
    rejection_detail: RejectionDetail
    interaction_protocol: str
    prompt_hashes: Mapping[str, str]
    game_config: GameConfig

    def __init__(
        self,
        *,
        seed: int,
        interaction_protocol: str,
        players: int = DEFAULT_PLAYERS,
        assist: AssistLevel = AssistLevel.L1,
        rejection_detail: RejectionDetail | None = None,
        prompt_hashes: Mapping[str, str] | None = None,
        game_config: GameConfig | None = None,
    ) -> None:
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "players", players)
        object.__setattr__(self, "assist", assist)
        object.__setattr__(
            self,
            "rejection_detail",
            DEFAULT_DETAIL_FOR_ASSIST[assist] if rejection_detail is None else rejection_detail,
        )
        object.__setattr__(self, "interaction_protocol", interaction_protocol)
        object.__setattr__(self, "prompt_hashes", MappingProxyType(dict(prompt_hashes or {})))
        object.__setattr__(
            self, "game_config", GameConfig() if game_config is None else game_config
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        """The header's 'config' object: core fields and game options, flat."""
        mapping: dict[str, JsonValue] = {
            "seed": self.seed,
            "players": self.players,
            "assist": self.assist.value,
            "rejection_detail": self.rejection_detail.value,
            "interaction_protocol": self.interaction_protocol,
            "prompt_hashes": dict(self.prompt_hashes),
        }
        mapping.update(self.game_config.options)
        return mapping

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, JsonValue],
        *,
        game_option_keys: Collection[str] | None = (),
    ) -> RunConfig:
        """Read a header's 'config' object, rejecting anything unrecognised (FR-5.4).

        'game_option_keys' is what the plugin declares it accepts; without it, a game's own
        keys are as unknown as a misspelling.

        Passing None means "carry every key the core does not own". Reading back a record
        that has already been validated is not the same act as accepting configuration from
        a user: a reader that demanded the plugin's declaration could not read a record
        produced by a plugin that is no longer installed.
        """
        permissive = game_option_keys is None
        declared = frozenset() if game_option_keys is None else frozenset(game_option_keys)
        shadowing = sorted(declared & CORE_KEYS)
        if shadowing:
            raise ConfigError(
                f"game option key(s) {shadowing} would shadow core configuration keys"
            )
        known = CORE_KEYS | declared
        unknown = [] if permissive else sorted(set(raw) - known)
        if unknown:
            raise ConfigError(
                f"unknown configuration key(s) {unknown}; accepted keys are {sorted(known)}"
            )
        missing = [key for key in REQUIRED_KEYS if key not in raw]
        if missing:
            raise ConfigError(f"missing required configuration key(s) {missing}")

        seed = raw["seed"]
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ConfigError(f"seed must be an integer, got {seed!r}")
        protocol = raw["interaction_protocol"]
        if not isinstance(protocol, str):
            raise ConfigError(f"interaction_protocol must be a string, got {protocol!r}")
        players = raw.get("players", DEFAULT_PLAYERS)
        if not isinstance(players, int) or isinstance(players, bool) or players < 2:
            raise ConfigError(f"players must be an integer of at least 2, got {players!r}")
        detail = raw.get("rejection_detail")

        return cls(
            seed=seed,
            players=players,
            assist=_as_enum(raw.get("assist", AssistLevel.L1.value), AssistLevel, "assist"),
            rejection_detail=(
                None if detail is None else _as_enum(detail, RejectionDetail, "rejection_detail")
            ),
            interaction_protocol=protocol,
            prompt_hashes=_as_prompt_hashes(raw.get("prompt_hashes", {})),
            # Whatever the core does not own is the game's. In strict mode the only such keys
            # that survive are the declared ones, because unknown keys were rejected above.
            game_config=GameConfig({key: raw[key] for key in raw if key not in CORE_KEYS}),
        )
