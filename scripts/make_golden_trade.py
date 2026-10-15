"""Record golden game 5: a trade between two players (kanban card K-053).

The four earlier fixtures never trade with each other: the bank is the only counterparty in the
base game as they play it. This one plays the whole game with the offer in it - a player who is
one card short of a build offers a spare for what they lack, the others answer, and the cards
move - and the fixture is required to contain a *completed* trade, which the test that reads it
asserts rather than hoping for it here.

The policy is written down rather than searched for, and it is driven by what the engine offers:
probe a few seeds with

    uv run python scripts/make_golden_trade.py --probe 6

which prints, for each candidate, how many offers were made, how many were taken, and how the
game ended, before anything is committed.
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
from lgbg.games.catan.state import RESOURCE_ORDER, RESPONSE_ACCEPT, CatanState, Phase

BASE_SEED: Final[int] = 20260415
BOARD: Final[str] = "fixed:standard_a"
PLAYERS: Final[int] = 4
GAME_ID: Final[str] = "g-0005"
SETUP_STEPS: Final[int] = 8
PROTOCOL: Final[str] = "decline_only"
MAX_ACTIONS: Final[int] = 12000
NOTHING: Final[tuple[int, ...]] = (0,) * len(RESOURCE_ORDER)
SLOT: Final[dict[str, int]] = {resource.value: i for i, resource in enumerate(RESOURCE_ORDER)}
PIPS: Final[dict[int, int]] = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}

SCRIPT_PATH: Final[Path] = Path("tests/fixtures/catan/trade_game.json")
GOLDEN_PATH: Final[Path] = Path("tests/golden/catan/trade_game.god.jsonl")


def config_for(seed: int) -> RunConfig:
    return RunConfig(
        seed=seed,
        players=PLAYERS,
        interaction_protocol=PROTOCOL,
        game_config=GameConfig({"board": BOARD}),
    )


def play(seed: int, *, directory: Path | None = None, limit: int = MAX_ACTIONS) -> Any:
    """Play one game; returns the run (finished only when a directory is given) and counts."""
    game = get_game("catan")
    run = GameRun(game, config_for(seed), game_id=GAME_ID, directory=directory)
    seen: Counter[str] = Counter()
    recorded: list[dict[str, JsonValue]] = []
    offered: set[tuple[int, int]] = set()
    for _ in range(SETUP_STEPS * 2):
        _take(game, run, recorded, seen, offered)
    for _ in range(limit):
        if game.is_terminal(run.state):
            break
        _take(game, run, recorded, seen, offered)
    else:
        raise SystemExit(f"seed {seed}: no winner within {limit} actions")
    return (run, recorded, seen) if directory is not None else (run.state, seen)


def _take(
    game: Any,
    run: GameRun,
    recorded: list[dict[str, JsonValue]],
    seen: Counter[str],
    offered: set[tuple[int, int]],
) -> None:
    action = _next_action(game, run, offered)
    result = run.submit(action)
    if not isinstance(result, Applied):
        raise SystemExit(f"a legal action was refused: {result.rejection.message}")
    recorded.append({"player": action.player, "type": action.type, "params": dict(action.params)})
    for event in result.events:
        seen[event.type] += 1


def _next_action(game: Any, run: GameRun, offered: set[tuple[int, int]]) -> Any:
    """Set up, answer, rob, build, and trade when a trade is what is missing."""
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
    if state.phase is Phase.TRADE_RESPONSE:
        return _trade_action(game, run)
    if state.phase in (Phase.TURN_PRODUCTION, Phase.ACTION):
        return _turn_action(game, state, offered)
    raise SystemExit(f"no policy for phase {state.phase.value}")


def _turn_action(game: Any, state: CatanState, offered: set[tuple[int, int]]) -> Any:
    turn = state.turn
    legal = game.legal_actions(state, turn)
    play = [action for action in legal if action.type == phases.PLAY_DEV_CARD]
    if play:
        return _best_card(state, play)
    if state.phase is Phase.TURN_PRODUCTION:
        return Action(player=turn, type=phases.ROLL_DICE, params={})
    for name in (phases.BUILD_CITY, phases.BUILD_SETTLEMENT, phases.BUY_DEV_CARD):
        for action in legal:
            if action.type == name:
                return action
    hand = state.hands[turn]
    if hand[SLOT["brick"]] >= 2 and hand[SLOT["wood"]] >= 2:
        for action in legal:
            if action.type == phases.BUILD_ROAD:
                return action
    # Nothing to build with what is in hand: this is where a table trades. One offer a turn is
    # enough, because an offer the whole table declines is over and would otherwise be made again.
    key = (state.round, turn)
    if key not in offered:
        wanted = _offer_for(state, turn)
        if wanted is not None:
            offered.add(key)
            return wanted
    for action in legal:
        if action.type == phases.END_TURN:
            return action
    raise SystemExit(f"no action for {state.phase.value} at seat {turn}")


def _offer_for(state: CatanState, turn: int) -> Action | None:
    """One card the player can spare, for one they hold none of that somebody holds two of.

    The offer is built from the state rather than taken from the enumeration, because what the
    driver wants is a trade somebody can take: the enumeration is every offer the rules accept,
    and most of them ask for cards no hand at the table could give.
    """
    hand = state.hands[turn]
    if sum(hand) < 3:
        return None
    spare = max(range(len(RESOURCE_ORDER)), key=lambda index: (hand[index], -index))
    if hand[spare] < 2:
        return None
    for want, resource in enumerate(RESOURCE_ORDER):
        if hand[want]:
            continue
        holders = [
            seat for seat in range(state.players) if seat != turn and state.hands[seat][want] >= 2
        ]
        if not holders:
            continue
        return Action(
            player=turn,
            type=phases.OFFER_TRADE,
            params={"give": {RESOURCE_ORDER[spare].value: 1}, "want": {resource.value: 1}},
        )
    return None


def _trade_action(game: Any, run: GameRun) -> Any:
    """Answer an offer if this seat was asked, otherwise settle the offer as its offerer.

    Answers are given before the offerer acts, so the offerer's request is the last one open only
    once the round is over - which is exactly when there is a choice among the acceptors to make.
    """
    state = run.state
    for request in run.pending:
        if request.kind == phases.RESPOND_TRADE:
            return _answer_for(game, state, request.player)
    acceptors = [seat for seat in range(state.players) if state.responses[seat] == RESPONSE_ACCEPT]
    if acceptors:
        return Action(
            player=state.turn,
            type=phases.CHOOSE_PARTNER,
            params={"partner": min(acceptors)},
        )
    return Action(player=state.turn, type=phases.CANCEL_TRADE, params={})


def _answer_for(game: Any, state: CatanState, seat: int) -> Any:
    """Accept a trade that is worth taking and paid for, decline anything else.

    A seat takes the offer when it can keep a card of the kind it would be giving away, and it
    declines when that card is its only one - which is what makes the fixture contain declines as
    well as accepts, and what makes some offers die at the table. What a seat *may* answer comes
    from the engine, so a responder who cannot pay for the offer at all is never told to accept:
    the offer of answers is already narrow for them.
    """
    answers = {
        action.params["response"]: action
        for action in game.legal_actions(state, seat)
        if action.type == phases.RESPOND_TRADE
    }
    offer = state.offer
    if offer is None or "accept" not in answers:
        return answers["decline"]
    asking = next(index for index in range(len(RESOURCE_ORDER)) if offer.want[index])
    if state.hands[seat][asking] >= 2:
        return answers["accept"]
    return answers["decline"]


def _best_card(state: CatanState, play: list[Action]) -> Action:
    """Which card to play: a knight if there is one, otherwise a progress card."""
    for action in play:
        if action.params.get("card") == "knight":
            return action
    for card in ("year_of_plenty", "monopoly"):
        choices = [action for action in play if action.params.get("card") == card]
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
    """Play a few seeds and report how much trading each one produced."""
    for offset in range(count):
        seed = BASE_SEED + offset
        state, seen = play(seed)
        print(
            f"seed {seed}: winner {state.turn} rounds {state.round} "
            f"offers {seen['trade_offered']} answers {seen['trade_responded']} "
            f"completed {seen['trade_completed']} closed {seen['trade_closed']}"
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
