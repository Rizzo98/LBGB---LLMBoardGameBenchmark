"""Playing a planned experiment: the matrix, then one game at a time (PRD-v2 FR-11.3, SC-7).

This is the smallest complete experiment the runner can run. It plans every game first, then plays
them in order, each in its own run directory with its own `run.json`, its own seat assignment and
its own seed. Planning first is not an optimisation: the set of games is part of what the run
declares, and a run whose games are decided as it goes cannot say what it measured.

The experiment's own record - the plan, the derivation and the games - is returned rather than
written. `results.json` is K-032's artefact; this slice's job is that every game already carries its
point in the design, which is what makes that artefact possible.

Unattended running, bounded concurrency and resuming are FR-11.5's, and deliberately not here: one
game at a time, in the game's own resolution order, is the record that the rest builds on.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from lgbg.agents.context import ContextPolicy
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.core.config import RunConfig
from lgbg.core.game import get_game
from lgbg.core.types import JsonValue
from lgbg.runner.agents import Agent
from lgbg.runner.design import DesignError, ExperimentDesign
from lgbg.runner.game import GameResult, run_game
from lgbg.runner.matrix import PlannedGame, plan

GAME_DIRECTORY_PREFIX: str = "g-"
"""How one game's directory is named: the game id, so the directory and the record agree."""


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """What one experiment produced: its declared design, its plan, and every game's record."""

    run_id: str
    root: Path
    design: ExperimentDesign
    derivation: Mapping[str, JsonValue]
    planned: tuple[PlannedGame, ...]
    games: tuple[GameResult, ...]

    @property
    def completed(self) -> int:
        return sum(1 for game in self.games if game.completed)

    @property
    def abandoned(self) -> int:
        return sum(1 for game in self.games if not game.completed)


async def run_experiment(
    *,
    game: str,
    config: RunConfig,
    root: Path,
    run_id: str,
    seats: Sequence[Agent],
    prompts: PromptSet,
    price_table: PriceTable,
    design: ExperimentDesign,
    policy: TurnPolicy | None = None,
    context: ContextPolicy | None = None,
    clock: Callable[[], str] | None = None,
) -> ExperimentResult:
    """Plan the design, then play every game it declares under one root directory."""
    plugin = get_game(game)
    if len(seats) != config.players:
        raise DesignError(
            f"the table names {len(seats)} agents but the configuration has {config.players} seats"
        )
    planned = plan(design=design, table=seats, seed=config.seed, profile=plugin.benchmark_profile())
    games: list[GameResult] = []
    for planned_game in planned:
        game_id = f"{GAME_DIRECTORY_PREFIX}{planned_game.index:04d}"
        games.append(
            await run_game(
                game=game,
                config=replace(config, seed=planned_game.seed),
                directory=root / game_id,
                run_id=f"{run_id}-{game_id}",
                requested_id=game_id,
                seats=planned_game.seat_map(),
                prompts=prompts,
                price_table=price_table,
                design=planned_game.design,
                policy=policy,
                context=context,
                clock=clock,
            )
        )
    return ExperimentResult(
        run_id=run_id,
        root=root,
        design=design,
        derivation=design.derivation(len(seats)),
        planned=planned,
        games=tuple(games),
    )


__all__: list[str] = [
    "GAME_DIRECTORY_PREFIX",
    "ExperimentResult",
    "run_experiment",
]
