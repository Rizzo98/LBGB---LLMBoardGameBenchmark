"""Two more golden games: a random board and three players (SC-1; kanban card K-068).

The first five fixtures all play the same curated board with four seats, so nothing in the corpus
exercised the other half of the board code (the random terrain and token draw, and the harbour
shuffle beside it) or a table that is not the standard four. SC-1 asks for complete games that
replay for distinct (seed, board) combinations and the card asks for at least seven games; these
are the sixth and the seventh, and they are pinned the same way as the others - a scripted action
file, a god log, and a test that replays one against the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from lgbg.adapters.cli.script import drive, load_script
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from lgbg.core.run import GameRun
from lgbg.games.catan.state import Phase

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CASES: Final[tuple[tuple[str, str, int, int, str], ...]] = (
    ("random_game", "random", 4, 790, "g-0006"),
    ("three_player_game", "fixed:standard_a", 3, 205, "g-0007"),
)
"""Name, board and seats, and the number of actions the record was produced with."""


@pytest.mark.parametrize(("name", "board", "seats", "actions", "game_id"), CASES)
def test_the_record_replays_with_every_hash_verified(
    name: str, board: str, seats: int, actions: int, game_id: str
) -> None:
    record = ROOT / "tests" / "golden" / "catan" / f"{name}.god.jsonl"
    log = GameLogReader(record).read()
    game = get_game(log.header.game)

    report = verify(log, game)

    assert report.actions == actions
    assert report.rejections == 0
    assert log.header.config["board"] == board
    assert log.header.config["players"] == seats
    assert replay(log, game).states[-1].phase is Phase.TERMINAL


@pytest.mark.parametrize(("name", "board", "seats", "actions", "game_id"), CASES)
def test_playing_the_script_reproduces_the_record_byte_for_byte(
    name: str, board: str, seats: int, actions: int, game_id: str, tmp_path: Path
) -> None:
    record = ROOT / "tests" / "golden" / "catan" / f"{name}.god.jsonl"
    fixture = ROOT / "tests" / "fixtures" / "catan" / f"{name}.json"
    script = load_script(fixture)
    run = GameRun(get_game("catan"), script.config, game_id=game_id, directory=tmp_path)

    drive(run, script)
    run.finish()

    produced = god_log_path(tmp_path, game_id).read_bytes()
    assert produced == record.read_bytes()
    assert b"\r" not in produced
