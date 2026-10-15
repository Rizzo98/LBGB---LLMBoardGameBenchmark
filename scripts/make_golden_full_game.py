"""Record golden game 3: a game played to a win (kanban card K-038).

The first two fixtures stop where their slice stopped - after the draft, and after a seven has
been resolved. This one is a whole game: played from the opening position to the tenth victory
point, with every rule the earlier slices built taking part, and ending in the terminal record
the runtime writes when somebody wins.

The game is *played*, not written: every action comes from the game's own legal actions under a
fixed and deliberately simple policy, so the fixture cannot drift from the rules, and the policy
is written down here rather than hidden in a script. Run it again only when a rule change is
intended, and read the diff first (ARCHITECTURE.md section 15.3).

    uv run python scripts/make_golden_full_game.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.run import GameRun
from lgbg.core.types import Action, JsonValue
from lgbg.games.catan import phases
from lgbg.games.catan.rules.robber import destinations, robber_victims
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState, Phase

SEED: Final[int] = 20250717
BOARD: Final[str] = "fixed:standard_a"
PLAYERS: Final[int] = 4
GAME_ID: Final[str] = "g-0003"
SETUP_STEPS: Final[int] = 8
PROTOCOL: Final[str] = "decline_only"
MAX_ACTIONS: Final[int] = 8000
NOTHING: Final[tuple[int, ...]] = (0,) * len(RESOURCE_ORDER)
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}

PREFERENCE: Final[tuple[str, ...]] = (
    phases.BUILD_CITY,
    phases.BUILD_SETTLEMENT,
    phases.BUILD_ROAD,
    phases.END_TURN,
)
"""What the policy does when it may do anything: points first, then connectivity, then stop."""

PIPS: Final[dict[int, int]] = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
"""How often each number token produces, which is how the draft is chosen.

The draft is the one decision this policy makes on the merits. Taking the first legal vertex -
which is what every earlier fixture does, because it does not care where the pieces go - puts
all eight settlements on the same terrain, and a game in which everybody produces wool for ever
is a true game and a useless fixture. So the policy puts each settlement where it will produce
most often, and the tie is broken by the vertex identifier so the choice stays deterministic.
"""

SCRIPT_PATH: Final[Path] = Path("tests/fixtures/catan/full_game.json")
GOLDEN_PATH: Final[Path] = Path("tests/golden/catan/full_game.god.jsonl")


def main() -> int:
    game = get_game("catan")
    config = RunConfig(
        seed=SEED,
        players=PLAYERS,
        interaction_protocol=PROTOCOL,
        game_config=GameConfig({"board": BOARD}),
    )
    actions, seen, outcome = _play(game, config)
    _write_script(actions)
    _write_record(game, config, actions)
    print(f"wrote {SCRIPT_PATH} and {GOLDEN_PATH}")
    print(f"{len(actions)} actions, winner {outcome.winner}, rounds {outcome.rounds}")
    print("events: " + ", ".join(f"{name} {count}" for name, count in sorted(seen.items())))
    return 0


def _play(game: Any, config: RunConfig) -> tuple[list[dict[str, JsonValue]], Counter[str], Any]:
    """Play the draft and then every turn, until somebody has won."""
    run = GameRun(game, config, game_id=GAME_ID)
    recorded: list[dict[str, JsonValue]] = []
    seen: Counter[str] = Counter()
    for _ in range(SETUP_STEPS * 2):
        _take(game, run, recorded, seen)
    for _ in range(MAX_ACTIONS):
        if game.is_terminal(run.state):
            break
        _take(game, run, recorded, seen)
    else:
        raise SystemExit(f"no winner within {MAX_ACTIONS} actions")
    if not game.is_terminal(run.state):
        raise SystemExit("the game ended without a terminal state")
    return recorded, seen, game.outcome(run.state)


def _take(
    game: Any, run: GameRun, recorded: list[dict[str, JsonValue]], seen: Counter[str]
) -> None:
    action = _next_action(game, run)
    result = run.submit(action)
    if not isinstance(result, Applied):
        raise SystemExit(f"a legal action was refused: {result.rejection.message}")
    recorded.append({"player": action.player, "type": action.type, "params": dict(action.params)})
    for event in result.events:
        seen[event.type] += 1


def _next_action(game: Any, run: GameRun) -> Any:
    """What to do now: draft, roll, discard, resolve the robber, or play the action phase."""
    state = run.state
    if state.phase in (Phase.SETUP_ROUND_1, Phase.SETUP_ROUND_2):
        request = run.pending[0]
        legal = game.legal_actions(state, request.player)
        if not legal:
            raise SystemExit(f"seat {request.player} has no legal answer to {request.kind}")
        if request.kind == phases.PLACE_SETTLEMENT:
            return max(legal, key=lambda action: (_pips(state, action), -_vertex_of(action)))
        return legal[0]
    if state.phase is Phase.DISCARD:
        request = run.pending[0]
        legal = game.legal_actions(state, request.player)
        if not legal:
            raise SystemExit(f"seat {request.player} has no legal answer to {request.kind}")
        return legal[0]
    if state.phase is Phase.TURN_PRODUCTION:
        return Action(player=state.turn, type=phases.ROLL_DICE, params={})
    if state.phase is Phase.ROBBER:
        return _robber_action(state, run.pending[0].kind)
    if state.phase is Phase.ACTION:
        offered = game.legal_actions(state, state.turn)
        hand = state.hands[state.turn]
        # Roads are built for connectivity, but not at the price of the next settlement: the
        # policy keeps one brick and one wood in hand while it has them to spare.
        reserve = hand[SLOT["brick"]] >= 2 and hand[SLOT["wood"]] >= 2
        for name in PREFERENCE:
            if name == phases.BUILD_ROAD and not reserve:
                continue
            for action in offered:
                if action.type == name:
                    return action
        raise SystemExit("the action phase offers nothing this policy knows")
    raise SystemExit(f"no policy for phase {state.phase.value}")


def _vertex_of(action: Action) -> int:
    value = action.params["vertex"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise SystemExit(f"expected a vertex in {action!r}")
    return value


def _pips(state: CatanState, action: Action) -> int:
    """How often a settlement on this vertex would produce."""
    vertex = _vertex_of(action)
    return sum(
        PIPS.get(state.board.tokens[hex_id] or 0, 0)
        for hex_id in state.board.topology.hexes_at(vertex)
        if state.board.resource_of_hex(hex_id) is not None
    )


def _robber_action(state: CatanState, kind: str) -> Action:
    """Move the robber next to somebody holding cards, and rob whoever holds the most."""
    if kind == phases.MOVE_ROBBER:
        legal = list(destinations(state))
        holding = [
            hex_id
            for hex_id in legal
            if any(
                state.hands[seat] != NOTHING
                for seat in robber_victims(replace(state, robber=hex_id))
            )
        ]
        return Action(
            player=state.turn, type=phases.MOVE_ROBBER, params={"hex": (holding or legal)[0]}
        )
    candidates = list(robber_victims(state))
    holding = [seat for seat in candidates if state.hands[seat] != NOTHING]
    victim = max(holding or candidates, key=lambda seat: sum(state.hands[seat]))
    return Action(player=state.turn, type=phases.CHOOSE_ROBBER_VICTIM, params={"victim": victim})


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
    """Play the script for real and commit the deterministic record, and nothing else."""
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
