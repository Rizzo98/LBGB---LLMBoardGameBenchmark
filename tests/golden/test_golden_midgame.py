"""Golden game 2: a seven, a forced discard and a steal, pinned byte for byte (K-029, SC-1).

Golden game 1 pins the opening draft, where the only randomness is the deck. This one pins what
happens once the dice have started paying: the same seed played seventeen actions further, until
a seven forces a player to return six cards to the bank and takes one card off another player.
Between them, the two fixtures cover every way a card moves in a game - production, the
endowment, a forced discard, a seizure - and every one of them is a recorded draw or an action
with a hash on both sides.

The fixture is committed in two halves, both deterministic: the scripted action file is the
input, the god log is what the engine produced. The test plays the first and compares it to the
second, which is what makes the pair a regression net rather than a transcript nobody checks.
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
from lgbg.games.catan.state import RESOURCE_ORDER, Phase

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SCRIPT: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "catan" / "seven_game.json"
RECORD: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan" / "seven_game.god.jsonl"
SETUP_RECORD: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan" / "setup_game.god.jsonl"

INITIAL_STATE_HASH: Final[str] = "0e3933658fbc42f3"
FINAL_STATE_HASH: Final[str] = "b59ca27542264e0c"
ACTIONS: Final[int] = 43
DRAFT_ACTIONS: Final[int] = 16
SEATS: Final[int] = 4
DISCARDED: Final[dict[str, Any]] = {"player": 3, "count": 6}
STOLEN: Final[dict[str, Any]] = {"player": 0, "victim": 3, "resource": "wool"}


def _log(path: Path = RECORD) -> Any:
    return GameLogReader(path).read()


def _events(log: Any, kind: str) -> list[dict[str, Any]]:
    return [
        dict(event.payload)
        for record in log.actions
        for event in record.events
        if event.type == kind
    ]


def _actions_of(log: Any, kind: str) -> list[int]:
    return [
        record.seq for record in log.actions if any(event.type == kind for event in record.events)
    ]


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
    assert replayed.states[-1].round == 3


def test_the_record_contains_a_forced_discard_and_a_seizure() -> None:
    """K-029: the fixture is only worth committing if the two events are provably in it."""
    log = _log()
    game = get_game(log.header.game)
    states = replay(log, game).states

    discarded = _events(log, "discarded")
    stolen = _events(log, "robber_stole")

    assert len(discarded) == 1, "one seven was rolled in this game"
    assert len(stolen) == 1
    seat = DISCARDED["player"]
    before = states[_actions_of(log, "discarded")[0]]
    assert sum(before.hands[seat]) > 7, "a discard only happens above the limit"
    assert discarded[0] == {
        "player": seat,
        "count": DISCARDED["count"],
        "discarded": discarded[0]["discarded"],
    }
    assert discarded[0]["count"] == sum(before.hands[seat]) // 2, "half the hand, rounded down"
    assert dict(stolen[0]) == STOLEN


def test_the_replayed_states_show_the_cards_leaving_and_arriving() -> None:
    """The record moves cards; the ledger is what proves it moved them and did not make them."""
    log = _log()
    game = get_game(log.header.game)
    states = replay(log, game).states

    discard_at = _actions_of(log, "discarded")[0]
    steal_at = _actions_of(log, "robber_stole")[0]
    victim = int(STOLEN["victim"])
    thief = int(STOLEN["player"])
    taken = RESOURCE_ORDER.index(
        next(resource for resource in RESOURCE_ORDER if resource.value == STOLEN["resource"])
    )

    discarded_before, discarded_after = states[discard_at], states[discard_at + 1]
    assert sum(discarded_after.hands[DISCARDED["player"]]) == (
        sum(discarded_before.hands[DISCARDED["player"]]) - DISCARDED["count"]
    )
    for index in range(len(RESOURCE_ORDER)):
        assert discarded_after.bank[index] == discarded_before.bank[index] + _returned(
            discarded_before, discarded_after, index
        ), "every discarded card went back to the bank"

    stole_before, stole_after = states[steal_at], states[steal_at + 1]
    assert stole_after.hands[victim][taken] == stole_before.hands[victim][taken] - 1
    assert stole_after.hands[thief][taken] == stole_before.hands[thief][taken] + 1
    assert game.check_invariants(stole_after) == []


def _returned(before: Any, after: Any, index: int) -> Any:
    """What went back to the bank: the hands before minus the hands after, for one resource."""
    held_before: int = sum(hand[index] for hand in before.hands)
    held_after: int = sum(hand[index] for hand in after.hands)
    return held_before - held_after


def test_the_seven_skipped_production_entirely() -> None:
    """FR-10.5: the roll that forced the discard paid nobody, and the turn waited on the robber."""
    log = _log()
    seven_at = _actions_of(log, "discarded")[0] - 1

    rolled = log.actions[seven_at]
    dice = [dict(event.payload) for event in rolled.events if event.type == "dice_rolled"]

    assert rolled.action.type == "roll_dice"
    assert len(dice) == 1, "the roll is recorded once"
    assert sum(dice[0]["dice"]) == 7
    assert not [event for event in rolled.events if event.type == "production"]
    phases = [record.phase for record in log.phases]
    assert phases[phases.index("discard") + 1] == "robber"
    assert phases[-1] == "action", "the turn goes on once the seven is resolved"


def test_the_draft_of_the_two_golden_games_is_the_same_game() -> None:
    """Both fixtures are one seed: the first sixteen records must be identical, byte for byte."""
    midgame = _log()
    setup = _log(SETUP_RECORD)

    assert midgame.header.initial_state_hash == setup.header.initial_state_hash
    assert midgame.header.config == setup.header.config
    assert midgame.actions[:DRAFT_ACTIONS] == setup.actions
    assert midgame.terminal is not None
    assert midgame.terminal.rounds == 3


def test_playing_the_committed_script_reproduces_the_record_byte_for_byte(tmp_path: Path) -> None:
    """The regression net: a rule change moves a hash, and this fails.

    If it fails, read the diff before regenerating anything: either the fixture is stale or a
    rule changed, and only one of those is a bug.
    """
    game = get_game("catan")
    script = load_script(SCRIPT)
    run = GameRun(game, script.config, game_id="g-0002", directory=tmp_path)

    drive(run, script)
    run.finish()

    produced = tmp_path / "games" / "g-0002.god.jsonl"
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


def test_every_intermediate_state_renders_for_the_table_and_for_a_player() -> None:
    """SC-1: replay with --print-states renders every state, and so does a player's own view."""
    log = _log()
    game = get_game(log.header.game)
    replayed = replay(log, game)

    for index, _record in enumerate(log.actions):
        state = replayed.states[index + 1]
        assert "board:" in render(game.observe_spectator(state))
        assert f"turn {state.turn}" in render(game.observe_spectator(state))
        for seat in range(SEATS):
            view = render(game.observe(state, seat))
            assert "hand:" in view, "every player's own hand is rendered"
            assert "hands:" not in view, "and nobody's view holds everybody's hands"


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
    assert [record.phase for record in _log().phases][:1] == [Phase.SETUP_ROUND_2.value], (
        "the draft opened the game and round one is where it started"
    )
