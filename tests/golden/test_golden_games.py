"""Golden game 1: the opening draft, pinned byte for byte (PRD-v1 SC-1, ARCHITECTURE.md 15.3).

A golden game is a regression net made of bytes. Every rule of slice 2 - the snake order, the
distance rule, the road attachment, the endowment, the phase machine, the encoding, the hashes -
is exercised by this fixture, and a change to any of them changes the file. That is the point:
a hash change cannot pass unnoticed, and it forces a deliberate decision to bump the plugin's
rules_version and regenerate (RULES.md section 1.2).

The fixture is committed in two halves, both of them deterministic. The scripted action file is
the input; the god log is what the engine produced. The test plays the first and compares it to
the second, which is what makes the pair a regression net rather than a transcript nobody
checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from lgbg.adapters.cli.script import drive, load_script
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader
from lgbg.core.replay import replay, verify
from lgbg.core.run import GameRun
from lgbg.games.catan.notation import render
from lgbg.games.catan.state import Phase

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SCRIPT: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "catan" / "setup_game.json"
RECORD: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan" / "setup_game.god.jsonl"

INITIAL_STATE_HASH: Final[str] = "ef8474ab042614f9"
FINAL_STATE_HASH: Final[str] = "90d1be41a7d264c0"
ACTIONS: Final[int] = 16
SEATS: Final[int] = 4


def _log() -> Any:
    return GameLogReader(RECORD).read()


def test_the_committed_record_replays_with_every_hash_verified() -> None:
    """SC-1: every intermediate state reconstructed, every hash asserted."""
    log = _log()
    game = get_game(log.header.game)

    report = verify(log, game)
    replayed = replay(log, game)

    assert report.actions == ACTIONS
    assert report.rejections == 0
    assert len(replayed.states) == ACTIONS + 1
    assert log.header.initial_state_hash == INITIAL_STATE_HASH
    assert report.terminal_hash == FINAL_STATE_HASH
    assert replayed.states[-1].phase is Phase.TURN_START


def test_playing_the_committed_script_reproduces_the_record_byte_for_byte(
    tmp_path: Path,
) -> None:
    """The regression net: a rule change moves a hash, and this fails.

    If it fails, read the diff before regenerating anything: either the fixture is stale or a
    rule changed, and only one of those is a bug.
    """
    game = get_game("catan")
    script = load_script(SCRIPT)
    run = GameRun(game, script.config, game_id="g-0001", directory=tmp_path)

    drive(run, script)
    run.finish()

    produced = tmp_path / "games" / "g-0001.god.jsonl"
    assert produced.read_bytes() == RECORD.read_bytes()


def test_the_two_halves_of_the_fixture_agree() -> None:
    """The script is the input and the record is the output: they must describe one game."""
    script = load_script(SCRIPT)
    actions = _log().actions

    assert len(script.actions) == len(actions) == ACTIONS
    for scripted, recorded in zip(script.actions, actions, strict=True):
        assert scripted.player == recorded.player
        assert scripted.type == recorded.action.type
        assert dict(scripted.params) == dict(recorded.action.params)


def test_the_record_ends_where_slice_2_ends() -> None:
    """The draft is complete, and the game is waiting for a turn structure to exist."""
    log = _log()
    terminal = log.terminal

    assert terminal is not None
    assert terminal.total_actions == ACTIONS
    assert terminal.rejections == 0
    assert terminal.winner is None, "nobody has won a game that has not started"
    assert dict(terminal.final_scores) == {str(seat): 2 for seat in range(SEATS)}, (
        "two settlements each is two victory points each"
    )


def test_every_transition_is_announced_in_the_record() -> None:
    log = _log()
    phases = [record.phase for record in log.phases]

    assert phases == (["setup_road", "setup_settlement"] * 7 + ["setup_road", "turn_start"]), (
        "the draft alternates settlement and road, and then the first turn opens"
    )


def test_every_intermediate_state_renders() -> None:
    """The slice's exit condition: replay with --print-states renders every placement."""
    log = _log()
    game = get_game(log.header.game)
    replayed = replay(log, game)

    for index, _record in enumerate(log.actions):
        state = replayed.states[index + 1]
        text = render(game.observe_spectator(state))
        assert "board:" in text, f"state after seq {index} did not render a board"
        assert f"turn {state.turn}" in text
    assert "board:" in render(game.observe_spectator(replayed.states[0]))


def test_the_record_is_deterministic_text() -> None:
    """No wall clock, no host, no process id, and no carriage returns: bytes are the point."""
    raw = RECORD.read_bytes()

    assert b"\r" not in raw
    text = raw.decode("utf-8")
    for forbidden in ('"at":', '"host":', '"pid":'):
        assert forbidden not in text
    assert raw.endswith(b"\n")


def test_the_record_carries_the_versions_it_was_produced_under() -> None:
    header = _log().header

    assert header.game == "catan"
    assert header.rules_version == "catan-rules-1"
    assert header.schema_version == "catan-actions-1"
    assert header.schema == "lgbg.game.v1"
    assert header.engine_version
    assert header.config["board"] == "fixed:standard_a"
    assert json.dumps(dict(header.prompt_hashes)) == "{}", "no prompt yet in this release"


def test_the_scripted_file_is_lf_only_too() -> None:
    """Both halves are hashed and compared as bytes, so neither may depend on the platform."""
    raw = SCRIPT.read_bytes()

    assert b"\r" not in raw
    assert raw.endswith(b"\n")
