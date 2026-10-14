"""Determinism across processes (PRD-v1 SC-3, ARCHITECTURE.md section 6).

The determinism contract is easy to satisfy inside one process and easy to break across two.
Python salts string hashing per process, so any use of 'hash()', of a set used as an ordered
collection, or of a dict built from unordered input produces a record that is stable on one
machine and different on the next. None of that shows up in a single-process test.

So the same game is played twice, in two child processes with different PYTHONHASHSEED
values, and the two records are compared byte for byte.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

PROGRAM: Final[str] = """
import sys
from lgbg.core.config import RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.run import GameRun
from lgbg.core.types import Action
import tests.games.fixture_game  # registers the fixture game

out = sys.argv[1]
game = get_game("fixture")
config = RunConfig(seed=20250101, players=2, interaction_protocol="decline_only")
run = GameRun(game, config, game_id="g-0001", directory=__import__("pathlib").Path(out))
for _ in range(60):
    if game.is_terminal(run.state):
        break
    player = run.pending[0].player
    type_ = "spend" if run.state.tokens[player] >= 4 else "gamble"
    result = run.submit(Action(player=player, type=type_, params={}))
    assert isinstance(result, Applied), result
run.submit(Action(player=0, type="nonsense", params={}))
run.finish()
print(sys.flags.hash_randomization, __import__("os").environ.get("PYTHONHASHSEED"))
"""


def _play_in_a_child_process(directory: Path, hash_seed: str) -> tuple[bytes, str]:
    """Play the same game in a fresh interpreter with the given hash seed."""
    environment = {**os.environ, "PYTHONHASHSEED": hash_seed}
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, test-only
        [sys.executable, "-c", PROGRAM, str(directory)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    record = (directory / "games" / "g-0001.god.jsonl").read_bytes()
    return record, result.stdout.strip()


def test_identical_inputs_produce_identical_records_across_processes(tmp_path: Path) -> None:
    first, first_seed = _play_in_a_child_process(tmp_path / "first", "0")
    second, second_seed = _play_in_a_child_process(tmp_path / "second", "987654321")

    assert first_seed != second_seed, "the two processes must not share a hash seed"
    assert first, "the record must not be empty"
    assert first == second


def test_the_record_carries_no_ambient_value(tmp_path: Path) -> None:
    """A record that differed on every run would be reproducible by accident, not by design."""
    first, _ = _play_in_a_child_process(tmp_path / "first", "0")
    second, _ = _play_in_a_child_process(tmp_path / "second", "0")

    assert first == second
    text = first.decode("utf-8")
    for forbidden in ('"at":', '"host":', '"pid":'):
        assert forbidden not in text
