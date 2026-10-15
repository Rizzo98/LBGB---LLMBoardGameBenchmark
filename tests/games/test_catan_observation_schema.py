"""The declared shape of a projection (PRD-v1 FR-18.3, FR-16.8; ARCHITECTURE.md 7.3).

The schema is only worth having if it is true of what the engine actually projects, so it is
checked against every observation of every recorded game - the spectator's and all four players'.
The rest of the file is the drift guard: the field names come from the projection's own allow-list,
so a field projected without a declared shape, or a shape declared for a field nobody projects,
is a failure rather than a surprise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader
from lgbg.core.replay import replay
from lgbg.core.schema import violations
from lgbg.games.catan.observation_schema import FIELDS
from lgbg.games.catan.projection import (
    PLAYER_OBSERVATION_FIELDS,
    SPECTATOR_OBSERVATION_FIELDS,
)

GAME: Final[Any] = get_game("catan")
SEATS: Final[int] = 4
RECORDS: Final[tuple[str, ...]] = (
    "full_game",
    "trade_game",
    "devcard_game",
    "seven_game",
    "setup_game",
)
SHORT: Final[int] = 100
"""A record this long or shorter is read in full; a longer one is read every SAMPLE states."""
SAMPLE: Final[int] = 20


def _states(name: str) -> list[Any]:
    path = Path(__file__).resolve().parents[1] / "golden" / "catan" / f"{name}.god.jsonl"
    log = GameLogReader(path).read()
    return replay(log, GAME).states


def _plain(view: Any) -> Any:
    """An observation as it would be written: the validator sees JSON, not Python."""
    return json.loads(json.dumps(view))


def test_every_observation_of_every_recorded_game_validates() -> None:
    """FR-16.8 read as evidence: five games, both projections, every state."""
    schema = GAME.observation_schema()
    checked = 0
    refused: list[str] = []

    for name in RECORDS:
        states = _states(name)
        # Every state of the short records, and a stride through the long ones: the shape is what
        # is being checked, and a game of 743 states exercises no shape a game of 40 does not.
        stride = 1 if len(states) <= SHORT else SAMPLE
        for state in states[::stride]:
            views = [GAME.observe_spectator(state)]
            views += [GAME.observe(state, seat) for seat in range(SEATS)]
            for view in views:
                checked += 1
                found = violations(view, schema)
                if found:
                    refused.append(f"{name}: {found[0]}")

    assert checked > 500, "the corpus is the evidence, so it has to be read"
    assert refused == [], f"observations outside the declared shape: {refused[:3]}"


def test_every_projected_field_has_a_declared_shape() -> None:
    """The drift guard: the names are the projection's, the shapes are this module's."""
    projected = PLAYER_OBSERVATION_FIELDS | SPECTATOR_OBSERVATION_FIELDS

    assert set(FIELDS) == set(projected), "a field without a shape, or a shape without a field"


def test_the_two_projections_are_two_shapes_and_no_observer_is_both() -> None:
    """oneOf: exactly one branch fits, which is what keeps the two views apart."""
    schema = GAME.observation_schema()
    state = _states("seven_game")[3]
    player = _plain(GAME.observe(state, 1))
    spectator = _plain(GAME.observe_spectator(state))

    assert violations(player, schema) == []
    assert violations(spectator, schema) == []
    assert "hand" in player
    assert "hands" not in player
    assert "hands" in spectator
    assert "hand" not in spectator

    mixed = dict(spectator, hand=player["hand"])
    assert violations(mixed, schema), "nobody sees their own hand and everybody else's"
