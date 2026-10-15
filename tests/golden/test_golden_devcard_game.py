"""Golden game 4: a win that comes from a development card (K-048; PRD-v1 SC-1).

The first three fixtures never buy a development card. This one plays the whole base game with the
deck in it - seventeen purchases, thirteen plays, knights, both progress cards used, both awards
changing hands - and the winner's tenth point is *required* to come from a card, which is asserted
rather than hoped for: without the two points of Largest Army and the two hidden victory-point
cards, that player's total would be six, and the game would not have ended.

The fixture is committed in two halves, both deterministic: the scripted action file is the input,
the god log is what the engine produced. The test plays the first and compares it to the second.
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
from lgbg.games.catan.rules.victory import victory_points
from lgbg.games.catan.state import CARD_ORDER, DevCard, Phase

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SCRIPT: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "catan" / "devcard_game.json"
RECORD: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan" / "devcard_game.god.jsonl"

INITIAL_STATE_HASH: Final[str] = "f8ef29543c198007"
FINAL_STATE_HASH: Final[str] = "34fec8a48e21537f"
ACTIONS: Final[int] = 476
SEATS: Final[int] = 4
TARGET: Final[int] = 10
VP: Final[int] = CARD_ORDER.index(DevCard.VICTORY_POINT)
ARMY_POINTS: Final[int] = 2

PLAYED: Final[tuple[str, ...]] = (
    "dev_card_bought",
    "dev_card_played",
    "game_won",
    "largest_army_awarded",
    "longest_road_awarded",
    "monopoly_taken",
    "resources_taken",
)


def _log() -> Any:
    return GameLogReader(RECORD).read()


def test_the_committed_record_replays_with_every_hash_verified() -> None:
    """SC-1: every intermediate state reconstructed, every hash asserted."""
    log = _log()
    game = get_game(log.header.game)

    report = verify(log, game)

    assert report.actions == ACTIONS
    assert report.rejections == 0
    assert log.header.initial_state_hash == INITIAL_STATE_HASH
    assert report.terminal_hash == FINAL_STATE_HASH
    assert replay(log, game).states[-1].phase is Phase.TERMINAL


def test_the_winner_could_not_have_won_without_a_development_card() -> None:
    """K-048's real acceptance criterion, asserted as a subtraction rather than a story."""
    log = _log()
    game = get_game(log.header.game)
    final = replay(log, game).states[-1]
    winner = int(log.terminal.winner)
    from_cards = (
        final.dev_cards[winner][VP]
        + (ARMY_POINTS if final.largest_army == winner else 0)
        + (ARMY_POINTS if final.longest_road == winner else 0)
    )

    assert victory_points(final, winner) >= TARGET
    assert from_cards >= 4, "the fixture must win on card points, not on buildings"
    assert victory_points(final, winner) - from_cards < TARGET, (
        "strip the card points out and the game would not have ended"
    )


def test_the_fixture_plays_the_cards_it_is_here_to_pin() -> None:
    """A fixture that stopped exercising a card would still replay perfectly, so assert it does."""
    played = {event.type for record in _log().actions for event in record.events}

    assert set(PLAYED) <= played, f"never played: {sorted(set(PLAYED) - played)}"


def test_the_game_ends_the_way_the_rules_say_it_does() -> None:
    log = _log()
    terminal = log.terminal
    game = get_game(log.header.game)
    final = replay(log, game).states[-1]

    assert terminal is not None
    assert terminal.total_actions == ACTIONS
    assert terminal.rejections == 0
    assert terminal.winner is not None
    assert int(terminal.final_scores[str(terminal.winner)]) >= TARGET
    assert game.outcome(final).winner == terminal.winner


def test_playing_the_committed_script_reproduces_the_record_byte_for_byte(tmp_path: Path) -> None:
    """The regression net: a card's rule changing moves a hash, and this fails."""
    game = get_game("catan")
    script = load_script(SCRIPT)
    run = GameRun(game, script.config, game_id="g-0004", directory=tmp_path)

    drive(run, script)
    run.finish()

    produced = tmp_path / "games" / "g-0004.god.jsonl"
    assert produced.read_bytes() == RECORD.read_bytes()


def test_the_two_halves_of_the_fixture_agree() -> None:
    script = load_script(SCRIPT)
    actions = _log().actions

    assert len(script.actions) == len(actions) == ACTIONS
    for scripted, recorded in zip(script.actions, actions, strict=True):
        assert scripted.player == recorded.player
        assert scripted.type == recorded.action.type
        assert dict(scripted.params) == dict(recorded.action.params)


def test_every_intermediate_state_renders_and_hides_the_cards() -> None:
    """The cards are exercised, so this is also the fixture where hidden points matter most."""
    log = _log()
    game = get_game(log.header.game)
    replayed = replay(log, game)

    for index, _record in enumerate(log.actions):
        state = replayed.states[index + 1]
        for seat in range(SEATS):
            text = render(game.observe(state, seat))
            assert "hand:" in text
            assert "points:" in text, "every view carries the score it can compute"
            assert "dev_cards" not in text
    assert Phase.TERMINAL.value in render(game.observe_spectator(replayed.states[-1]))


def test_the_record_is_deterministic_text() -> None:
    raw = RECORD.read_bytes()

    assert b"\r" not in raw
    text = raw.decode("utf-8")
    for forbidden in ('"at":', '"host":', '"pid":'):
        assert forbidden not in text
    assert raw.endswith(b"\n")
    assert SCRIPT.read_bytes().endswith(b"\n")


def test_the_record_carries_the_versions_it_was_produced_under() -> None:
    header = _log().header

    assert header.game == "catan"
    assert header.rules_version == "catan-rules-6"
    assert header.schema_version == "catan-actions-1"
    assert header.config["board"] == "fixed:standard_a"
    assert json.dumps(dict(header.prompt_hashes)) == "{}"
