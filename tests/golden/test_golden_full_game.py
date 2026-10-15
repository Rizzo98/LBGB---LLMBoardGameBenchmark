"""Golden game 3: a whole game, played to a win (K-038; PRD-v1 SC-1).

The first two fixtures stop where their slice stopped. This one is the exit condition of slice 4:
743 actions played from the opening position to the tenth victory point, ending in the terminal
record the runtime writes when somebody wins. Everything the earlier slices built takes part in
it - the draft, production, a seven and its forced discards, the robber and its seizures, roads,
settlements, cities, the Longest Road card changing hands - and every one of those is asserted to
be *in* the record rather than assumed, because a fixture that stopped exercising a rule would
still replay perfectly.

The fixture is committed in two halves, both deterministic: the scripted action file is the
input, the god log is what the engine produced. The test plays the first and compares it to the
second, which is what makes the pair a regression net rather than a transcript nobody checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from lgbg.adapters.cli.main import main
from lgbg.adapters.cli.script import drive, load_script
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader
from lgbg.core.replay import replay, verify
from lgbg.games.catan.notation import render
from lgbg.games.catan.rules.victory import victory_points
from lgbg.games.catan.state import Phase

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SCRIPT: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "catan" / "full_game.json"
RECORD: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan" / "full_game.god.jsonl"

INITIAL_STATE_HASH: Final[str] = "77dc715bc5abf370"
FINAL_STATE_HASH: Final[str] = "e57e23d3c4839159"
ACTIONS: Final[int] = 743
ROUNDS: Final[int] = 68
WINNER: Final[int] = 0
SEATS: Final[int] = 4
TARGET: Final[int] = 10

PLAYED: Final[tuple[str, ...]] = (
    "city_built",
    "discarded",
    "game_won",
    "longest_road_awarded",
    "production",
    "resources_granted",
    "road_built",
    "robber_moved",
    "robber_stole",
    "settlement_placed",
    "turn_ended",
)
"""The rules this fixture is required to exercise, asserted rather than hoped for."""


def _log() -> Any:
    return GameLogReader(RECORD).read()


def _event_types(log: Any) -> set[str]:
    return {event.type for record in log.actions for event in record.events}


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
    assert replayed.states[-1].phase is Phase.TERMINAL
    assert replayed.states[0].phase is Phase.SETUP_ROUND_1


def test_the_game_ends_the_way_the_rules_say_it_does() -> None:
    """FR-15.4: the terminal record carries the winner, the totals and the length of the game."""
    log = _log()
    game = get_game(log.header.game)
    terminal = log.terminal
    final = replay(log, game).states[-1]

    assert terminal is not None
    assert terminal.winner == WINNER
    assert terminal.total_actions == ACTIONS
    assert terminal.rejections == 0
    assert terminal.rounds == ROUNDS
    assert terminal.state_hash == FINAL_STATE_HASH
    assert int(terminal.final_scores[str(WINNER)]) >= TARGET
    assert [record.phase for record in log.phases][-1] == Phase.TERMINAL.value
    assert game.is_terminal(final) is True
    assert game.outcome(final).winner == WINNER


def test_the_win_was_announced_by_the_engine_not_claimed_by_a_player() -> None:
    """RULES.md 4.13 item 7: there is no claim action, so the record must contain the verdict."""
    log = _log()
    won = [
        dict(event.payload)
        for record in log.actions
        for event in record.events
        if event.type == "game_won"
    ]

    assert len(won) == 1
    assert won[0]["player"] == WINNER
    assert won[0]["points"] >= TARGET
    assert won[0]["target"] == TARGET
    assert log.actions[-1].action.type != "claim_victory", "no such action exists"


def test_the_fixture_actually_plays_the_rules_it_is_here_to_pin() -> None:
    """A fixture that stopped exercising a rule would still replay perfectly, so assert it does."""
    played = _event_types(_log())

    assert set(PLAYED) <= played, f"the game never played: {sorted(set(PLAYED) - played)}"
    assert "dice_rolled" in played


def test_playing_the_committed_script_reproduces_the_record_byte_for_byte(tmp_path: Path) -> None:
    """The regression net: a rule change moves a hash, and this fails.

    If it fails, read the diff before regenerating anything: either the fixture is stale or a
    rule changed, and only one of those is a bug.
    """
    game = get_game("catan")
    script = load_script(SCRIPT)
    run = game_run(game, script, tmp_path)

    drive(run, script)
    run.finish()

    produced = tmp_path / "games" / "g-0003.god.jsonl"
    assert produced.read_bytes() == RECORD.read_bytes()


def game_run(game: Any, script: Any, directory: Path) -> Any:
    from lgbg.core.run import GameRun

    return GameRun(game, script.config, game_id="g-0003", directory=directory)


def test_the_two_halves_of_the_fixture_agree() -> None:
    """The script is the input and the record is the output: they must describe one game."""
    script = load_script(SCRIPT)
    actions = _log().actions

    assert len(script.actions) == len(actions) == ACTIONS
    for scripted, recorded in zip(script.actions, actions, strict=True):
        assert scripted.player == recorded.player
        assert scripted.type == recorded.action.type
        assert dict(scripted.params) == dict(recorded.action.params)


def test_every_intermediate_state_renders_for_the_table_and_for_a_player() -> None:
    """SC-1: a replay of this game is readable, state by state, by an operator."""
    log = _log()
    game = get_game(log.header.game)
    replayed = replay(log, game)

    for index, _record in enumerate(log.actions):
        state = replayed.states[index + 1]
        assert "board:" in render(game.observe_spectator(state))
        for seat in range(SEATS):
            view = render(game.observe(state, seat))
            assert "hand:" in view
            assert "hands:" not in view
    final = render(game.observe_spectator(replayed.states[-1]))
    assert Phase.TERMINAL.value in final


def test_the_cli_replays_the_record_and_prints_its_states(capsys: Any) -> None:
    """The same replay, through the surface an operator actually uses."""
    code = main(["replay", str(RECORD), "--print-states", "--compact"])

    printed = capsys.readouterr().out
    assert code == 0
    assert Phase.TERMINAL.value in printed
    assert "board" in printed


def test_the_record_is_deterministic_text() -> None:
    """No wall clock, no host, no process id, and no carriage returns: bytes are the point."""
    raw = RECORD.read_bytes()

    assert b"\r" not in raw
    text = raw.decode("utf-8")
    for forbidden in ('"at":', '"host":', '"pid":'):
        assert forbidden not in text
    assert raw.endswith(b"\n")
    assert SCRIPT.read_bytes().endswith(b"\n")
    assert b"\r" not in SCRIPT.read_bytes()


def test_the_record_carries_the_versions_it_was_produced_under() -> None:
    header = _log().header

    assert header.game == "catan"
    assert header.rules_version == "catan-rules-6"
    assert header.schema_version == "catan-actions-1"
    assert header.schema == "lgbg.game.v1"
    assert header.engine_version
    assert header.config["board"] == "fixed:standard_a"
    assert json.dumps(dict(header.prompt_hashes)) == "{}", "no prompt yet in this release"


@pytest.mark.parametrize("seat", range(SEATS))
def test_every_seat_was_worth_what_the_scoring_says_at_the_end(seat: int) -> None:
    """The terminal totals are the scoring rule applied to the final position, not a memory."""
    log = _log()
    game = get_game(log.header.game)
    final = replay(log, game).states[-1]
    terminal = log.terminal
    assert terminal is not None

    assert victory_points(final, seat) == int(terminal.final_scores[str(seat)])
