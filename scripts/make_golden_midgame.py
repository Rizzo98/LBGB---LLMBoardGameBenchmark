"""Record golden game 2: a seven, a forced discard and a steal (kanban card K-029).

Golden game 1 pins the opening draft. This one pins what happens a few turns later, when the
dice, the bank and the robber have all started moving resources around: the same seed, played
on, until a seven has forced somebody to return half their hand and has taken a card off
somebody else. The draft is the same sixteen actions, so the first sixteen records of this log
are game 1's - a second, free check that nothing in the opening moved.

The game is *played*, not hand-written: every action comes from the game's own legal actions, so
the fixture cannot drift from the rules it is supposed to pin. Run it again only when a rule
change is intended, and read the diff first (ARCHITECTURE.md section 15.3).

    uv run python scripts/make_golden_midgame.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.run import GameRun
from lgbg.core.types import Action, JsonValue
from lgbg.games.catan.rules.robber import destinations, robber_victims
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState, Phase

SEED: Final[int] = 20250701
BOARD: Final[str] = "fixed:standard_a"
PLAYERS: Final[int] = 4
GAME_ID: Final[str] = "g-0002"
SETUP_STEPS: Final[int] = 8
PROTOCOL: Final[str] = "decline_only"
MAX_ACTIONS: Final[int] = 4000
NOTHING: Final[tuple[int, ...]] = (0,) * len(RESOURCE_ORDER)

SCRIPT_PATH: Final[Path] = Path("tests/fixtures/catan/seven_game.json")
GOLDEN_PATH: Final[Path] = Path("tests/golden/catan/seven_game.god.jsonl")


def main() -> int:
    game = get_game("catan")
    config = RunConfig(
        seed=SEED,
        players=PLAYERS,
        interaction_protocol=PROTOCOL,
        game_config=GameConfig({"board": BOARD}),
    )
    actions, seen = _play(game, config)
    _write_script(actions)
    _write_record(game, config, actions)
    print(f"wrote {SCRIPT_PATH} and {GOLDEN_PATH}")
    discards = seen["discarded"]
    steals = seen["robber_stole"]
    print(f"{len(actions)} actions, {discards} discard(s), {steals} steal(s)")
    return 0


def _play(game: Any, config: RunConfig) -> tuple[list[dict[str, JsonValue]], dict[str, int]]:
    """Draft, then play on until a seven has forced a discard and taken a card."""
    run = GameRun(game, config, game_id=GAME_ID)
    recorded: list[dict[str, JsonValue]] = []
    seen: dict[str, int] = {"discarded": 0, "robber_stole": 0}
    for _ in range(SETUP_STEPS * 2):
        _take(game, run, recorded, seen)
    for _ in range(MAX_ACTIONS):
        if seen["discarded"] and seen["robber_stole"]:
            break
        _take(game, run, recorded, seen)
    if not (seen["discarded"] and seen["robber_stole"]):
        raise SystemExit(f"the game never forced a discard and a steal: {seen}")
    return recorded, seen


def _take(
    game: Any, run: GameRun, recorded: list[dict[str, JsonValue]], seen: dict[str, int]
) -> None:
    """Make the next move: whatever it is, taken from the game's own legal actions."""
    action = _next_action(game, run)
    result = run.submit(action)
    if not isinstance(result, Applied):
        raise SystemExit(f"a legal action was refused: {result.rejection.message}")
    recorded.append({"player": action.player, "type": action.type, "params": dict(action.params)})
    for event in result.events:
        if event.type in seen:
            seen[event.type] += 1


def _next_action(game: Any, run: GameRun) -> Any:
    """What to do in this phase: draft, roll, discard, resolve the robber, or end the turn."""
    state = run.state
    if state.phase in (Phase.SETUP_ROUND_1, Phase.SETUP_ROUND_2, Phase.DISCARD):
        request = run.pending[0]
        legal = game.legal_actions(state, request.player)
        if not legal:
            raise SystemExit(f"seat {request.player} has no legal answer to {request.kind}")
        return legal[0]
    if state.phase is Phase.TURN_PRODUCTION:
        return Action(player=state.turn, type="roll_dice", params={})
    if state.phase is Phase.ROBBER:
        return _robber_action(state, run.pending[0].kind)
    return Action(player=state.turn, type="end_turn", params={})


def _robber_action(state: CatanState, kind: str) -> Action:
    """Move the robber next to somebody holding cards, and rob whoever holds the most."""
    if kind == "move_robber":
        legal = list(destinations(state))
        holding = [
            hex_id
            for hex_id in legal
            if any(
                state.hands[seat] != NOTHING
                for seat in robber_victims(replace(state, robber=hex_id))
            )
        ]

        return Action(player=state.turn, type="move_robber", params={"hex": (holding or legal)[0]})
    candidates = list(robber_victims(state))
    holding = [seat for seat in candidates if state.hands[seat] != NOTHING]
    victim = max(holding or candidates, key=lambda seat: sum(state.hands[seat]))
    return Action(player=state.turn, type="choose_robber_victim", params={"victim": victim})


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

    The sidecar is deliberately left behind: it holds the wall clock and the host, and the point
    of the split is that nothing like that can reach the record (ARCHITECTURE.md 8.2).
    """
    with tempfile.TemporaryDirectory() as scratch:
        run = GameRun(game, config, game_id=GAME_ID, directory=Path(scratch))
        for entry in actions:
            result = run.submit(
                Action(
                    player=_as_int(entry["player"]),
                    type=str(entry["type"]),
                    params=_as_mapping(entry["params"]),
                )
            )
            if not isinstance(result, Applied):
                raise SystemExit(f"the script was refused: {result.rejection.message}")
        run.finish()
        produced = Path(scratch) / "games" / f"{GAME_ID}.god.jsonl"
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, GOLDEN_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
