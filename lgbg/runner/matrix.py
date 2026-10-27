"""The experiment-design matrix: from three axes to the games a run contains (PRD-v2 FR-11.3,
FR-11.4, FR-11.9, FR-11.10).

A run is not one game played N times. It is a set of games whose *points in the design* are declared
before any of them is played, so that a result can be attributed to a seat assignment and a starting
position rather than to chance. This module is what turns `ExperimentDesign` into that set:

- **fixed** seating keeps the table as declared;
- **rotated** seating is the N cyclic shifts of it, so every agent occupies every seat index equally
  often - including an agent that holds several seats, with no special case (FR-11.9);
- **random** seating is one drawn permutation per replicate, derived from the run's seed.

Two rules are worth stating because they are what make a comparison mean something:

- **The count is a product, and the product is recorded.** `games = replicates x seatings`, and the
  derivation travels with every game (FR-11.4).
- **A replicate is mirrored.** The rotations of one replicate share a seed, so the board and the
  dice are the same and only the seats change; a random starting position drawn per game is the one
  declared exception, because then the draw *is* per game (FR-11.3).

Nothing here names a game. The only game fact the matrix consumes is the plugin's benchmark profile,
and the one thing it asks of it is whether seat order matters - which is what decides whether a
pinned seating is a caveat the record must carry (ARCHITECTURE 7.10, FR-11.12).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from lgbg.core.game import BenchmarkProfile
from lgbg.core.rng import Purpose, SeededRandomSource
from lgbg.core.types import PlayerId
from lgbg.runner.agents import Agent
from lgbg.runner.design import (
    ROTATED_SEATING,
    DesignError,
    ExperimentDesign,
    GameDesign,
)

SEATING_SHUFFLE: Final[Purpose] = "experiment_seating_shuffle"
"""The one draw the matrix makes: the permutation of a random seating. Named, never inline."""

GAME_SEED_LABEL: Final[str] = "lgbg.experiment"
"""The label every derived seed is hashed under, so a seed is a decision rather than an accident."""


@dataclass(frozen=True, slots=True)
class PlannedGame:
    """One game the matrix produced: where it sits in the design, who plays where, and its seed."""

    index: int
    design: GameDesign
    seats: tuple[Agent, ...]
    seed: int

    def seat_map(self) -> dict[PlayerId, Agent]:
        """The assignment in the form the runner takes: seat number to agent."""
        return dict(enumerate(self.seats))


def plan(
    *,
    design: ExperimentDesign,
    table: Sequence[Agent],
    seed: int,
    profile: BenchmarkProfile,
) -> tuple[PlannedGame, ...]:
    """Every game this design declares, in replicate-then-rotation order."""
    seats = len(table)
    if seats < 2:
        raise DesignError("an experiment needs at least two seats")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise DesignError(f"the experiment seed must be an integer, got {seed!r}")
    derivation = design.derivation(seats)
    uncontrolled = design.uncontrolled(profile, seats)
    planned: list[PlannedGame] = []
    for replicate in range(design.replicates):
        assignments = _assignments(design, table, seed=seed, replicate=replicate)
        for rotation, assignment in enumerate(assignments):
            planned.append(
                PlannedGame(
                    index=len(planned),
                    design=GameDesign(
                        seating=design.seating,
                        initial_configuration=design.initial_configuration,
                        configuration_scope=design.configuration_scope,
                        replicates=design.replicates,
                        uncontrolled=uncontrolled,
                        derivation=derivation,
                        replicate=replicate,
                        rotation=rotation,
                    ),
                    seats=assignment,
                    seed=_game_seed(
                        seed,
                        replicate=replicate,
                        rotation=rotation,
                        draws_per_game=design.draws_per_game,
                    ),
                )
            )
    return tuple(planned)


def _assignments(
    design: ExperimentDesign, table: Sequence[Agent], *, seed: int, replicate: int
) -> list[tuple[Agent, ...]]:
    """The seat assignments of one replicate, one per rotation of the design (FR-11.9)."""
    seats = len(table)
    if design.seating == ROTATED_SEATING:
        # Rotation k moves every agent k seats on: seat i is played by table[(i + k) mod N].
        return [
            tuple(table[(seat + rotation) % seats] for seat in range(seats))
            for rotation in range(seats)
        ]
    if design.seating == "random":
        order = SeededRandomSource(_seating_seed(seed, replicate)).shuffle(
            list(range(seats)), purpose=SEATING_SHUFFLE
        )
        return [tuple(table[index] for index in order)]
    return [tuple(table)]


def _game_seed(base: int, *, replicate: int, rotation: int, draws_per_game: bool) -> int:
    """The seed of one game: mirrored across rotations unless the configuration is drawn per game.

    Replicate 0 keeps the run's own seed, so the first game of a run is the game a single-game run
    with the same seed would have played; every other seed is derived from it.
    """
    replicate_seed = base if replicate == 0 else _seed("replicate", base, replicate)
    if not draws_per_game or rotation == 0:
        return replicate_seed
    return _seed("rotation", replicate_seed, rotation)


def _seating_seed(seed: int, replicate: int) -> int:
    """The seed of one random seating draw, apart from the games' own seeds."""
    return _seed("seating", seed, replicate)


def _seed(*parts: object) -> int:
    text = GAME_SEED_LABEL + ":" + ":".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16)


__all__: list[str] = [
    "GAME_SEED_LABEL",
    "SEATING_SHUFFLE",
    "PlannedGame",
    "plan",
]
