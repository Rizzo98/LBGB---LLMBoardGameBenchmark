"""The god log: writer and reader (PRD-v1 FR-3.1 to FR-3.9).

The record is the release's central artefact. A log is a transcript; this is a program -
replayable, verifiable, and the input every metric is computed from. Two properties matter
more than the others here:

- The deterministic record and the sidecar are *physically separate files*, so nothing
  non-deterministic can enter the hash chain by accident (P9).
- A rejected action is a first-class record whose state hash does not move, which makes
  illegal-move rate measurable without special-casing anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from lgbg.core.canonical import hash_state
from lgbg.core.config import GameConfig
from lgbg.core.errors import UNKNOWN_ACTION, Rejection
from lgbg.core.log import (
    GOD_LOG_SCHEMA,
    ActionRecord,
    GameLogReader,
    GameLogWriter,
    HeaderRecord,
    LogFormatError,
    PhaseRecord,
    SidecarWriter,
    TerminalRecord,
    TruncatedLogError,
    UnknownRecordTypeError,
    UnsupportedSchemaError,
    god_log_path,
    rejected_result,
    sidecar_path,
)
from lgbg.core.rng import NullRandomSource, RngDraw
from lgbg.core.types import Action, Event, JsonValue
from tests.games.fixture_game import FixtureGame

FIXED_TIME: Final[str] = "2025-01-01T00:00:00+00:00"


def _header(game: FixtureGame) -> HeaderRecord:
    state: Any = game.initial_state(GameConfig({}), NullRandomSource())
    return HeaderRecord(
        game_id="g-0001",
        game=game.name,
        rules_version=game.rules_version,
        schema_version=game.schema_version,
        players=2,
        config={"seed": 7, "assist": "L1"},
        prompt_hashes={},
        initial_state_hash=hash_state(state, game),
    )


def _accepted(seq: int, prev_hash: str, new_hash: str) -> ActionRecord:
    return ActionRecord(
        seq=seq,
        player=0,
        action=Action(player=0, type="take", params={}),
        result={"ok": True},
        state_hash_prev=prev_hash,
        state_hash=new_hash,
        rng=[RngDraw(purpose="gamble_bonus", kind="randint", args={"lo": 1, "hi": 3}, value=2)],
        events=[Event(type="tokens_gained", payload={"player": 0, "amount": 1})],
        request_id="d0",
    )


def _rejected(seq: int, state_hash: str) -> ActionRecord:
    rejection = Rejection(
        code=UNKNOWN_ACTION, message="no such action", details={"action_type": "fly"}
    )
    return ActionRecord(
        seq=seq,
        player=0,
        action=Action(player=0, type="fly", params={}),
        result=rejected_result(rejection),
        state_hash_prev=state_hash,
        state_hash=state_hash,
        rng=[],
        events=[],
        request_id=None,
    )


def _terminal(seq: int, state_hash: str) -> TerminalRecord:
    return TerminalRecord(
        seq=seq,
        winner=0,
        final_scores={"0": 2, "1": 1},
        rounds=9,
        total_actions=seq,
        rejections=1,
        state_hash=state_hash,
    )


def test_writer_writes_header_action_and_terminal_in_order(tmp_path: Path) -> None:
    game = FixtureGame()
    writer = GameLogWriter(god_log_path(tmp_path, "g-0001"))
    writer.write_header(_header(game))
    writer.write_action(_accepted(0, "aaaa", "bbbb"))
    writer.write_action(_rejected(1, "bbbb"))
    writer.write_terminal(_terminal(2, "bbbb"))
    writer.close()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()

    assert [record.kind for record in log.records] == ["header", "action", "action", "terminal"]
    assert [record.seq for record in log.actions] == [0, 1]
    assert log.terminal is not None
    assert log.terminal.total_actions == 2
    assert log.header.game_id == "g-0001"
    assert log.header.schema == GOD_LOG_SCHEMA


def test_records_round_trip_exactly(tmp_path: Path) -> None:
    game = FixtureGame()
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    header = _header(game)
    accepted = _accepted(0, "aaaa", "bbbb")
    phase = PhaseRecord(seq=1, phase="play", detail={"turn": 0})
    terminal = _terminal(1, "bbbb")
    writer.write_header(header)
    writer.write_action(accepted)
    writer.write_phase(phase)
    writer.write_terminal(terminal)
    writer.close()

    log = GameLogReader(path).read()

    assert log.header == header
    assert log.actions == [accepted]
    assert log.phases == [phase]
    assert log.terminal == terminal


def test_a_rejected_action_leaves_the_state_hash_unchanged(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.write_action(_rejected(0, "9f8e7d6c5b4a3210"))
    writer.close()

    record = GameLogReader(path).read().actions[0]

    assert record.result["ok"] is False
    assert record.result["error"] == UNKNOWN_ACTION.code
    assert record.state_hash == record.state_hash_prev


def test_the_god_log_carries_no_time_host_or_pid(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.write_action(_accepted(0, "aaaa", "bbbb"))
    writer.close()

    text = path.read_text(encoding="utf-8")

    for forbidden in ('"at":', '"host":', '"pid":', "timestamp"):
        assert forbidden not in text, f"{forbidden} must live in the sidecar, not the record"


def test_the_sidecar_carries_time_host_and_pid(tmp_path: Path) -> None:
    path = sidecar_path(tmp_path, "g-0001")
    sidecar = SidecarWriter(path, clock=lambda: FIXED_TIME)
    payload: dict[str, JsonValue] = {"seq": 0, "agent": {"tokens": 12}}
    sidecar.write("action", payload)
    sidecar.close()

    written = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

    assert written["at"] == FIXED_TIME
    assert written["host"]
    assert isinstance(written["pid"], int)
    assert written["t"] == "action"
    assert written["agent"] == {"tokens": 12}


def test_records_are_flushed_as_they_are_written(tmp_path: Path) -> None:
    """FR-3.8: a crashed process must leave a parseable prefix, not nothing."""
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.write_action(_accepted(0, "aaaa", "bbbb"))

    seen_while_open = path.read_text(encoding="utf-8").splitlines()
    writer.close()

    assert len(seen_while_open) == 2


def test_a_truncated_final_line_is_reported_as_truncation(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.write_action(_accepted(0, "aaaa", "bbbb"))
    writer.close()
    text = path.read_text(encoding="utf-8")
    path.write_text(text[:-12], encoding="utf-8")

    with pytest.raises(TruncatedLogError) as raised:
        GameLogReader(path).read()

    assert "line 2" in str(raised.value)


def test_a_malformed_middle_line_is_reported_as_a_format_error(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.write_action(_accepted(0, "aaaa", "bbbb"))
    writer.write_terminal(_terminal(1, "bbbb"))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = "{not json at all"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(LogFormatError, match="line 2"):
        GameLogReader(path).read()


def test_an_unknown_schema_major_version_is_rejected_clearly(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.close()
    text = path.read_text(encoding="utf-8").replace(GOD_LOG_SCHEMA, "lgbg.game.v2")

    path.write_text(text, encoding="utf-8")

    with pytest.raises(UnsupportedSchemaError) as raised:
        GameLogReader(path).read()

    assert "lgbg.game.v2" in str(raised.value)


def test_a_minor_schema_bump_is_backward_compatible(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.close()
    text = path.read_text(encoding="utf-8").replace(GOD_LOG_SCHEMA, GOD_LOG_SCHEMA + ".1")

    path.write_text(text, encoding="utf-8")

    assert GameLogReader(path).read().header.schema == GOD_LOG_SCHEMA + ".1"


def test_an_unknown_record_type_is_rejected(tmp_path: Path) -> None:
    """FR-3.9: the runtime owns the record vocabulary; a game may not add a type."""
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.close()
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"t":"catan_special","seq":1}\n')

    with pytest.raises(UnknownRecordTypeError, match="catan_special"):
        GameLogReader(path).read()


def test_a_gap_in_the_action_sequence_is_rejected_on_read(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    writer = GameLogWriter(path)
    writer.write_header(_header(FixtureGame()))
    writer.write_action(_accepted(0, "aaaa", "bbbb"))
    writer.write_action(_accepted(1, "bbbb", "cccc"))
    writer.close()
    # Edited directly: the writer refuses to produce this, which is exactly the point.
    altered = path.read_text(encoding="utf-8").replace('"seq":1', '"seq":2')
    path.write_text(altered, encoding="utf-8")

    with pytest.raises(LogFormatError, match="seq"):
        GameLogReader(path).read()


def test_the_writer_refuses_a_gap_in_the_action_sequence(tmp_path: Path) -> None:
    writer = GameLogWriter(god_log_path(tmp_path, "g-0001"))
    writer.write_header(_header(FixtureGame()))

    with pytest.raises(LogFormatError, match="seq"):
        writer.write_action(_accepted(3, "aaaa", "bbbb"))


def test_the_writer_refuses_an_action_before_the_header(tmp_path: Path) -> None:
    writer = GameLogWriter(god_log_path(tmp_path, "g-0001"))

    with pytest.raises(LogFormatError, match="header"):
        writer.write_action(_accepted(0, "aaaa", "bbbb"))


def test_the_writer_refuses_anything_after_the_terminal_record(tmp_path: Path) -> None:
    writer = GameLogWriter(god_log_path(tmp_path, "g-0001"))
    writer.write_header(_header(FixtureGame()))
    writer.write_terminal(_terminal(0, "aaaa"))

    with pytest.raises(LogFormatError, match="terminal"):
        writer.write_action(_accepted(1, "aaaa", "bbbb"))


def test_a_header_may_only_be_written_once(tmp_path: Path) -> None:
    writer = GameLogWriter(god_log_path(tmp_path, "g-0001"))
    writer.write_header(_header(FixtureGame()))

    with pytest.raises(LogFormatError, match="header"):
        writer.write_header(_header(FixtureGame()))


def test_paths_follow_the_documented_run_layout(tmp_path: Path) -> None:
    assert god_log_path(tmp_path, "g-0001") == tmp_path / "games" / "g-0001.god.jsonl"
    assert sidecar_path(tmp_path, "g-0001") == tmp_path / "games" / "g-0001.meta.jsonl"


def test_an_empty_log_is_reported_as_truncated(tmp_path: Path) -> None:
    path = god_log_path(tmp_path, "g-0001")
    GameLogWriter(path).close()

    with pytest.raises(TruncatedLogError):
        GameLogReader(path).read()
