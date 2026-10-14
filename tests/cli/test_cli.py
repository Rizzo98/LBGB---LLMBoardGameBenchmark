"""The CLI, run the way an operator runs it (PRD-v1 FR-20.1 to FR-20.4, FR-20.7).

Two things are asserted here beyond "the command works". First, that a failure is legible:
an operator diagnosing a benchmark run from a Python traceback is an operator who cannot
diagnose it at all, so an expected failure must print a message and exit non-zero (FR-20.7).
Second, that a rejected action does not destroy the record: the run still ends with a
terminal line, because the record of a failed run is exactly what one needs afterwards.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Final

import pytest

from lgbg.adapters.cli.main import main
from lgbg.core.config import RunConfig
from lgbg.core.game import Applied
from lgbg.core.log import GameLogReader, god_log_path, sidecar_path
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from tests.games.fixture_game import FixtureGame

SEED: Final[int] = 90210
PROTOCOL: Final[str] = "decline_only"


@pytest.fixture(autouse=True)
def _register_the_fixture_game() -> None:
    """The CLI discovers games by importing them, so a test of the CLI must do the same."""
    importlib.import_module("tests.games.fixture_game")


def _script(tmp_path: Path, actions: list[dict[str, Any]], *, name: str = "game.json") -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "game": "fixture",
                "config": {
                    "seed": SEED,
                    "interaction_protocol": PROTOCOL,
                    "players": 2,
                },
                "actions": actions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _winning_script(tmp_path: Path) -> Path:
    """Record a winning line by playing it, then commit the line as a script.

    Hand-writing a legal sequence is how a fixture becomes a maintenance burden; the game
    knows its own rules, so it is asked instead.
    """
    game = FixtureGame()
    run = GameRun(
        game, RunConfig(seed=SEED, players=2, interaction_protocol=PROTOCOL), game_id="g-x"
    )
    steps: list[dict[str, Any]] = []
    for _ in range(200):
        if game.is_terminal(run.state):
            break
        player = run.pending[0].player
        type_ = "spend" if run.state.tokens[player] >= 4 else "take"
        result = run.submit(Action(player=player, type=type_, params={}))
        assert isinstance(result, Applied), result
        steps.append({"player": player, "type": type_})
    assert steps, "the fixture must be winnable"
    run.close()
    return _script(tmp_path, steps)


def _script_for(
    tmp_path: Path,
    game: str,
    actions: list[dict[str, Any]],
    *,
    players: int = 2,
    extra_config: dict[str, Any] | None = None,
) -> Path:
    """A scripted file for any registered game, so a test can pick the one it needs."""
    path = tmp_path / f"{game}.json"
    config: dict[str, Any] = {
        "seed": SEED,
        "players": players,
        "interaction_protocol": PROTOCOL,
    }
    config.update(extra_config or {})
    path.write_text(
        json.dumps({"game": game, "config": config, "actions": actions}, indent=2),
        encoding="utf-8",
    )
    return path


def _catan_script(tmp_path: Path) -> Path:
    """A two-action Catan draft: enough for a real board to render through the CLI."""
    from lgbg.games.catan.board.topology import standard_topology

    edge = standard_topology().edges_at(4)[0]
    return _script_for(
        tmp_path,
        "catan",
        [
            {"player": 0, "type": "place_settlement", "params": {"vertex": 4}},
            {"player": 0, "type": "place_road", "params": {"edge": edge}},
        ],
        players=4,
        extra_config={"board": "fixed:standard_a"},
    )


def _capsys_text(captured: pytest.CaptureFixture[str]) -> tuple[str, str]:
    """Everything printed since the last read, and clear the buffer."""
    result = captured.readouterr()
    return result.out, result.err


def test_new_prints_the_opening_decision(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = main(["new", "--game", "fixture", "--players", "2", "--seed", str(SEED)])

    out, err = _capsys_text(capsys)
    assert code == 0, err
    assert "fixture" in out
    assert "player 0" in out
    assert "turn" in out


def test_new_accepts_a_game_option_as_a_flag(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["new", "--game", "fixture", "--players", "2", "--unused", "7"])

    out, _err = _capsys_text(capsys)
    assert code == 0
    assert "fixture" in out


def test_an_out_of_tree_plugin_can_be_imported_by_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A game that does not ship with the engine is reachable by importing its module."""
    code = main(
        [
            "new",
            "--game",
            "imported",
            "--players",
            "2",
            "--plugin",
            "tests.cli.plugin_for_import",
        ]
    )

    out, err = _capsys_text(capsys)
    assert code == 0, err
    assert "imported" in out


def test_an_unknown_game_fails_legibly(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["new", "--game", "no_such_game", "--players", "2"])

    out, err = _capsys_text(capsys)
    assert code == 1
    assert "error:" in err
    assert "no_such_game" in err
    assert "Traceback" not in err + out


def test_a_misspelled_config_value_fails_legibly(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["new", "--game", "fixture", "--players", "2", "--assist", "L9"])

    _out, err = _capsys_text(capsys)
    assert code == 1
    assert "L9" in err
    assert "Traceback" not in err


def test_play_writes_a_record_that_verifies(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _winning_script(tmp_path)
    out_dir = tmp_path / "run"

    code = main(["play", "--script", str(script), "--out", str(out_dir)])

    out, err = _capsys_text(capsys)
    assert code == 0, err + out
    assert god_log_path(out_dir, "g-0001").exists()
    assert sidecar_path(out_dir, "g-0001").exists()
    assert main(["verify", str(out_dir)]) == 0


def test_play_stops_at_the_first_rejection_and_keeps_the_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _script(
        tmp_path,
        [
            {"player": 0, "type": "take"},
            {"player": 1, "type": "spend"},
            {"player": 0, "type": "take"},
        ],
    )
    out_dir = tmp_path / "run"

    code = main(["play", "--script", str(script), "--out", str(out_dir)])

    _out, err = _capsys_text(capsys)
    assert code == 1
    assert "TOKENS_UNAVAILABLE" in err
    assert "Traceback" not in err
    log = GameLogReader(god_log_path(out_dir, "g-0001")).read()
    assert len(log.actions) == 2
    assert log.terminal is not None


def test_allow_rejections_keeps_playing(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    script = _script(
        tmp_path,
        [
            {"player": 0, "type": "take"},
            {"player": 1, "type": "spend"},
            {"player": 0, "type": "take"},
        ],
    )
    out_dir = tmp_path / "run"

    code = main(["play", "--script", str(script), "--out", str(out_dir), "--allow-rejections"])

    out, err = _capsys_text(capsys)
    assert code == 0, err
    assert "rejection" in out
    assert len(GameLogReader(god_log_path(out_dir, "g-0001")).read().actions) == 3


def test_play_uses_the_sole_open_request_when_none_is_named(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _script(tmp_path, [{"player": 0, "type": "gamble"}, {"player": 1, "type": "gamble"}])
    out_dir = tmp_path / "run"

    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0

    actions = GameLogReader(god_log_path(out_dir, "g-0001")).read().actions
    assert [record.request_id for record in actions] == ["d0", "d1"]


def test_play_fails_legibly_on_a_malformed_script(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "broken.json"
    path.write_text(
        json.dumps(
            {
                "game": "fixture",
                "config": {"seed": SEED, "players": 2, "interaction_protocol": PROTOCOL},
                "actions": [{"type": "take"}],
            }
        ),
        encoding="utf-8",
    )

    code = main(["play", "--script", str(path), "--out", str(tmp_path / "run")])

    _out, err = _capsys_text(capsys)
    assert code == 1
    assert "player" in err
    assert "Traceback" not in err


def test_play_fails_legibly_on_a_missing_script(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = main(["play", "--script", str(tmp_path / "nope.json"), "--out", str(tmp_path / "run")])

    _out, err = _capsys_text(capsys)
    assert code == 1
    assert "nope.json" in err
    assert "Traceback" not in err


def test_replay_reports_every_action(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    script = _script(tmp_path, [{"player": 0, "type": "take"}, {"player": 1, "type": "take"}])
    out_dir = tmp_path / "run"
    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0
    capsys.readouterr()

    code = main(["replay", str(god_log_path(out_dir, "g-0001"))])

    out, err = _capsys_text(capsys)
    assert code == 0, err
    assert "seq 0" in out
    assert "seq 1" in out
    assert "verified" in out


def test_replay_renders_states_with_the_games_own_notation(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """FR-19.4 and ARCHITECTURE.md 11.3: one renderer, used by the CLI and later by prompts."""
    script = _catan_script(tmp_path)
    out_dir = tmp_path / "run"
    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0
    capsys.readouterr()

    assert main(["replay", str(god_log_path(out_dir, "g-0001")), "--print-states"]) == 0

    out, _err = _capsys_text(capsys)
    assert "catan |" in out, "the game's notation names the game"
    assert "board:" in out, "and lays the board out as a board"


def test_replay_can_render_compactly(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    script = _catan_script(tmp_path)
    out_dir = tmp_path / "run"
    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0
    capsys.readouterr()
    log = str(god_log_path(out_dir, "g-0001"))

    assert main(["replay", log, "--print-states"]) == 0
    full, _ = _capsys_text(capsys)
    assert main(["replay", log, "--print-states", "--compact"]) == 0
    compact, _ = _capsys_text(capsys)

    assert compact.count("\n") < full.count("\n")
    assert len(compact) < len(full)
    assert "catan |" in compact


def test_replay_can_print_every_intermediate_state(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _script(tmp_path, [{"player": 0, "type": "gamble"}])
    out_dir = tmp_path / "run"
    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0
    capsys.readouterr()

    code = main(["replay", str(god_log_path(out_dir, "g-0001")), "--print-states"])

    out, _err = _capsys_text(capsys)
    assert code == 0
    assert "initial state:" in out
    assert "state after seq 0" in out
    assert out.count("state after seq") == 1


def test_replay_fails_legibly_on_a_tampered_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _script(tmp_path, [{"player": 0, "type": "take"}, {"player": 1, "type": "take"}])
    out_dir = tmp_path / "run"
    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0
    path = god_log_path(out_dir, "g-0001")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[2]["state_hash"] = "deadbeefdeadbeef"
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records)
        + "\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    code = main(["replay", str(path)])

    out, err = _capsys_text(capsys)
    assert code == 1
    assert "seq 1" in err
    assert "Traceback" not in err + out


def test_verify_accepts_a_directory_of_records(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _script(tmp_path, [{"player": 0, "type": "take"}])
    out_dir = tmp_path / "run"
    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0
    capsys.readouterr()

    code = main(["verify", str(out_dir)])

    out, err = _capsys_text(capsys)
    assert code == 0, err
    assert "ok" in out


def test_verify_fails_and_names_the_seq_on_a_tampered_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _script(tmp_path, [{"player": 0, "type": "take"}, {"player": 1, "type": "take"}])
    out_dir = tmp_path / "run"
    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0
    path = god_log_path(out_dir, "g-0001")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[1]["state_hash"] = "deadbeefdeadbeef"
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records)
        + "\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    code = main(["verify", str(path)])

    _out, err = _capsys_text(capsys)
    assert code == 1
    assert "seq 0" in err


def test_verify_fails_legibly_on_a_path_that_does_not_exist(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = main(["verify", str(tmp_path / "nothing-here")])

    _out, err = _capsys_text(capsys)
    assert code == 1
    assert "nothing-here" in err
    assert "Traceback" not in err


def test_an_unknown_command_is_an_argparse_error() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["fly"])

    assert raised.value.code == 2


def test_an_empty_script_still_produces_a_verifiable_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = _script(tmp_path, [])
    out_dir = tmp_path / "run"

    assert main(["play", "--script", str(script), "--out", str(out_dir)]) == 0

    log = GameLogReader(god_log_path(out_dir, "g-0001")).read()
    assert log.actions == []
    assert log.terminal is not None
    assert main(["verify", str(out_dir)]) == 0
