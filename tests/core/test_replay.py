"""Replay and verification (PRD-v1 FR-4.1 to FR-4.7).

This is what makes the record a program rather than a transcript. Replay rebuilds every
intermediate state through the normal 'apply' path, so the engine cannot diverge from the
record without the hashes disagreeing; verification walks the same chain while keeping only
the current state, so a large corpus can be checked cheaply.

Every failure localises itself. A verification that says "replay failed" is nearly useless
at scale; one that says which seq, which kind, and what disagreed is diagnosable from the
message alone (NFR-11).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lgbg.core.canonical import hash_state
from lgbg.core.log import GameLogReader
from lgbg.core.replay import (
    ReplayedGame,
    ReplayError,
    ReplayFailure,
    VerificationReport,
    projection_replay,
    replay,
    verify,
)
from tests.games.fixture_game import FixtureGame
from tests.support.records import record_fixture_game, rewrite_records


def _log(tmp_path: Path, **kwargs: Any) -> Any:
    return GameLogReader(record_fixture_game(tmp_path, **kwargs)).read()


def test_replay_reconstructs_the_state_after_every_action(tmp_path: Path) -> None:
    log = _log(tmp_path, actions=6)

    replayed = replay(log, FixtureGame())

    assert isinstance(replayed, ReplayedGame)
    assert len(replayed.states) == len(log.actions) + 1
    assert log.terminal is not None
    assert hash_state(replayed.states[-1], FixtureGame()) == log.terminal.state_hash


def test_replay_is_the_normal_apply_path_not_a_second_implementation(tmp_path: Path) -> None:
    log = _log(tmp_path, actions=4)

    replayed = replay(log, FixtureGame())

    for index, record in enumerate(log.actions):
        assert hash_state(replayed.states[index], FixtureGame()) == record.state_hash_prev


def test_replay_reports_a_mismatch_in_the_state_before_an_action(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(
        path, lambda records: records[2].__setitem__("state_hash_prev", "deadbeefdeadbeef")
    )

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.HASH_MISMATCH
    assert raised.value.seq == 1
    assert "seq 1" in str(raised.value)


def test_replay_reports_a_mismatch_in_the_state_after_an_action(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(path, lambda records: records[3].__setitem__("state_hash", "deadbeefdeadbeef"))

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.HASH_MISMATCH
    assert raised.value.seq == 2


def test_replay_reports_a_changed_action(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(path, lambda records: records[2]["action"].__setitem__("type", "take"))

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.seq == 1


def test_replay_reports_an_action_the_game_does_not_declare(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(path, lambda records: records[1]["action"].__setitem__("type", "teleport"))

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.UNKNOWN_ACTION
    assert raised.value.seq == 0


def _different_draw(value: int) -> int:
    """A value that cannot equal the recorded one, whatever the recorded one was."""
    return value % 3 + 1


def test_replay_reports_a_changed_draw_value(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(
        path,
        lambda records: records[1]["rng"][0].__setitem__(
            "value", _different_draw(records[1]["rng"][0]["value"])
        ),
    )

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.seq == 0


def test_replay_reports_a_reordered_draw_purpose(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(path, lambda records: records[1]["rng"][0].__setitem__("purpose", "deck_deal"))

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.RNG_MISMATCH
    assert raised.value.seq == 0
    assert "deck_deal" in str(raised.value)


def test_replay_reports_a_missing_recorded_draw(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(path, lambda records: records[1].__setitem__("rng", []))

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.RNG_MISMATCH
    assert raised.value.seq == 0


def test_replay_reports_an_unconsumed_recorded_draw(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    extra = {"args": {"lo": 1, "hi": 3}, "kind": "randint", "purpose": "gamble_bonus", "value": 1}
    rewrite_records(path, lambda records: records[1]["rng"].append(extra))

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.RNG_EXHAUSTION
    assert raised.value.seq == 0


def test_replay_reports_a_changed_event_payload(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    # A gain the fixture can never produce, so the edit always changes the event.
    rewrite_records(
        path, lambda records: records[1]["events"][0]["payload"].__setitem__("amount", 9)
    )

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.EVENT_MISMATCH
    assert raised.value.seq == 0


def test_replay_reports_a_mismatched_initial_state(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=3)
    rewrite_records(
        path, lambda records: records[0].__setitem__("initial_state_hash", "0000000000000000")
    )

    with pytest.raises(ReplayError) as raised:
        replay(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.INITIAL_STATE_MISMATCH


def test_a_recorded_rejection_replays_and_leaves_the_hash_unchanged(tmp_path: Path) -> None:
    """SC-5: rejection invariance, asserted on a real record rather than in principle."""
    log = _log(tmp_path, actions=6, with_rejection=True)
    rejected = [record for record in log.actions if record.result["ok"] is False]

    replayed = replay(log, FixtureGame())

    assert rejected, "the fixture must have produced a rejected action"
    for record in rejected:
        assert record.state_hash == record.state_hash_prev
        assert hash_state(replayed.states[record.seq + 1], FixtureGame()) == record.state_hash_prev


def test_verify_walks_the_chain_and_reports_counts(tmp_path: Path) -> None:
    log = _log(tmp_path, actions=6)

    report = verify(log, FixtureGame())

    assert isinstance(report, VerificationReport)
    assert report.actions == len(log.actions)
    assert report.rejections == 0
    assert report.terminal_hash == log.terminal.state_hash


def test_verify_keeps_only_the_current_state(tmp_path: Path) -> None:
    """FR-4.4: verification must be affordable over a large corpus."""
    report = verify(_log(tmp_path, actions=6), FixtureGame())

    assert not hasattr(report, "states")


def test_verify_reports_the_offending_seq(tmp_path: Path) -> None:
    path = record_fixture_game(tmp_path, actions=5)
    rewrite_records(path, lambda records: records[2].__setitem__("state_hash", "deadbeefdeadbeef"))

    with pytest.raises(ReplayError) as raised:
        verify(GameLogReader(path).read(), FixtureGame())

    assert raised.value.seq == 1
    assert "seq 1" in str(raised.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [("total_actions", 99), ("rejections", 3), ("state_hash", "deadbeefdeadbeef")],
)
def test_verify_rejects_an_inconsistent_terminal_record(
    tmp_path: Path, field: str, value: Any
) -> None:
    path = record_fixture_game(tmp_path, actions=4)
    rewrite_records(path, lambda records: records[-1].__setitem__(field, value))

    with pytest.raises(ReplayError):
        verify(GameLogReader(path).read(), FixtureGame())


def test_verify_rejects_a_terminal_record_that_disagrees_with_the_final_state(
    tmp_path: Path,
) -> None:
    path = record_fixture_game(tmp_path, actions=4)
    rewrite_records(path, lambda records: records[-1].__setitem__("winner", 0))

    with pytest.raises(ReplayError, match="winner"):
        verify(GameLogReader(path).read(), FixtureGame())


def test_projection_replay_rebuilds_what_one_player_saw(tmp_path: Path) -> None:
    """FR-4.6: the exact sequence of observations, taken from the pre-action states."""
    log = _log(tmp_path, actions=6)
    game = FixtureGame()
    replayed = replay(log, game)

    for player in (0, 1):
        observations = projection_replay(log, game, player)
        expected = [
            game.observe(replayed.states[index], player)
            for index, record in enumerate(log.actions)
            if record.player == player
        ]
        assert observations == expected
        assert observations, f"player {player} acted at least once"


def test_projection_replay_hides_the_other_players_holding(tmp_path: Path) -> None:
    log = _log(tmp_path, actions=6)
    game = FixtureGame()

    for observation in projection_replay(log, game, 0):
        opponents: Any = observation["opponents"]
        assert isinstance(observation["tokens"], int)
        assert set(opponents) == {"1"}, "another player's holding is visible only as a count"


def test_replay_rejects_a_log_that_is_not_a_complete_game(tmp_path: Path) -> None:
    """A record without a terminal line still replays: a crashed run is worth diagnosing."""
    path = record_fixture_game(tmp_path, actions=3)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    replayed = replay(GameLogReader(path).read(), FixtureGame())

    assert len(replayed.states) == 4
