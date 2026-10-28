"""The unattended CI campaign: fifty games or more, every failing behaviour included (SC-12).

This is the mock's campaign, and it is deliberately not a smoke test. v2's claim is that a run
completes without a human, at a size where a hang or a leaked failure would show, and that its
results.json accounts for every game and every seat. The mock is what makes the failing half of
that cheap: the same command line an operator uses, with a table holding correct play, a timeout,
malformed arguments, prose, an illegal action and a runaway at once.

One experiment of ten rotated replicates over six seats is sixty games. Every rotation puts a
different behaviour in seat 0, so every failing behaviour is the recorded abandonment in one
rotation and the closing agent completes another; nothing is sampled by chance. It runs in the
gate because it is in the suite, not beside it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

import tests.games.campaign_game  # noqa: F401 - importing registers the game
from lgbg.adapters.cli.main import main
from lgbg.core.contracts import validate_results
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify

PLAYERS: Final[int] = 6
REPLICATES: Final[int] = 10
GAMES: Final[int] = PLAYERS * REPLICATES
RUN_ID: Final[str] = "r-campaign"
BEHAVIOURS: Final[tuple[str, ...]] = (
    "correct-play",
    "timeout",
    "malformed-arguments",
    "prose-only",
    "always-illegal",
    "runaway",
)
"""One seat per declared behaviour, in the order the rotation puts them in seat 0."""


def _config(tmp_path: Path) -> Path:
    prompt = tmp_path / "game.md"
    prompt.write_text("The campaign game: every seat marks once.\n", encoding="utf-8")
    seats: list[dict[str, Any]] = []
    for seat, behaviour in enumerate(BEHAVIOURS):
        spec: dict[str, Any] = {
            "seat": seat,
            "agent": "llm",
            "model": f"mock-{behaviour}",
            "provider": "mock",
            "behaviour": behaviour,
        }
        if behaviour == "correct-play":
            # The table is reused across games, so the script is one action per game it plays.
            spec["actions"] = [{"type": "close", "params": {}} for _ in range(GAMES)]
        if behaviour == "always-illegal":
            # Declared and always refused, so the redo budget is what ends the game - and the
            # record still replays, because a refusal is a legal record of a refused action.
            spec["actions"] = [{"type": "refuse", "params": {}}]
        seats.append(spec)
    payload: dict[str, Any] = {
        "game": "campaign",
        "config": {"seed": 20261028, "players": PLAYERS, "interaction_protocol": "decline_only"},
        "seats": seats,
        "design": {
            "seating": "rotated",
            "initial_configuration": "fixed",
            "replicates": REPLICATES,
        },
        "policies": {"redo_budget": 2, "step_budget": 3, "decision_timeout_s": 5},
        "prompts": {"game": str(prompt)},
    }
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_unattended_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """PRD-v2 FR-14.2, SC-12: sixty games on the mock, unattended, failures included."""
    config = _config(tmp_path)
    root = tmp_path / "run"

    code = main(
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(root),
            "--run-id",
            RUN_ID,
            "--concurrency",
            "4",
        ]
    )

    out, err = capsys.readouterr()
    assert code == 0, err + out
    assert "abandoned: 50" in out

    payload: dict[str, Any] = json.loads((root / "results.json").read_text(encoding="utf-8"))
    assert validate_results(payload) == []
    summary = payload["summary"]
    assert summary["games"] == GAMES
    assert summary["completed"] == REPLICATES, "one rotation in six closes the round"
    assert summary["abandoned"] == GAMES - REPLICATES
    assert summary["total_tokens"] > 0
    assert summary["latency_ms"] >= 0
    # A malformed call never reaches the engine, so only the engine's own refusals appear here;
    # the malformed behaviour is counted as a failure kind below.
    assert summary["rejections_by_code"] == {"REFUSED": 20}

    # Every failing behaviour is present, and none of them is a loss for anybody.
    failures = set(summary["failures_by_kind"])
    abandonment_kinds = {
        str(game["abandonment"]["failure"])
        for game in payload["games"]
        if game["abandonment"] is not None
    }
    assert {"timeout", "no_action", "malformed_arguments", "runaway"} <= failures
    assert {"timeout", "redo_exhausted", "no_action", "runaway"} == abandonment_kinds

    # Per game: the design point, and completed and abandoned are distinguishable.
    assert len(payload["games"]) == GAMES
    assert [game["game_id"] for game in payload["games"]] == [
        f"g-{index:04d}" for index in range(GAMES)
    ]
    assert sum(1 for game in payload["games"] if game["outcome"] is not None) == REPLICATES
    for game in payload["games"]:
        assert game["design"]["replicates"] == REPLICATES
        assert 0 <= game["design"]["replicate"] < REPLICATES
        assert 0 <= game["design"]["rotation"] < PLAYERS
        assert [seat["seat"] for seat in game["seats"]] == list(range(PLAYERS))

    # Per seat: seat 0 is where every failing rotation fails; the other seats' completed games
    # are still counted, which is what makes a seat row an account rather than a failure list.
    per_seat = {row["seat"]: row for row in payload["per_seat"]}
    assert set(per_seat) == set(range(PLAYERS))
    assert per_seat[0]["games"] == GAMES
    assert per_seat[0]["completed"] == REPLICATES
    assert per_seat[0]["abandoned"] == GAMES - REPLICATES
    assert per_seat[0]["wins"] == REPLICATES
    for seat in range(1, PLAYERS):
        assert per_seat[seat]["games"] == REPLICATES
        assert per_seat[seat]["losses"] == REPLICATES

    # Per model: each failing model is abandoned exactly ten times and charged no win.
    per_model = {row["model"]: row for row in payload["per_model"]}
    assert set(per_model) == {f"mock-{behaviour}" for behaviour in BEHAVIOURS}
    assert per_model["mock-correct-play"]["wins"] == REPLICATES
    assert per_model["mock-correct-play"]["abandoned"] == 0
    for behaviour in BEHAVIOURS[1:]:
        row = per_model[f"mock-{behaviour}"]
        assert row["games"] == REPLICATES * 2
        assert row["completed"] == REPLICATES
        assert row["abandoned"] == REPLICATES
        assert row["losses"] == REPLICATES

    # Every record terminates, and every one verifies with the v1 command's own engine.
    plugin = get_game("campaign")
    for game in payload["games"]:
        log = GameLogReader(god_log_path(root / str(game["game_id"]), str(game["game_id"]))).read()
        report = verify(log, plugin)
        assert report.completed is game["completed"]
        # The report counts every record; results.json counts the accepted ones and the refusals
        # by code, which is the same account told twice.
        assert report.rejections == sum(game["rejections_by_code"].values())
        assert report.actions == game["actions"] + report.rejections
        if not game["completed"]:
            assert log.terminal is None, "an abandoned game never gets a synthetic verdict"


def test_the_campaign_results_are_readable_by_inspect_run(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The campaign's artefact is the operator's artefact: the same command reads it."""
    config = _config(tmp_path)
    root = tmp_path / "run"
    assert main(["run", "--config", str(config), "--out", str(root), "--concurrency", "4"]) == 0
    capsys.readouterr()

    assert main(["inspect-run", str(root), "--game", "g-0000", "--seat", "0"]) == 0
    transcript, _err = capsys.readouterr()
    assert "The campaign game: every seat marks once." in transcript
    assert '"name":"close"' in transcript
    assert "d0001" in transcript
