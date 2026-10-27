"""Outcome aggregates over played games (PRD-v2 FR-7.5, FR-11.8).

This is the arithmetic the runner and results.json will use (K-032 writes the artefact). It has
one rule: an abandoned game is not an outcome. It is counted in its own column, per
model, and it never enters a win or a loss. Folding it in would reward a model that plays badly
but legally over one that fails decisively, which is the opposite of what the benchmark is for
(PRD-v2 section 10.2).

v2 reports facts, not inferences: these are counts over games that happened, not a rating.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from lgbg.core.types import JsonValue
from lgbg.runner.game import GameResult


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


__all__: Final[list[str]] = [
    "ModelTally",
    "OutcomeSummary",
    "summarise",
]
