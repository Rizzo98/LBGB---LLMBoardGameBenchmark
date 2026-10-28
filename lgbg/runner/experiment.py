"""Playing a planned experiment: the matrix, then one game at a time (PRD-v2 FR-11.3, SC-7).

This is the smallest complete experiment the runner can run. It plans every game first, then plays
them in order, each in its own run directory with its own `run.json`, its own seat assignment and
its own seed. Planning first is not an optimisation: the set of games is part of what the run
declares, and a run whose games are decided as it goes cannot say what it measured.

The experiment's own record - the plan, the derivation and the games - is returned, and
`results.json` is written at the run root: the axes the design did not control, every game with
its per-seat split, and the per-model totals. The caveat travels with the data rather than living
only in this object, and the totals are facts about games that happened rather than a claim about
models (FR-10.6, FR-11.8, FR-11.12).

Unattended running with bounded concurrency across games and resuming are FR-11.5's, and not here:
one game at a time, each in its own resolution order, is the record the rest builds on.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from lgbg.agents.context import ContextPolicy
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import RunConfig
from lgbg.core.contracts import validate_results
from lgbg.core.game import get_game
from lgbg.core.types import JsonValue
from lgbg.runner.agents import Agent
from lgbg.runner.design import DesignError, ExperimentDesign
from lgbg.runner.game import GameResult, run_game
from lgbg.runner.matrix import PlannedGame, plan
from lgbg.runner.results import RESULTS_FILENAME, ResultsError, experiment_results

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

    @property
    def results_path(self) -> Path:
        """The run's results file: the design caveat, every game, and the per-model totals."""
        return self.root / RESULTS_FILENAME


async def run_experiment(
    *,
    game: str,
    config: RunConfig,
    root: Path,
    run_id: str,
    seats: Sequence[Agent],
    prompts: PromptSet,
    price_table: PriceTable,
    design: ExperimentDesign | None = None,
    policy: TurnPolicy | None = None,
    context: ContextPolicy | None = None,
    clock: Callable[[], str] | None = None,
) -> ExperimentResult:
    """Plan the design, then play every game it declares under one root directory.

    A caller that declares no design gets the single-game exploration case (FR-11.13): one game,
    random seats, and the starting configuration the plugin says it can draw.
    """
    plugin = get_game(game)
    if len(seats) != config.players:
        raise DesignError(
            f"the table names {len(seats)} agents but the configuration has {config.players} seats"
        )
    profile = plugin.benchmark_profile()
    chosen = ExperimentDesign.exploration(profile) if design is None else design
    planned = plan(design=chosen, table=seats, seed=config.seed, profile=profile)
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
    result = ExperimentResult(
        run_id=run_id,
        root=root,
        design=chosen,
        derivation=chosen.derivation(len(seats)),
        planned=planned,
        games=tuple(games),
    )
    record = experiment_results(
        run_id=run_id,
        design=chosen,
        profile=profile,
        seats=len(seats),
        derivation=result.derivation,
        games=result.games,
    )
    problems = validate_results(record)
    if problems:
        raise ResultsError("; ".join(problems))
    result.results_path.write_text(to_canonical_json(record) + "\n", encoding="utf-8")
    return result


__all__: list[str] = [
    "GAME_DIRECTORY_PREFIX",
    "ExperimentResult",
    "run_experiment",
]
