"""Record golden game 4: a win that comes from a development card (kanban card K-048).

The first three fixtures never buy a development card. This one plays the whole base game with
the deck in it: cards are bought when they can be afforded, knights are played, the progress
cards are used, and the winner's tenth point is required to come from a card *effect* rather
than from a build - which is the point of the fixture, and is asserted rather than hoped for.

The game is played by a policy written down here. Probe a few seeds with

    uv run python scripts/make_golden_devcards.py --probe 6

which prints, for each candidate, whether the win was card-driven before committing anything.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections import Counter
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
from lgbg.games.catan.rules.victory import victory_points
from lgbg.games.catan.state import (
    CARD_ORDER,
    RESOURCE_ORDER,
    CatanState,
    DevCard,
    Phase,
)

BASE_SEED: Final[int] = 20260211
BOARD: Final[str] = "fixed:standard_a"
PLAYERS: Final[int] = 4
GAME_ID: Final[str] = "g-0004"
SETUP_STEPS: Final[int] = 8
PROTOCOL: Final[str] = "decline_only"
MAX_ACTIONS: Final[int] = 12000
NOTHING: Final[tuple[int, ...]] = (0,) * len(RESOURCE_ORDER)
KNIGHT: Final[int] = CARD_ORDER.index(DevCard.KNIGHT)
VP: Final[int] = CARD_ORDER.index(DevCard.VICTORY_POINT)
SLOT: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}
PIPS: Final[dict[int, int]] = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}

SCRIPT_PATH: Final[Path] = Path("tests/fixtures/catan/devcard_game.json")
GOLDEN_PATH: Final[Path] = Path("tests/golden/catan/devcard_game.god.jsonl")


def config_for(seed: int) -> RunConfig:
    return RunConfig(
        seed=seed,
        players=PLAYERS,
        interaction_protocol=PROTOCOL,
        game_config=GameConfig({"board": BOARD}),
    )


def play(seed: int, *, directory: Path | None = None, limit: int = MAX_ACTIONS) -> tuple[Any, Any]:
    """Play one game; returns the run (finished only when a directory is given) and the counts."""
    game = get_game("catan")
    run = GameRun(game, config_for(seed), game_id=GAME_ID, directory=directory)
    seen: Counter[str] = Counter()
    recorded: list[dict[str, JsonValue]] = []
    for _ in range(SETUP_STEPS * 2):
        _take(game, run, recorded, seen)
    for _ in range(limit):
        if game.is_terminal(run.state):
            break
        _take(game, run, recorded, seen)
    else:
        raise SystemExit(f"seed {seed}: no winner within {limit} actions")
    return (run, recorded, seen) if directory is not None else (run.state, seen)


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
    """Cards first when they help, then points, then connectivity, then the roll or the end."""
    state = run.state
    if state.phase in (Phase.SETUP_ROUND_1, Phase.SETUP_ROUND_2):
        request = run.pending[0]
        legal = game.legal_actions(state, request.player)
        if request.kind == phases.PLACE_SETTLEMENT:
            return max(legal, key=lambda action: (_pips(state, action), -_vertex_of(action)))
        return legal[0]
    if state.phase in (Phase.DISCARD, Phase.ROAD_BUILDING):
        request = run.pending[0]
        return game.legal_actions(state, request.player)[0]
    if state.phase is Phase.ROBBER:
        return _robber_action(state, run.pending[0].kind)
    if state.phase in (Phase.TURN_PRODUCTION, Phase.ACTION):
        offered = game.legal_actions(state, state.turn)
        play = [action for action in offered if action.type == phases.PLAY_DEV_CARD]
        if play:
            return _best_card(state, play)
        if state.phase is Phase.TURN_PRODUCTION:
            return Action(player=state.turn, type=phases.ROLL_DICE, params={})
        hand = state.hands[state.turn]
        for name in (phases.BUILD_CITY, phases.BUILD_SETTLEMENT, phases.BUY_DEV_CARD):
            for action in offered:
                if action.type == name:
                    return action
        if hand[SLOT["brick"]] >= 2 and hand[SLOT["wood"]] >= 2:
            for action in offered:
                if action.type == phases.BUILD_ROAD:
                    return action
        for action in offered:
            if action.type == phases.END_TURN:
                return action
    raise SystemExit(f"no policy for phase {state.phase.value}")


def _best_card(state: CatanState, play: list[Action]) -> Action:
    """Which card to play: a knight if there is one, otherwise whichever progress card is left."""
    for action in play:
        if action.params.get("card") == DevCard.KNIGHT.value:
            return action
    # The progress cards are chosen from what the engine offers, so the choice is one the rules
    # already accept - the bank limits what a Year of Plenty may take, and the offer knows it.
    for card in (DevCard.YEAR_OF_PLENTY, DevCard.MONOPOLY):
        choices = [action for action in play if action.params.get("card") == card.value]
        if not choices:
            continue
        hand = state.hands[state.turn]
        return min(
            choices,
            key=lambda action: (
                sum(hand[SLOT[str(name)]] for name in _named(action)),
                [str(name) for name in _named(action)],
            ),
        )
    return play[0]


def _named(action: Action) -> list[JsonValue]:
    names = action.params.get("resources")
    return list(names) if isinstance(names, list) else []


def _robber_action(state: CatanState, kind: str) -> Action:
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


def _vertex_of(action: Action) -> int:
    value = action.params["vertex"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise SystemExit(f"expected a vertex in {action!r}")
    return value


def _pips(state: CatanState, action: Action) -> int:
    vertex = _vertex_of(action)
    return sum(
        PIPS.get(state.board.tokens[hex_id] or 0, 0)
        for hex_id in state.board.topology.hexes_at(vertex)
        if state.board.resource_of_hex(hex_id) is not None
    )


def probe(count: int) -> int:
    """Play a few seeds and report whether the win came from a card."""
    for offset in range(count):
        seed = BASE_SEED + offset
        state, seen = play(seed)
        winner = state.turn
        knights = state.knights_played[winner]
        cards = state.dev_cards[winner][VP]
        award = state.largest_army == winner
        print(
            f"seed {seed}: winner {winner} points {victory_points(state, winner)} "
            f"knights {knights} vp_cards {cards} army {award} "
            f"plays {seen['dev_card_played']} buys {seen['dev_card_bought']} "
            f"awards {seen['largest_army_awarded']} rounds {state.round}"
        )
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--probe":
        return probe(int(argv[1]) if len(argv) > 1 else 4)
    game = get_game("catan")
    with tempfile.TemporaryDirectory() as scratch:
        run, actions, seen = play(BASE_SEED, directory=Path(scratch))
        run.finish()
        produced = Path(scratch) / "games" / f"{GAME_ID}.god.jsonl"
        SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCRIPT_PATH.write_text(
            # newline="
": the fixture is compared as bytes, so it may not depend on Windows.
            json.dumps(
                {
                    "game": "catan",
                    "config": {
                        "seed": BASE_SEED,
                        "players": PLAYERS,
                        "interaction_protocol": PROTOCOL,
                        "board": BOARD,
                    },
                    "actions": actions,
                },
                indent=2,
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, GOLDEN_PATH)
    print(f"wrote {SCRIPT_PATH} and {GOLDEN_PATH}")
    print(f"{len(actions)} actions, winner {game.outcome(run.state).winner}")
    print("events: " + ", ".join(f"{name} {number}" for name, number in sorted(seen.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
