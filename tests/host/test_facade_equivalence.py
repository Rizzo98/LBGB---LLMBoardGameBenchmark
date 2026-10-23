"""K-004: the facade does not change the game.

The facade is a new layer over v1's engine, and the cheapest proof that it changed nothing is
not a new fixture: it is v1's own evidence. This module drives the committed golden corpus
through the facade and checks two claims (PRD-v2 FR-1.4, SC-2):

- one complete corpus game produces a god log byte-for-byte identical to the same actions
  driven through a bare GameRun, and to the record v1 pinned;
- every one of the seven golden games reaches the same final state hash through the facade,
  whether or not the game itself has ended.

Nothing here writes a new fixture. The input is tests/golden/catan, the record v1 already
committed; the only new artefact is a temporary log under pytest's own tmp directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.log import GameLog, GameLogReader, god_log_path
from lgbg.core.replay import verify
from lgbg.core.run import GameRun
from lgbg.core.types import GameId
from lgbg.host.facade import SessionFacade

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
GOLDEN: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan"
GOLDEN_RECORDS: Final[tuple[Path, ...]] = tuple(sorted(GOLDEN.glob("*.god.jsonl")))
GOLDEN_IDS: Final[tuple[str, ...]] = tuple(
    path.name.removesuffix(".god.jsonl") for path in GOLDEN_RECORDS
)
COMPLETE_GAME: Final[Path] = GOLDEN / "full_game.god.jsonl"


def config_of(log: GameLog) -> RunConfig:
    """The configuration the record itself carries, read the way a record reader reads it."""
    return RunConfig.from_mapping(log.header.config, game_option_keys=None)


def play_through_facade(log: GameLog, directory: Path) -> GameId:
    """Drive one record's actions through a fresh facade, then close the session.

    The recorded action sequence and the recorded request ids are the input: the facade is
    asked to make exactly the attempts v1 made, in exactly the order v1 made them.
    """
    facade = SessionFacade()
    game_id = facade.create_session(
        log.header.game, config_of(log), game_id=log.header.game_id, directory=directory
    )
    for record in log.actions:
        result = facade.submit_action(game_id, record.action, request_id=record.request_id)
        assert isinstance(result, Applied) == (record.result.get("ok") is True), (
            f"seq {record.seq}: the facade answered differently from the record"
        )
    # A finished session needs no terminal line and an unfinished one must not invent one;
    # end_session is the facade's declared way to leave it in either case.
    facade.end_session(game_id)
    return game_id


def produced_log(directory: Path, game_id: GameId) -> GameLog:
    return GameLogReader(god_log_path(directory, game_id)).read()


def test_the_corpus_is_the_seven_v1_golden_games() -> None:
    """The card names seven; a shrinking corpus must fail rather than quietly test less."""
    assert GOLDEN_IDS == (
        "devcard_game",
        "full_game",
        "random_game",
        "setup_game",
        "seven_game",
        "three_player_game",
        "trade_game",
    )


def test_a_complete_corpus_game_is_byte_identical_through_the_facade(tmp_path: Path) -> None:
    """The same actions through GameRun and through the facade produce the same bytes.

    'full_game' is the corpus's complete 743-action game: it ends in a winner, so both paths
    write a terminal record and the comparison is the whole file rather than a prefix.
    """
    log = GameLogReader(COMPLETE_GAME).read()
    game = get_game(log.header.game)
    run = GameRun(
        game, config_of(log), game_id=log.header.game_id, directory=tmp_path / "v1-engine"
    )
    for record in log.actions:
        assert isinstance(run.submit(record.action, request_id=record.request_id), Applied)
    run.finish()

    facade_id = play_through_facade(log, tmp_path / "facade")

    engine_bytes = god_log_path(tmp_path / "v1-engine", log.header.game_id).read_bytes()
    facade_bytes = god_log_path(tmp_path / "facade", facade_id).read_bytes()

    assert facade_bytes == engine_bytes
    assert facade_bytes == COMPLETE_GAME.read_bytes()


@pytest.mark.parametrize("path", GOLDEN_RECORDS, ids=GOLDEN_IDS)
def test_every_golden_game_reaches_the_recorded_final_hash_through_the_facade(
    path: Path, tmp_path: Path
) -> None:
    """All seven records replay through the new path to the hash v1's own verifier reports.

    Two of the seven stop before the game is over, so the facade deliberately leaves their
    record without a terminal line. The final hash is still the state after the last action,
    which is exactly what verify reports for a log with no terminal record.
    """
    log = GameLogReader(path).read()
    game = get_game(log.header.game)
    expected = verify(log, game)

    game_id = play_through_facade(log, tmp_path)
    actual = verify(produced_log(tmp_path, game_id), game)

    assert actual.actions == expected.actions
    assert actual.rejections == expected.rejections
    assert actual.terminal_hash == expected.terminal_hash
