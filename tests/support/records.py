"""Recording a real game, and tampering with it.

Several suites need the same two things: a genuine record produced by the engine, and a way
to edit one on disk the way a corrupted or tampered record would arrive. Keeping both here
means the tamper suite and the replay suite cannot drift apart in how they build their input.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from lgbg.core.canonical import hash_state
from lgbg.core.config import RunConfig
from lgbg.core.game import Applied
from lgbg.core.log import (
    ActionRecord,
    GameLogWriter,
    HeaderRecord,
    TerminalRecord,
    god_log_path,
)
from lgbg.core.rng import SeededRandomSource
from lgbg.core.types import Action, JsonValue
from tests.games.fixture_game import FixtureGame

SEED: Final[int] = 4242
PROTOCOL: Final[str] = "decline_only"
GAME_ID: Final[str] = "g-0001"

Mutation = Callable[[list[dict[str, Any]]], None]


def record_fixture_game(
    directory: Path,
    *,
    actions: int = 6,
    with_rejection: bool = False,
    game_id: str = GAME_ID,
) -> Path:
    """Play the fixture game and write a real record: the input these suites replay."""
    game = FixtureGame()
    config = RunConfig(seed=SEED, players=2, interaction_protocol=PROTOCOL)
    source = SeededRandomSource(config.seed)
    state: Any = game.initial_state(config.game_config, source)
    path = god_log_path(directory, game_id)
    writer = GameLogWriter(path)
    writer.write_header(
        HeaderRecord(
            game_id=game_id,
            game=game.name,
            rules_version=game.rules_version,
            schema_version=game.schema_version,
            players=2,
            config=config.to_mapping(),
            prompt_hashes={},
            initial_state_hash=hash_state(state, game),
        )
    )
    previous = hash_state(state, game)
    seq = 0
    rejections = 0
    for index in range(actions):
        if game.is_terminal(state):
            break
        player = game.pending_decisions(state)[0].player
        refusing = with_rejection and index == 2
        action = Action(player=player, type="spend" if refusing else "gamble", params={})
        mark = len(source.draws())
        result = game.apply(state, action, source)
        if isinstance(result, Applied):
            state = result.state
            events = list(result.events)
            outcome: dict[str, JsonValue] = {"ok": True}
        else:
            events = []
            outcome = {"ok": False, "error": result.rejection.code.code}
            rejections += 1
        current = hash_state(state, game)
        writer.write_action(
            ActionRecord(
                seq=seq,
                player=player,
                action=action,
                result=outcome,
                state_hash_prev=previous,
                state_hash=current,
                rng=source.draws()[mark:],
                events=events,
                request_id=f"d{seq}",
            )
        )
        previous = current
        seq += 1
    final = game.outcome(state)
    writer.write_terminal(
        TerminalRecord(
            seq=seq,
            winner=final.winner,
            final_scores=dict(final.scores),
            rounds=final.rounds,
            total_actions=seq,
            rejections=rejections,
            state_hash=previous,
        )
    )
    writer.close()
    return path


def rewrite_records(path: Path, mutate: Mutation) -> None:
    """Edit a record in place, the way a tampered one would arrive."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    mutate(records)
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records)
        + "\n",
        encoding="utf-8",
    )
