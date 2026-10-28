"""The design one game sits in, as the manifest records it (PRD-v2 FR-11.3, FR-11.10).

The runner does not choose an experiment design; it *carries* one. This module is the value the
manifest writes and the record can be read back from: which seats were varied, which starting
configuration was used, how many replicates the experiment declared, and the derivation that turns
those decisions into a game count rather than a number somebody stated.

Two values live here, and the split is the whole point. `ExperimentDesign` is what a run *asks
for*: three independent axes and a replicate count. `GameDesign` is what one game *records*: those
axes, the derivation they produced, and the game's own replicate and rotation index. The matrix
turns the first into the second. A game that cannot vary an axis is not asked to - a random
configuration from a single fixed start is a configuration error - and a design that pins an axis
the game could have varied carries that axis as uncontrolled (FR-11.11, FR-11.12). The single-game
exploration case is first-class and is what an undeclared design gives (FR-11.13). A game that
cannot say which design produced it cannot be compared with any other run (FR-11.10), and that is
true even for a single exploration game.

Nothing in this module names a game. A configuration is a label the caller declares - the game's own
options travel opaquely in the run config - so a game with one fixed starting position, and a game
that can deal a hundred, are recorded by the same code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from lgbg.core.game import BenchmarkProfile
from lgbg.core.types import JsonValue

SEATING: Final[tuple[str, ...]] = ("fixed", "random", "rotated")
"""How seat assignment varies (FR-11.3). Rotation is N cyclic shifts, K-028's matrix."""

ROTATED_SEATING: Final[str] = "rotated"
"""The seating rule that makes the game count one per seat (FR-11.9)."""

RANDOM_CONFIGURATION: Final[str] = "random"
"""The configuration axis value that asks for a draw rather than a named position (FR-11.3)."""

CONFIGURATION_SCOPES: Final[tuple[str, ...]] = ("per_experiment", "per_game")
"""Whether a random configuration is drawn once for the experiment or once per game (FR-11.3)."""

AXIS_SEATING: Final[str] = "seating"
"""The seat-assignment axis. It varies in every game with more than one seat (FR-11.11)."""

AXIS_INITIAL_CONFIGURATION: Final[str] = "initial_configuration"
"""The starting-position axis. It varies only where the game can vary it (K-029, FR-11.11)."""

AXES: Final[tuple[str, ...]] = (AXIS_INITIAL_CONFIGURATION, AXIS_SEATING)
"""The two independent axes a design either controls or marks as uncontrolled (FR-11.12)."""

DERIVATION_RULE: Final[str] = "games = replicates x seatings"
"""The rule the game count follows, recorded so the product is traceable to a decision (FR-11.4)."""


class DesignError(ValueError):
    """The declared design cannot be recorded as a point in an experiment."""


def _check_configuration(initial_configuration: str, profile: BenchmarkProfile) -> None:
    """A random draw is a request the game must be able to honour (FR-11.11)."""
    if initial_configuration == RANDOM_CONFIGURATION and not profile.configuration_is_variable:
        raise DesignError(
            "this game declares a single fixed starting position, so a random initial "
            "configuration cannot be drawn; declare a fixed configuration instead"
        )


def _check_axes(
    *,
    seating: str,
    initial_configuration: str,
    configuration_scope: str,
    replicates: int,
) -> None:
    """The three axes and the replicate count, validated once for the request and for the record."""
    if seating not in SEATING:
        raise DesignError(f"seating {seating!r} is not one of {SEATING}")
    if configuration_scope not in CONFIGURATION_SCOPES:
        raise DesignError(
            f"configuration_scope {configuration_scope!r} is not one of {CONFIGURATION_SCOPES}"
        )
    if not initial_configuration:
        raise DesignError("a design must name the initial configuration it used")
    if not isinstance(replicates, int) or isinstance(replicates, bool):
        raise DesignError(f"replicates must be an integer, got {replicates!r}")
    if replicates < 1:
        raise DesignError("replicates must be at least 1")


@dataclass(frozen=True, slots=True)
class ExperimentDesign:
    """What a run asks for: the three axes, and how many independent experiments to play (FR-11.3).

    Exactly what the PRD calls the design: `seating`, `initial_configuration` and `replicates`.
    The initial configuration's scope is the second half of the configuration axis - *where* a
    random draw happens - and it is meaningless for a fixed configuration, which draws nothing.
    """

    seating: str = SEATING[0]
    initial_configuration: str = "fixed"
    configuration_scope: str = CONFIGURATION_SCOPES[0]
    replicates: int = 1

    def __post_init__(self) -> None:
        _check_axes(
            seating=self.seating,
            initial_configuration=self.initial_configuration,
            configuration_scope=self.configuration_scope,
            replicates=self.replicates,
        )

    @classmethod
    def exploration(cls, profile: BenchmarkProfile) -> ExperimentDesign:
        """The one-game design an undeclared run gives (FR-11.13).

        Exploration draws both axes where the game can draw them: seats are assigned at random
        and, when the plugin declares a variable starting position, so is the configuration. A
        game with a single opening position is explored at that position rather than asked for a
        draw it cannot make (FR-11.11), which is what keeps the one-game case first-class for
        every game and not only for the ones with a setup.
        """
        return cls(
            seating="random",
            initial_configuration=(
                RANDOM_CONFIGURATION if profile.configuration_is_variable else "fixed"
            ),
            replicates=1,
        )

    @property
    def draws_per_game(self) -> bool:
        """Whether a random starting position is drawn for every game rather than per replicate."""
        return (
            self.initial_configuration == RANDOM_CONFIGURATION
            and self.configuration_scope == CONFIGURATION_SCOPES[1]
        )

    def check(self, profile: BenchmarkProfile, seats: int) -> None:
        """Refuse a design the game cannot carry out (FR-11.11).

        A game with a single fixed starting position cannot draw another one, so asking for a
        random configuration is a configuration error rather than a request to ignore. The
        seating rule is checked here too, so a rotated design over one seat fails before any
        game is planned.
        """
        _check_configuration(self.initial_configuration, profile)
        self.seatings(seats)

    def seatings(self, seats: int) -> int:
        """How many seat assignments one replicate contains (FR-11.4, FR-11.9).

        A rotated design is exactly one seat assignment per seat; every other rule is one game
        per replicate.
        """
        if self.seating != ROTATED_SEATING:
            return 1
        if seats < 2:
            raise DesignError("a rotated design needs at least two seats")
        return seats

    def game_count(self, seats: int) -> int:
        """The product the manifest records, never a number stated separately (FR-11.4)."""
        return self.replicates * self.seatings(seats)

    def derivation(self, seats: int) -> dict[str, JsonValue]:
        """The derivation itself, so a game count can be traced to a decision."""
        return {
            "rule": DERIVATION_RULE,
            "replicates": self.replicates,
            "seatings": self.seatings(seats),
            "games": self.game_count(seats),
        }

    def uncontrolled(self, profile: BenchmarkProfile, seats: int) -> tuple[str, ...]:
        """The axes this design does not vary, as far as the game's declaration lets us know.

        Both marks are caveats, not facts about the game. A pinned seat order is a caveat only
        when the game says seat order matters, which is what the plugin's profile declares
        (ARCHITECTURE 7.10); randomised seating controls the axis in expectation and rotation
        controls it exactly, so neither is marked. A fixed starting configuration is a caveat
        only when the game could have varied it: a game with a single opening position has no
        configuration variance to control, and marking it would invent a caveat where there is
        nothing to caveat. A random configuration is the axis being controlled.
        """
        uncontrolled: list[str] = []
        if self.initial_configuration != RANDOM_CONFIGURATION and profile.configuration_is_variable:
            uncontrolled.append(AXIS_INITIAL_CONFIGURATION)
        if self.seating == SEATING[0] and seats > 1 and profile.positional_asymmetry:
            uncontrolled.append(AXIS_SEATING)
        return tuple(uncontrolled)


@dataclass(frozen=True, slots=True)
class GameDesign:
    """One game's point in the design: what varied, what did not, and how the count follows."""

    seating: str = SEATING[0]
    initial_configuration: str = "fixed"
    configuration_scope: str = CONFIGURATION_SCOPES[0]
    replicates: int = 1
    uncontrolled: tuple[str, ...] = ()
    derivation: Mapping[str, JsonValue] = field(default_factory=dict)
    replicate: int = 0
    rotation: int = 0

    def __post_init__(self) -> None:
        _check_axes(
            seating=self.seating,
            initial_configuration=self.initial_configuration,
            configuration_scope=self.configuration_scope,
            replicates=self.replicates,
        )
        axes = tuple(self.uncontrolled)
        unknown = sorted(set(axes) - set(AXES))
        if unknown:
            raise DesignError(f"uncontrolled axis(es) {unknown} are not one of {AXES}")
        derivation = dict(self.derivation) if self.derivation else self._derived()
        replicates, seatings = _check_derivation(derivation, replicates=self.replicates)
        _check_point(
            replicate=self.replicate,
            rotation=self.rotation,
            replicates=replicates,
            seatings=seatings,
        )
        object.__setattr__(self, "uncontrolled", axes)
        object.__setattr__(self, "derivation", MappingProxyType(derivation))

    @classmethod
    def exploration(cls, profile: BenchmarkProfile, *, seats: int = 1) -> GameDesign:
        """The one-game point an undeclared run records (FR-11.13).

        It is the record side of `ExperimentDesign.exploration`: random seats, the configuration
        the game can offer, one game, and the caveat the profile's declarations imply.
        """
        request = ExperimentDesign.exploration(profile)
        return cls(
            seating=request.seating,
            initial_configuration=request.initial_configuration,
            configuration_scope=request.configuration_scope,
            replicates=request.replicates,
            uncontrolled=request.uncontrolled(profile, seats),
        )

    def check(self, profile: BenchmarkProfile) -> None:
        """Refuse a recorded design that asks for an axis the game does not have (FR-11.11).

        The matrix checks the request before it plans; this is the same refusal at the manifest
        seam, so a caller that hands one game a design directly cannot smuggle in a random draw
        the game will silently ignore.
        """
        _check_configuration(self.initial_configuration, profile)

    def to_mapping(self) -> dict[str, JsonValue]:
        """The `design` object of run.json, exactly as the manifest shape declares it."""
        return {
            "seating": self.seating,
            "initial_configuration": self.initial_configuration,
            "configuration_scope": self.configuration_scope,
            "replicates": self.replicates,
            "uncontrolled": list(self.uncontrolled),
            "derivation": dict(self.derivation),
            "replicate": self.replicate,
            "rotation": self.rotation,
        }

    def _derived(self) -> dict[str, JsonValue]:
        """A derivation consistent with the declared replicate count, for a caller with one game.

        The seating factor is the matrix's business: a rotated design is one game per seat, which
        the matrix computes, so a caller that declares one supplies the derivation it used.
        """
        return {
            "rule": DERIVATION_RULE,
            "replicates": self.replicates,
            "seatings": 1,
            "games": self.replicates,
        }


def _check_derivation(derivation: Mapping[str, JsonValue], *, replicates: int) -> tuple[int, int]:
    """The recorded derivation must add up; a product nobody can reconstruct is not a derivation.

    Returns the two factors, so a caller checking a game's point does not read untyped JSON twice.
    """
    required = ("rule", "replicates", "seatings", "games")
    missing = [key for key in required if key not in derivation]
    unexpected = sorted(set(derivation) - set(required))
    if missing or unexpected:
        raise DesignError(
            f"the derivation must declare exactly {list(required)}; "
            f"missing {missing}, unexpected {unexpected}"
        )
    rule = derivation["rule"]
    if not isinstance(rule, str) or not rule:
        raise DesignError("the derivation must state the rule it used")
    numbers: dict[str, int] = {}
    for key in ("replicates", "seatings", "games"):
        value = derivation[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DesignError(f"derivation.{key} must be a non-negative integer, got {value!r}")
        numbers[key] = value
    if numbers["replicates"] != replicates:
        raise DesignError(
            f"the derivation says {numbers['replicates']} replicate(s) but the design declares "
            f"{replicates}"
        )
    if numbers["seatings"] < 1:
        raise DesignError("the derivation needs at least one seating")
    if numbers["games"] != numbers["replicates"] * numbers["seatings"]:
        raise DesignError(
            f"the derivation does not add up: {numbers['replicates']} x {numbers['seatings']} "
            f"is not {numbers['games']}"
        )
    return numbers["replicates"], numbers["seatings"]


def _check_point(*, replicate: int, rotation: int, replicates: int, seatings: int) -> None:
    """A game cannot claim a point outside the experiment that produced it (FR-11.10)."""
    for name, value in (("replicate", replicate), ("rotation", rotation)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DesignError(f"{name} must be a non-negative integer, got {value!r}")
    if replicate >= replicates:
        raise DesignError(f"replicate {replicate} is outside a design of {replicates} replicate(s)")
    if rotation >= seatings:
        raise DesignError(f"rotation {rotation} is outside a design of {seatings} seating(s)")


def declared_seating() -> Sequence[str]:
    """The seating rules a run may declare, for a caller that needs the vocabulary only."""
    return SEATING


__all__: list[str] = [
    "AXES",
    "AXIS_INITIAL_CONFIGURATION",
    "AXIS_SEATING",
    "CONFIGURATION_SCOPES",
    "DERIVATION_RULE",
    "RANDOM_CONFIGURATION",
    "ROTATED_SEATING",
    "SEATING",
    "DesignError",
    "ExperimentDesign",
    "GameDesign",
    "declared_seating",
]
