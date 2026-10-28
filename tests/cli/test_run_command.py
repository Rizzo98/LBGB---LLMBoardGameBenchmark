"""The operator's commands for a model run: run and inspect-run (PRD-v2 FR-14.2, PRD-v2 FR-14.3).

A run is declared in a file, played unattended, and then read back from its directory alone. The
test drives the command line exactly as an operator does, and then reads the artefacts as a
reviewer would: results.json for the account, the sidecar for the exact conversation.

The game is the suite's concurrent asset: four seats mark once, so a mock provider can play a
complete game without the test knowing any rules.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pytest

import tests.games.concurrent_game  # noqa: F401 - importing registers the game
from lgbg.adapters.cli.main import main
from lgbg.core.contracts import validate_results

SEED: Final[int] = 7
RUN_ID: Final[str] = "r-cli"
MODEL: Final[str] = "mock-model"


def _prompt(tmp_path: Path) -> Path:
    path = tmp_path / "game.md"
    path.write_text("The concurrent game: every seat marks once.\n", encoding="utf-8")
    return path


def _config(
    tmp_path: Path,
    *,
    seats: list[dict[str, Any]] | None = None,
    design: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    chosen = design or {"seating": "fixed", "initial_configuration": "fixed", "replicates": 1}
    replicates = int(chosen.get("replicates", 1))
    table = (
        seats
        if seats is not None
        else [
            {
                "seat": seat,
                "agent": "llm",
                "model": MODEL,
                "provider": "mock",
                "behaviour": "correct-play",
                # The mock is scripted per call and the table is reused across games, so a
                # correct-play seat needs one action for every game the design declares.
                "actions": [{"type": "mark", "params": {}} for _ in range(replicates)],
            }
            for seat in range(4)
        ]
    )
    payload: dict[str, Any] = {
        "game": "concurrent",
        "config": {"seed": SEED, "players": 4, "interaction_protocol": "concurrent"},
        "seats": table,
        "design": chosen,
        "prompts": {"game": str(_prompt(tmp_path))},
    }
    payload.update(extra or {})
    path = tmp_path / "run.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(tmp_path: Path, config: Path, *, concurrency: int = 1) -> Path:
    out = tmp_path / "run"
    code = main(
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(out),
            "--run-id",
            RUN_ID,
            "--concurrency",
            str(concurrency),
        ]
    )
    assert code == 0
    return out


def _results(root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((root / "results.json").read_text(encoding="utf-8"))
    assert validate_results(payload) == []
    return payload


def test_run_plays_a_config_file_and_writes_a_verifiable_run(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """PRD-v2 FR-14.2: a declared run, played unattended, lands on disk as a run directory."""
    config = _config(tmp_path)

    code = main(
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(tmp_path / "run"),
            "--run-id",
            RUN_ID,
        ]
    )

    out, err = capsys.readouterr()
    assert code == 0, err + out
    root = tmp_path / "run"
    payload = _results(root)
    assert payload["run_id"] == RUN_ID
    assert payload["summary"]["games"] == 1
    assert payload["summary"]["completed"] == 1
    assert payload["games"][0]["game_id"] == "g-0000"
    assert payload["games"][0]["actions"] == 4
    assert payload["per_seat"], "per-seat accounting is in the same artefact"
    assert "results.json" in out

    # PRD-v2 FR-14.6: a v2 record verifies with the command that verifies a v1 one.
    assert main(["verify", str(root)]) == 0


def test_run_makes_a_concurrent_run_out_of_one_config(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Bounded concurrency is an operator choice, and the record is the same either way."""
    config = _config(
        tmp_path,
        design={"seating": "fixed", "initial_configuration": "fixed", "replicates": 4},
    )

    code = main(
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(tmp_path / "run"),
            "--run-id",
            RUN_ID,
            "--concurrency",
            "3",
        ]
    )

    out, err = capsys.readouterr()
    assert code == 0, err + out
    payload = _results(tmp_path / "run")
    assert payload["summary"]["games"] == 4
    assert payload["summary"]["completed"] == 4
    assert [game["game_id"] for game in payload["games"]] == [
        "g-0000",
        "g-0001",
        "g-0002",
        "g-0003",
    ]


def test_inspect_run_lists_the_games_and_summarises_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """PRD-v2 FR-14.3: the run directory can be read without rerunning anything."""
    root = _run(
        tmp_path,
        _config(
            tmp_path,
            design={"seating": "fixed", "initial_configuration": "fixed", "replicates": 2},
        ),
    )
    capsys.readouterr()

    assert main(["inspect-run", str(root)]) == 0
    listed, _err = capsys.readouterr()
    assert "g-0000" in listed
    assert "g-0001" in listed
    assert "completed" in listed

    assert main(["inspect-run", str(root), "--game", "g-0001"]) == 0
    summary, _err = capsys.readouterr()
    assert "g-0001" in summary
    assert "outcome" in summary
    assert "seat 0" in summary


def test_inspect_run_shows_the_exact_messages_and_responses_of_one_seat(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """PRD-v2 FR-14.3: the decision turns of one seat, with what the model saw and what it said."""
    root = _run(tmp_path, _config(tmp_path))
    capsys.readouterr()

    code = main(["inspect-run", str(root), "--game", "g-0000", "--seat", "0"])

    out, err = capsys.readouterr()
    assert code == 0, err
    assert "The concurrent game: every seat marks once." in out, "the exact prompt bytes"
    assert "messages:" in out
    assert "response:" in out
    assert '"name":"mark"' in out, "the exact tool call it answered with"
    assert '"prompt_tokens"' in out or "prompt_tokens" in out
    assert "d0001" in out or "d.0" in out


def test_inspect_run_needs_a_game_to_show_a_seat(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A seat's turns belong to one game, so asking for them without one is an error."""
    root = _run(tmp_path, _config(tmp_path))
    capsys.readouterr()

    code = main(["inspect-run", str(root), "--seat", "0"])

    _out, err = capsys.readouterr()
    assert code == 1
    assert "--game" in err
    assert "Traceback" not in err


def test_inspect_run_refuses_a_directory_that_is_not_a_run(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = main(["inspect-run", str(tmp_path)])

    _out, err = capsys.readouterr()
    assert code == 1
    assert "results.json" in err
    assert "Traceback" not in err


def test_run_fails_legibly_when_the_config_is_missing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = main(["run", "--config", str(tmp_path / "nope.json"), "--out", str(tmp_path / "run")])

    _out, err = capsys.readouterr()
    assert code == 1
    assert "nope.json" in err
    assert "Traceback" not in err


def test_run_fails_legibly_when_a_seat_has_no_agent(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A table that does not cover the configuration is a configuration error, not a crash."""
    config = _config(
        tmp_path,
        seats=[
            {
                "seat": 0,
                "agent": "llm",
                "model": MODEL,
                "provider": "mock",
                "behaviour": "correct-play",
                "actions": [{"type": "mark", "params": {}}],
            }
        ],
    )

    code = main(["run", "--config", str(config), "--out", str(tmp_path / "run")])

    _out, err = capsys.readouterr()
    assert code == 1
    assert "seat" in err
    assert "Traceback" not in err


def test_run_fails_legibly_on_an_unknown_provider(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config = _config(
        tmp_path,
        seats=[
            {
                "seat": seat,
                "agent": "llm",
                "model": MODEL,
                "provider": "no-such-provider",
            }
            for seat in range(4)
        ],
    )

    code = main(["run", "--config", str(config), "--out", str(tmp_path / "run")])

    _out, err = capsys.readouterr()
    assert code == 1
    assert "no-such-provider" in err
    assert "Traceback" not in err
