"""A human plays the full game through play-live (PRD-v2 FR-14.4, SC-14).

The input here is what a person would type: one JSON action per line. Nothing in the command
gets to use the facade directly; the projection, the decisions and every action all travel over
the MCP sandbox surface. The record is the same committed record the scripted client produces,
which is what makes the human path a client rather than a second implementation.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.cli.main import main
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "catan" / "full_game.json"
GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "catan" / "full_game.god.jsonl"
SESSION_ID = "g-0003"


def test_play_live_plays_the_full_game_by_hand(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """SC-14: a human's action lines produce the same record as the scripted client."""
    script: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actions: list[dict[str, Any]] = script["actions"]
    config: dict[str, Any] = script["config"]
    typed = "".join(json.dumps(entry) + "\n" for entry in actions)
    monkeypatch.setattr(sys, "stdin", io.StringIO(typed))
    out = tmp_path / "run"

    code = main(
        [
            "play-live",
            "--game",
            "catan",
            "--seed",
            str(config["seed"]),
            "--players",
            str(config["players"]),
            "--session-id",
            SESSION_ID,
            "--out",
            str(out),
            "--board",
            str(config["board"]),
            "--detail",
            "compact",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "record:" in captured.out
    record = god_log_path(out, SESSION_ID)
    assert record.read_bytes() == GOLDEN.read_bytes()
    log = GameLogReader(record).read()
    game = get_game("catan")
    assert verify(log, game).actions == len(actions)
    assert len(replay(log, game).states) == len(actions) + 1
    assert log.terminal is not None


def test_play_live_at_l0_exposes_the_projection_and_still_accepts_an_action(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """PRD-v2 FR-4.1: with no decisions resource, the operator names the seat and plays on."""
    typed = json.dumps({"player": 0, "type": "take"}) + "\nquit\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(typed))
    out = tmp_path / "l0"

    code = main(
        [
            "play-live",
            "--game",
            "fixture",
            "--plugin",
            "tests.games.fixture_game",
            "--players",
            "2",
            "--session-id",
            "g-l0",
            "--out",
            str(out),
            "--assist",
            "L0",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "open decisions: not exposed at this assist level" in captured.out
    assert "accepted take by seat 0" in captured.out
    log = GameLogReader(god_log_path(out, "g-l0")).read()
    assert [record.action.type for record in log.actions] == ["take"]
