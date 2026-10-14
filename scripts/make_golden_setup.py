"""Record golden game 1: the opening draft, committed as a fixture (kanban card K-021).

A golden game is a regression net made of bytes. If any rule of slice 2 changes - the distance
rule, the snake order, the endowment, the phase machine, the encoding - the hashes in the
record change, the committed fixture stops matching, and the change cannot pass unnoticed.
ARCHITECTURE.md section 15.3 makes that consequence deliberate: a hash change means bumping the
plugin's `rules_version` and regenerating this file, with the diff read first.

The draft is played, not hand-written: the game is asked for its own legal actions, so the
fixture cannot drift from the rules it is supposed to pin. Run it again only when a rule change
is intended.

    uv run python scripts/make_golden_setup.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.core.run import GameRun
from lgbg.core.types import Action, JsonValue

SEED: Final[int] = 20250701
BOARD: Final[str] = "fixed:standard_a"
PLAYERS: Final[int] = 4
GAME_ID: Final[str] = "g-0001"
SETUP_STEPS: Final[int] = 8
PROTOCOL: Final[str] = "decline_only"

SCRIPT_PATH: Final[Path] = Path("tests/fixtures/catan/setup_game.json")
GOLDEN_PATH: Final[Path] = Path("tests/golden/catan/setup_game.god.jsonl")


def main() -> int:
    game = get_game("catan")
    config = RunConfig(
        seed=SEED,
        players=PLAYERS,
        interaction_protocol=PROTOCOL,
        game_config=GameConfig({"board": BOARD}),
    )
    actions = _draft(game, config)
    _write_script(actions)
    _write_record(game, config, actions)
    print(f"wrote {SCRIPT_PATH} and {GOLDEN_PATH}")
    print(f"{len(actions)} actions, {SETUP_STEPS} selections")
    return 0


def _draft(game: Any, config: RunConfig) -> list[dict[str, JsonValue]]:
    """Play a legal draft, asking the game for its own legal actions."""
    source = SeededRandomSource(config.seed)
    state = game.initial_state(config.game_config, source)
    recorded: list[dict[str, JsonValue]] = []
    for _ in range(SETUP_STEPS * 2):
        pending = game.pending_decisions(state)
        if not pending:
            break
        player = pending[0].player
        legal = game.legal_actions(state, player)
        if not legal:
            raise SystemExit(f"seat {player} has no legal action, which cannot happen in a draft")
        result = game.apply(state, legal[0], source)
        if not isinstance(result, Applied):
            raise SystemExit(f"a legal action was refused: {result.rejection.message}")
        state = result.state
        recorded.append({"player": player, "type": legal[0].type, "params": dict(legal[0].params)})
    if len(recorded) != SETUP_STEPS * 2:
        raise SystemExit(f"the draft made {len(recorded)} actions, expected {SETUP_STEPS * 2}")
    return recorded


def _write_script(actions: list[dict[str, JsonValue]]) -> None:
    SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "game": "catan",
        "config": {
            "seed": SEED,
            "players": PLAYERS,
            "interaction_protocol": PROTOCOL,
            "board": BOARD,
        },
        "actions": actions,
    }
    with SCRIPT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def _as_int(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SystemExit(f"expected an integer in the script, got {value!r}")
    return value


def _as_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise SystemExit(f"expected an object in the script, got {value!r}")
    return value


def _write_record(game: Any, config: RunConfig, actions: list[dict[str, JsonValue]]) -> None:
    """Play the script for real and commit the deterministic record, and nothing else.

    The sidecar is deliberately left behind: it holds the wall clock and the host, and the
    point of the split is that nothing like that can reach the record (ARCHITECTURE.md 8.2).
    """
    with tempfile.TemporaryDirectory() as scratch:
        run = GameRun(game, config, game_id=GAME_ID, directory=Path(scratch))
        for entry in actions:
            run.submit(
                Action(
                    player=_as_int(entry["player"]),
                    type=str(entry["type"]),
                    params=_as_mapping(entry["params"]),
                )
            )
        run.finish()
        produced = Path(scratch) / "games" / f"{GAME_ID}.god.jsonl"
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, GOLDEN_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
