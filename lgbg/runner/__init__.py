"""The runner: what a run *is*, rather than how a game is played (PRD-v2 D4).

The layers below this one know how to run one game and how to talk to one model. The runner is the
first layer that knows what an *experiment* is: which agent sits in which seat, what design the game
occupies a point in, and what the run declared before it began.

The cut through this package is deliberate:

- `agents` declares the three ways a seat is played and nothing about choosing one;
- `design` carries the point in the experiment, without building the matrix that produces it;
- `manifest` records the run's declaration, and knows no game;
- `game` drives one game through the facade and reports completed or abandoned.

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
    CONFIGURATION_SCOPES,
    DERIVATION_RULE,
    SEATING,
    DesignError,
    GameDesign,
    declared_seating,
)
from lgbg.runner.game import (
    Abandonment,
    GameAbortedError,
    GameError,
    GameResult,
    run_game,
)
from lgbg.runner.manifest import DEFAULT_GAME_TIMEOUT_S, ManifestError, build_manifest

__all__: list[str] = [
    "AXES",
    "CONFIGURATION_SCOPES",
    "DEFAULT_GAME_TIMEOUT_S",
    "DERIVATION_RULE",
    "SEATING",
    "Abandonment",
    "Agent",
    "AgentKind",
    "DesignError",
    "GameAbortedError",
    "GameDesign",
    "GameError",
    "GameResult",
    "LlmAgent",
    "ManifestError",
    "ReferenceAgent",
    "ReferencePlayer",
    "ReferenceView",
    "ScriptedAgent",
    "build_manifest",
    "declared_seating",
    "run_game",
]
