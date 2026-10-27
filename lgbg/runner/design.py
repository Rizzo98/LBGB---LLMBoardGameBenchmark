"""The design one game sits in, as the manifest records it (PRD-v2 FR-11.3, FR-11.10).

The runner does not choose an experiment design; it *carries* one. This module is the value the
manifest writes and the record can be read back from: which seats were varied, which starting
configuration was used, how many replicates the experiment declared, and the derivation that turns
those decisions into a game count rather than a number somebody stated.

That distinction is the point. K-028 builds the design matrix - it is what turns `replicates` and
a seating rule into the games a run contains - and K-029 decides what happens when a game cannot
vary an axis. The runner core only has to record the point each game occupies, which is why this
value exists here and the matrix does not: a game that cannot say which design produced it cannot be
compared with any other run (FR-11.10), and that is true even for a single exploration game.

Nothing in this module names a game. A configuration is a label the caller declares - the game's own
options travel opaquely in the run config - so a game with one fixed starting position, and a game
that can deal a hundred, are recorded by the same code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from lgbg.core.types import JsonValue

SEATING: Final[tuple[str, ...]] = ("fixed", "random", "rotated")
"""How seat assignment varies (FR-11.3). Rotation is N cyclic shifts, K-028's matrix."""

CONFIGURATION_SCOPES: Final[tuple[str, ...]] = ("per_experiment", "per_game")
"""Whether a random configuration is drawn once for the experiment or once per game (FR-11.3)."""

AXES: Final[tuple[str, ...]] = ("initial_configuration", "seating")
"""The two independent axes a design either controls or marks as uncontrolled (FR-11.12)."""

DERIVATION_RULE: Final[str] = "games = replicates x seatings"
"""The rule the game count follows, recorded so the product is traceable to a decision (FR-11.4)."""


class DesignError(ValueError):
    """The declared design cannot be recorded as a point in an experiment."""


@dataclass(frozen=True, slots=True)
class GameDesign:
    """One game's point in the design: what varied, what did not, and how the count follows."""

    seating: str = SEATING[0]
    initial_configuration: str = "fixed"
    configuration_scope: str = CONFIGURATION_SCOPES[0]
    replicates: int = 1
    uncontrolled: tuple[str, ...] = ()
    derivation: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.seating not in SEATING:
            raise DesignError(f"seating {self.seating!r} is not one of {SEATING}")
        if self.configuration_scope not in CONFIGURATION_SCOPES:
            raise DesignError(
                f"configuration_scope {self.configuration_scope!r} is not one of "
                f"{CONFIGURATION_SCOPES}"
            )
        if not self.initial_configuration:
            raise DesignError("a design must name the initial configuration it used")
        if not isinstance(self.replicates, int) or isinstance(self.replicates, bool):
            raise DesignError(f"replicates must be an integer, got {self.replicates!r}")
        if self.replicates < 1:
            raise DesignError("replicates must be at least 1")
        axes = tuple(self.uncontrolled)
        unknown = sorted(set(axes) - set(AXES))
        if unknown:
            raise DesignError(f"uncontrolled axis(es) {unknown} are not one of {AXES}")
        derivation = dict(self.derivation) if self.derivation else self._derived()
        _check_derivation(derivation, replicates=self.replicates)
        object.__setattr__(self, "uncontrolled", axes)
        object.__setattr__(self, "derivation", MappingProxyType(derivation))

    @classmethod
    def single_game(cls, *, initial_configuration: str = "fixed") -> GameDesign:
        """The one-game exploration case: no replicates, one seating, a declared configuration."""
        return cls(initial_configuration=initial_configuration)

    def to_mapping(self) -> dict[str, JsonValue]:
        """The `design` object of run.json, exactly as the manifest shape declares it."""
        return {
            "seating": self.seating,
            "initial_configuration": self.initial_configuration,
            "configuration_scope": self.configuration_scope,
            "replicates": self.replicates,
            "uncontrolled": list(self.uncontrolled),
            "derivation": dict(self.derivation),
        }

    def _derived(self) -> dict[str, JsonValue]:
        """A derivation consistent with the declared replicate count, for a caller with one game.

        The seating factor is the matrix's business: a rotated design is one game per seat, which
        only K-028 can compute, so a caller that declares one supplies the derivation it used.
        """
        return {
            "rule": DERIVATION_RULE,
            "replicates": self.replicates,
            "seatings": 1,
            "games": self.replicates,
        }


def _check_derivation(derivation: Mapping[str, JsonValue], *, replicates: int) -> None:
    """The recorded derivation must add up; a product nobody can reconstruct is not a derivation."""
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
    if numbers["games"] != numbers["replicates"] * numbers["seatings"]:
        raise DesignError(
            f"the derivation does not add up: {numbers['replicates']} x {numbers['seatings']} "
            f"is not {numbers['games']}"
        )


def declared_seating() -> Sequence[str]:
    """The seating rules a run may declare, for a caller that needs the vocabulary only."""
    return SEATING


__all__: list[str] = [
    "AXES",
    "CONFIGURATION_SCOPES",
    "DERIVATION_RULE",
    "SEATING",
    "DesignError",
    "GameDesign",
    "declared_seating",
]
