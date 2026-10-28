"""Outcome aggregates over played games (PRD-v2 FR-7.5, FR-11.8).

This is the arithmetic the runner and results.json use. The experiment block is written at the run
root by `run_experiment`, caveats included; K-032 extends the same artefact with per-game and
per-seat detail. The one rule here is that an abandoned game is not an outcome. It is counted in
its own column, per model, and it never enters a win or a loss. Folding it in would reward a model
that plays badly but legally over one that fails decisively, which is the opposite of what the
benchmark is for (PRD-v2 section 10.2).

v2 reports facts, not inferences: these are counts over games that happened, not a rating.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from lgbg.core.game import BenchmarkProfile
from lgbg.core.types import JsonValue
from lgbg.runner.design import ExperimentDesign
from lgbg.runner.game import GameResult

RESULTS_SCHEMA_NAME: Final[str] = "lgbg.results.v1"
"""The schema of the run's results file, declared here so a reader and a writer agree."""

RESULTS_FILENAME: Final[str] = "results.json"
"""What the experiment writes at its root: the design axes and the caveats they carry."""


@dataclass(frozen=True, slots=True)
class ModelTally:
    """One model's games: finished outcomes and abandonments, kept apart on purpose."""

    model: str
    completed: int = 0
    wins: int = 0
    losses: int = 0
    abandoned: int = 0

    @property
    def games(self) -> int:
        return self.completed + self.abandoned

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "model": self.model,
            "games": self.games,
            "completed": self.completed,
            "wins": self.wins,
            "losses": self.losses,
            "abandoned": self.abandoned,
        }


@dataclass(frozen=True, slots=True)
class OutcomeSummary:
    """The run's outcomes: completed games only, with abandonments in their own row."""

    completed: int
    abandoned: int
    per_model: tuple[ModelTally, ...]

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "completed": self.completed,
            "abandoned": self.abandoned,
            "per_model": [row.to_mapping() for row in self.per_model],
        }


def summarise(results: Sequence[GameResult]) -> OutcomeSummary:
    """Count finished games and abandonments, per model, without mixing them.

    A completed game counts once for every model that held a seat in it, and a win is the model
    whose seat the game's winner names. An abandoned game counts once, for the model responsible,
    and not as a loss for anyone (FR-7.5, FR-11.8).
    """
    completed = 0
    abandoned = 0
    rows: dict[str, dict[str, int]] = {}

    def row(model: str) -> dict[str, int]:
        return rows.setdefault(model, {"completed": 0, "wins": 0, "losses": 0, "abandoned": 0})

    for result in results:
        if result.completed:
            completed += 1
            for seat, model in result.model_seats.items():
                counts = row(model)
                counts["completed"] += 1
                if result.winner == seat:
                    counts["wins"] += 1
                else:
                    counts["losses"] += 1
            continue
        abandoned += 1
        if result.abandonment is not None:
            row(result.abandonment.model)["abandoned"] += 1

    per_model = tuple(ModelTally(model=model, **counts) for model, counts in sorted(rows.items()))
    return OutcomeSummary(completed=completed, abandoned=abandoned, per_model=per_model)


def experiment_record(
    *,
    run_id: str,
    design: ExperimentDesign,
    profile: BenchmarkProfile,
    seats: int,
    derivation: Mapping[str, JsonValue],
    planned: int,
    completed: int,
    abandoned: int,
) -> dict[str, JsonValue]:
    """The experiment block of `results.json`, with every uncontrolled axis named (FR-11.12).

    The caveat is computed from the same declaration the matrix used, so it cannot drift from the
    games the run actually played: the axes are re-derived here from the plugin's profile rather
    than copied from whatever the caller remembered to pass.
    """
    return {
        "schema": RESULTS_SCHEMA_NAME,
        "run_id": run_id,
        "design": {
            "seating": design.seating,
            "initial_configuration": design.initial_configuration,
            "configuration_scope": design.configuration_scope,
            "replicates": design.replicates,
            "uncontrolled": list(design.uncontrolled(profile, seats)),
            "derivation": dict(derivation),
        },
        "games": {
            "planned": planned,
            "completed": completed,
            "abandoned": abandoned,
        },
    }


__all__: Final[list[str]] = [
    "RESULTS_FILENAME",
    "RESULTS_SCHEMA_NAME",
    "ModelTally",
    "OutcomeSummary",
    "experiment_record",
    "summarise",
]
