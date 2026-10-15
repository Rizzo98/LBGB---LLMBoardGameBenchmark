"""Measure the engine against NFR-2 (kanban card K-039; PRD-v1 NFR-2, risk R8).

NFR-2 asks for three things: a four-player game in under 50 ms with the fuzz driver, ten
thousand games in under thirty minutes single-threaded, and a replay that costs no more than
twice the original play. This script measures all three on the machine it is run on, and reports
where the time goes, because the finding that matters while it is still cheap to change is
whether canonical JSON plus SHA-256 is the bottleneck.

It is a measuring instrument, not a test: the numbers depend on the machine, so the test file
next to it asserts only what would be a *bug* rather than a slow afternoon (an accidental
quadratic, a replay that costs an order of magnitude more than the play).

    uv run python scripts/benchmark_simulation.py [games]
"""

from __future__ import annotations

import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.canonical import hash_state
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from lgbg.core.run import GameRun
from lgbg.core.types import Action

DEFAULT_GAMES: Final[int] = 20
PLAYERS: Final[int] = 4
BOARD: Final[str] = "fixed:standard_a"
MAX_ACTIONS: Final[int] = 20000


def play_once(
    seed: int, *, directory: Path | None = None, game_id: str = "bench"
) -> tuple[int, float]:
    """One game, played by a fuzz driver: a random legal action, from a seeded choice.

    The driver is deliberately the cheapest possible one - pick a legal action at random - so
    that what is being measured is the engine rather than a clever policy. Its randomness comes
    from a local Random, not from the engine: the engine's own draws are already part of the game.
    """
    game = get_game("catan")
    config = RunConfig(
        seed=seed,
        players=PLAYERS,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": BOARD}),
    )
    chooser = random.Random(seed)
    started = time.perf_counter()
    run = GameRun(game, config, game_id=game_id, directory=directory)
    actions = 0
    for _ in range(MAX_ACTIONS):
        if game.is_terminal(run.state):
            break
        action = _choose(game, run, chooser)
        result = run.submit(action)
        if not isinstance(result, Applied):
            raise SystemExit(f"a legal action was refused: {result.rejection.message}")
        actions += 1
    else:
        raise SystemExit(f"no terminal state within {MAX_ACTIONS} actions")
    run.finish()
    return actions, time.perf_counter() - started


def _choose(game: Any, run: GameRun, chooser: random.Random) -> Action:
    """A random legal action, which is what the fuzz driver of NFR-2 asks for."""
    offered: list[Action] = []
    for request in run.pending:
        offered.extend(game.legal_actions(run.state, request.player))
    if not offered:
        raise SystemExit(f"no legal action in phase {run.state.phase.value}")
    return chooser.choice(offered)


def main(argv: list[str]) -> int:
    games = int(argv[0]) if argv else DEFAULT_GAMES
    with tempfile.TemporaryDirectory() as scratch:
        directory = Path(scratch)
        durations: list[float] = []
        action_counts: list[int] = []
        for index in range(games):
            actions, seconds = play_once(
                20_250_000 + index, directory=directory, game_id=f"bench-{index}"
            )
            durations.append(seconds)
            action_counts.append(actions)
        play_total = sum(durations)

        # A replay of one of those games, and how it compares with playing it once more.
        path = god_log_path(directory, "bench-0")
        log = GameLogReader(path).read()
        before = time.perf_counter()
        verify(log, get_game(log.header.game))
        replay_seconds = time.perf_counter() - before

        hashes, hashing = _time_hashing(directory)
        hash_game = _hash_a_game(directory, len(log.actions))

    per_game = statistics.median(durations)
    print(f"games                 {games}")
    print(
        f"actions per game      median {int(statistics.median(action_counts))}, "
        f"max {max(action_counts)}"
    )
    print(f"play per game         median {per_game * 1000:.2f} ms")
    print(f"play total            {play_total:.2f} s for {games} games")
    print(
        f"replay one game       {replay_seconds * 1000:.2f} ms "
        f"({replay_seconds / per_game:.2f}x the play)"
    )
    print(
        f"hash path             {hashes} hash_state calls in {hashing * 1000:.2f} ms; "
        f"one game's worth {_REPEATS} times over costs {hash_game * 1000:.2f} ms, "
        f"{hash_game / per_game * 100:.0f}% of playing it"
    )
    print(
        f"NFR-2 budget          50 ms per game, 2x for replay; "
        f"{per_game * 1000:.2f} ms and {replay_seconds / per_game:.2f}x measured"
    )
    return 0


_REPEATS: Final[int] = 5


def _time_hashing(directory: Path) -> tuple[int, float]:
    """How much of a game's cost is the hash path, which NFR-2's risk R8 names."""
    game = get_game("catan")
    log = GameLogReader(god_log_path(directory, "bench-0")).read()
    states = replay(log, game).states
    started = time.perf_counter()
    for _ in range(_REPEATS):
        for state in states:
            hash_state(state, game)
    return len(states) * _REPEATS, time.perf_counter() - started


def _hash_a_game(directory: Path, actions: int) -> float:
    """One game's worth of hashing: both hashes of every action's state, twice per action is
    what the runtime does, so this is the share of a game that the hash path could account for.
    """
    game = get_game("catan")
    log = GameLogReader(god_log_path(directory, "bench-0")).read()
    states = replay(log, game).states
    per_state = _per_hash(states[0], game)
    return per_state * actions * 2


def _per_hash(state: Any, game: Any) -> float:
    started = time.perf_counter()
    for _ in range(20):
        hash_state(state, game)
    return (time.perf_counter() - started) / 20


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
