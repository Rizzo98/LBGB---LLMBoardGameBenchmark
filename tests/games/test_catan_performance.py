"""Performance against NFR-2 (kanban card K-039; PRD-v1 NFR-2, risk R8).

NFR-2 asks for a four-player game in under 50 ms with the fuzz driver, ten thousand games in
under thirty minutes single-threaded, and a replay costing no more than twice the play. The
measurements live in scripts/benchmark_simulation.py, because a number in an assertion is a
number that depends on the machine it runs on.

What the tests here assert is the part that does not depend on the machine: that the engine is
not *asymptotically* wrong, and that replay does not cost an order of magnitude more than play.
A bound with an order of magnitude of headroom catches the regression that matters - an
accidental quadratic, a hash that walks the whole state twice as often as it should - without
failing on a busy afternoon.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.canonical import hash_state
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from lgbg.core.rng import NullRandomSource
from lgbg.core.run import GameRun
from lgbg.core.types import Action

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251208
MAX_ACTIONS: Final[int] = 4000
PER_ACTION_BUDGET: Final[float] = 0.020
"""Twenty milliseconds an action, where the measurement is under one."""
REPLAY_BUDGET: Final[float] = 4.0
"""NFR-2 allows twice the play; the measurement is a quarter of it."""
HASH_BUDGET: Final[float] = 0.005


def _play(tmp_path: Path, seed: int = SEED) -> tuple[Any, int, float]:
    """One fuzz game: a random legal action each step, which is what NFR-2 measures."""
    import random

    game = get_game("catan")
    config = RunConfig(
        seed=seed,
        players=PLAYERS,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": "fixed:standard_a"}),
    )
    chooser = random.Random(seed)
    run = GameRun(game, config, game_id="perf", directory=tmp_path)
    started = time.perf_counter()
    actions = 0
    for _ in range(MAX_ACTIONS):
        if game.is_terminal(run.state):
            break
        offered = [
            action
            for request in run.pending
            for action in game.legal_actions(run.state, request.player)
        ]
        assert offered, "a live game always offers something"
        result = run.submit(chooser.choice(offered))
        assert isinstance(result, Applied)
        actions += 1
    run.finish()
    return run, actions, time.perf_counter() - started


def test_a_whole_game_costs_what_an_action_should(tmp_path: Path) -> None:
    """The budget is per action, so the bound does not depend on how long the game ran."""
    _run, actions, seconds = _play(tmp_path)

    assert actions > 100, "the fixture must play a game, not a handful of moves"
    assert seconds / actions < PER_ACTION_BUDGET, (
        f"{seconds / actions * 1000:.2f} ms per action over {actions} actions"
    )


def test_replaying_a_game_costs_no_more_than_playing_it(tmp_path: Path) -> None:
    """NFR-2: replay is a verification path, and it may not be the expensive one."""
    _run, _actions, play = _play(tmp_path)
    log = GameLogReader(god_log_path(tmp_path, "perf")).read()
    game = get_game(log.header.game)

    started = time.perf_counter()
    report = verify(log, game)
    replay_seconds = time.perf_counter() - started

    assert report.rejections == 0
    assert replay_seconds < play * REPLAY_BUDGET, (
        f"replay took {replay_seconds:.3f} s against {play:.3f} s of play"
    )


def test_hashing_a_state_is_not_the_expensive_part(tmp_path: Path) -> None:
    """Risk R8: canonical JSON plus SHA-256, measured rather than assumed.

    The benchmark on the machine this was written on puts the whole hash path at about a tenth
    of a game, and the JSON traversal inside it at most of that: the hashing is not free, and it
    is not the bottleneck. This test keeps the per-call cost honest; the share of a game it
    accounts for is what the benchmark script reports.
    """
    run, _actions, _seconds = _play(tmp_path)
    states = replay(GameLogReader(god_log_path(tmp_path, "perf")).read(), GAME).states

    started = time.perf_counter()
    for state in states[:200]:
        hash_state(state, GAME)
    per_call = (time.perf_counter() - started) / min(len(states), 200)

    assert per_call < HASH_BUDGET, f"{per_call * 1000:.3f} ms per hash_state call"
    assert run.state is not None


def test_the_hash_chain_is_what_replay_checks(tmp_path: Path) -> None:
    """A replay that verified nothing would be fast for the wrong reason."""
    _run, actions, _seconds = _play(tmp_path)
    log = GameLogReader(god_log_path(tmp_path, "perf")).read()

    report = verify(log, GAME)

    assert report.actions == actions
    assert report.terminal_hash == log.terminal.state_hash if log.terminal else True
    assert all(record.state_hash_prev for record in log.actions[1:])


def test_a_rejected_action_is_cheap(tmp_path: Path) -> None:
    """The illegal-move rate is a metric, so a refusal may not cost what an action costs."""
    _run, _actions, _seconds = _play(tmp_path)
    state = _terminal_or_live(tmp_path)

    started = time.perf_counter()
    for _ in range(20):
        refused = GAME.apply(
            state,
            Action(player=0, type="not_an_action", params={}),
            NullRandomSource(),
        )
        assert refused is not None
    per_call = (time.perf_counter() - started) / 20

    assert per_call < PER_ACTION_BUDGET


def _terminal_or_live(tmp_path: Path) -> Any:
    log = GameLogReader(god_log_path(tmp_path, "perf")).read()
    return replay(log, GAME).states[-1]
