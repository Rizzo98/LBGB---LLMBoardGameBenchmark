"""Every code the engine raises in play is one the plugin declared (FR-6.8, SC-13; card K-063).

The declaration is what makes rejection-code distribution a game-agnostic metric: the metrics
layer can enumerate the codes without knowing the game, which it can only do if the set of them is
closed. A source audit already walks the engine and fails on a code that is raised but not
declared; this file is the other half - a driver that plays badly on purpose, and an assertion
that every code the resulting record carries was declared before it was ever seen.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.run import GameRun
from lgbg.core.types import Action

GAME: Final[Any] = get_game("catan")
SEED: Final[int] = 20261001
MAX_ACTIONS: Final[int] = 400


def _wrong(seat: int, offered: list[Action], chooser: random.Random) -> Action:
    """Three kinds of nonsense, each of which the engine has a code for."""
    kind = chooser.choice(("seat", "type", "params"))
    if kind == "seat":
        return Action(player=(seat + 1) % 4, type=offered[0].type, params=dict(offered[0].params))
    if kind == "type":
        return Action(player=seat, type="teleport", params={})
    return Action(player=seat, type=chooser.choice(offered).type, params={})


def _badly(directory: Path) -> list[str]:
    """Play, and answer every third decision with something nobody offered."""
    chooser = random.Random(SEED)
    config = RunConfig(
        seed=SEED,
        players=4,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": "fixed:standard_a"}),
    )
    run = GameRun(GAME, config, game_id="g-refusals", directory=directory)
    for step in range(MAX_ACTIONS):
        if GAME.is_terminal(run.state):
            break
        request = run.pending[0]
        offered = GAME.legal_actions(run.state, request.player)
        if step % 3 == 0:
            run.submit(_wrong(request.player, offered, chooser))
            continue
        run.submit(chooser.choice(offered))
    run.finish()
    log = GameLogReader(god_log_path(directory, "g-refusals")).read()
    return [
        str(record.result["error"]) for record in log.actions if record.result.get("ok") is not True
    ]


def test_every_code_a_fuzz_run_raises_is_declared(tmp_path: Path) -> None:
    """FR-6.8: the declaration covers what play produces, not only what the source says."""
    declared = {code.code for code in GAME.rejection_codes()}
    seen = sorted(set(_badly(tmp_path)))

    assert len(seen) >= 3, f"the driver barely misbehaved: {seen}"
    for code in seen:
        assert code in declared, f"{code} was raised and is not declared"


def test_the_run_produced_refusals_at_all(tmp_path: Path) -> None:
    """The control: a run that never misbehaved would pass the test above for free."""
    codes = _badly(tmp_path)

    assert len(codes) > 20, "a third of four hundred decisions should have gone wrong"
