"""The runner: what a run *is*, rather than how a game is played (PRD-v2 D4).

The layers below this one know how to run one game and how to talk to one model. The runner is the
first layer that knows what an *experiment* is: which agent sits in which seat, what design the game
occupies a point in, and what the run declared before it began.

The cut through this package is deliberate:

- `agents` declares the three ways a seat is played and nothing about choosing one;
- `design` holds the design a run asks for and the point one game records;
- `matrix` turns the first into the second: the games, their seat assignments and their seeds;
- `manifest` records the run's declaration, and knows no game;
- `game` drives one game through the facade and reports completed or abandoned;
- `experiment` plans a matrix and plays every game it declares.

Everything here is game-agnostic. A game reaches the runner as a registered name and a set of
declarations, never as an import (FR-11.7).
"""

from __future__ import annotations

from lgbg.runner.agents import (
    Agent,
    AgentKind,
    LlmAgent,
    ReferenceAgent,
    ReferencePlayer,
    ReferenceView,
    ScriptedAgent,
)
from lgbg.runner.design import (
    AXES,
    AXIS_INITIAL_CONFIGURATION,
    AXIS_SEATING,
    CONFIGURATION_SCOPES,
    DERIVATION_RULE,
    RANDOM_CONFIGURATION,
    ROTATED_SEATING,
    SEATING,
    DesignError,
    ExperimentDesign,
    GameDesign,
    declared_seating,
)
from lgbg.runner.experiment import ExperimentResult, run_experiment
from lgbg.runner.game import (
    Abandonment,
    GameAbortedError,
    GameError,
    GameResult,
    run_game,
)
from lgbg.runner.manifest import DEFAULT_GAME_TIMEOUT_S, ManifestError, build_manifest
from lgbg.runner.matrix import PlannedGame, plan
from lgbg.runner.results import (
    RESULTS_FILENAME,
    RESULTS_SCHEMA_NAME,
    GameFacts,
    ModelTally,
    OutcomeSummary,
    ResultsError,
    SeatFacts,
    experiment_record,
    experiment_results,
)

__all__: list[str] = [
    "AXES",
    "AXIS_INITIAL_CONFIGURATION",
    "AXIS_SEATING",
    "CONFIGURATION_SCOPES",
    "DEFAULT_GAME_TIMEOUT_S",
    "DERIVATION_RULE",
    "RANDOM_CONFIGURATION",
    "RESULTS_FILENAME",
    "RESULTS_SCHEMA_NAME",
    "ROTATED_SEATING",
    "SEATING",
    "Abandonment",
    "Agent",
    "AgentKind",
    "DesignError",
    "ExperimentDesign",
    "ExperimentResult",
    "GameAbortedError",
    "GameDesign",
    "GameError",
    "GameFacts",
    "GameResult",
    "LlmAgent",
    "ManifestError",
    "ModelTally",
    "OutcomeSummary",
    "PlannedGame",
    "ReferenceAgent",
    "ReferencePlayer",
    "ReferenceView",
    "ResultsError",
    "ScriptedAgent",
    "SeatFacts",
    "build_manifest",
    "declared_seating",
    "experiment_record",
    "experiment_results",
    "plan",
    "run_experiment",
    "run_game",
]
