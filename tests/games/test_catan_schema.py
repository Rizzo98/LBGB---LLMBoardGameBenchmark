"""The declared action surface, against everything the game produces (FR-18.1, FR-18.2, FR-18.5).

A schema that drifts from its implementation is worse than none: it is a contract the engine
advertises and does not keep. So the surface is checked from three directions at once - every
action in the committed corpus, every action a fuzzed game offers, and every action the runtime
refuses before rule logic sees it.

The corpus check is the one that found the first real drift: play_dev_card declared only its card
while the engine let Year of Plenty and Monopoly be told which resources to take, so eight recorded
actions were outside the declaration. The declared schema now says which card takes what, from the
same table the rule reads.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Final

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.errors import BAD_PARAMS
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.run import GameRun
from lgbg.core.schema import validate_action
from lgbg.core.types import Action, JsonValue
from lgbg.games.catan import phases

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
BOARD: Final[str] = "fixed:standard_a"
RECORDS: Final[tuple[str, ...]] = (
    "full_game",
    "devcard_game",
    "seven_game",
    "setup_game",
    "trade_game",
)
FUZZ_SEEDS: Final[tuple[int, ...]] = (20260601, 20260602, 20260603)
MAX_ACTIONS: Final[int] = 600


def _recorded(name: str) -> list[Action]:
    path = Path(__file__).resolve().parents[1] / "golden" / "catan" / f"{name}.god.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[1:]]
    return [
        Action(player=row["player"], type=row["action"]["type"], params=row["action"]["params"])
        for row in rows
        if row.get("t") == "action" and row.get("action") is not None
    ]


def test_every_action_in_the_committed_corpus_fits_the_declared_schema() -> None:
    """FR-18.5 against five recorded games: not one action outside the surface."""
    schema = GAME.action_schema()
    checked = 0
    outside: list[str] = []

    for name in RECORDS:
        for action in _recorded(name):
            checked += 1
            refusal = validate_action(schema, action)
            if refusal is not None:
                outside.append(f"{name} {action.type} {dict(action.params)}")

    assert checked > 1500, "the corpus is the evidence, so it has to be read"
    assert outside == [], f"actions outside the declared surface: {outside[:5]}"


def _fuzz(seed: int) -> tuple[int, list[str]]:
    """Play random legal actions; every action offered is checked before it is taken.

    This is the fuzz form of FR-18.5: not the actions somebody wrote down, but the ones the game
    produces when it is played without a plan.
    """
    schema = GAME.action_schema()
    chooser = random.Random(seed)
    config = RunConfig(
        seed=seed,
        players=PLAYERS,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": BOARD}),
    )
    run = GameRun(GAME, config, game_id="g-schema")
    checked = 0
    refused: list[str] = []

    for _ in range(MAX_ACTIONS):
        if GAME.is_terminal(run.state):
            break
        offered = [
            action
            for request in run.pending
            for action in GAME.legal_actions(run.state, request.player)
        ]
        for action in offered:
            checked += 1
            if validate_action(schema, action) is not None:
                refused.append(f"{action.type} {dict(action.params)}")
        result = run.submit(chooser.choice(offered))
        if not isinstance(result, Applied):
            refused.append(f"refused: {result.rejection.code.code}")
    return checked, refused


def test_every_action_a_fuzzed_game_offers_fits_the_declared_schema() -> None:
    """FR-18.5 as a fuzz run: the surface the game produces, not the one it was written with."""
    for seed in FUZZ_SEEDS:
        checked, refused = _fuzz(seed)
        assert checked > 200, f"seed {seed} hardly played"
        assert refused == [], f"seed {seed}: {refused[:5]}"


def test_a_schema_violation_never_reaches_rule_logic(monkeypatch: Any, tmp_path: Path) -> None:
    """FR-18.2: validation happens before the rule, not inside it."""
    from lgbg.games.catan import game as plugin

    called: list[str] = []
    original = plugin.ACTIONS[phases.BUILD_ROAD]

    def watched(state: Any, action: Any, rng: Any) -> Any:
        called.append(action.type)
        return original(state, action, rng)

    monkeypatch.setitem(plugin.ACTIONS, phases.BUILD_ROAD, watched)
    config = RunConfig(
        seed=20260601,
        players=PLAYERS,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": BOARD}),
    )
    run = GameRun(GAME, config, game_id="g-schema", directory=tmp_path)
    for _ in range(8):
        request = run.pending[0]
        run.submit(GAME.legal_actions(run.state, request.player)[0])
    seat = run.pending[0].player
    before = run.state

    refused = run.submit(Action(player=seat, type=phases.BUILD_ROAD, params={"edge": "north"}))

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == BAD_PARAMS
    assert called == [], "the rule ran on an action the schema refused"
    assert run.state == before


def test_the_cards_declare_exactly_the_parameters_they_take() -> None:
    """The drift this card found: a card that takes nothing may not be told anything."""
    schema = GAME.action_schema()

    def dev(**params: JsonValue) -> Action:
        return Action(player=0, type=phases.PLAY_DEV_CARD, params=dict(params))

    assert validate_action(schema, dev(card="knight")) is None
    stray = validate_action(schema, dev(card="knight", resources=["ore"]))
    assert stray is not None, "a knight takes no telling"
    assert stray.code == BAD_PARAMS

    assert validate_action(schema, dev(card="monopoly", resources=["ore"])) is None
    assert validate_action(schema, dev(card="year_of_plenty", resources=["ore", "ore"])) is None
    assert validate_action(schema, dev(card="monopoly", resources=["ore", "wood"])) is not None
    assert validate_action(schema, dev(card="year_of_plenty", resources=["ore"])) is not None
    assert (
        validate_action(schema, dev(card="year_of_plenty", resources=["gold", "ore"])) is not None
    )
