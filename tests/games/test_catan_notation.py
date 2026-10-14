"""Notation: the renderings a person and a model actually read (PRD-v1 FR-19.4).

Notation is a first-class artefact, not a debugging convenience. How a state is rendered
measurably changes how a model plays, so holding the rendering constant across models is a
benchmark requirement (ARCHITECTURE.md section 11.4), and the CLI is where a human checks that
the rendering says what it should before any model ever sees it.

Two renderings are required: a full one for reading, and a compact one for token budgets. Both
must be stable - the same projection renders to the same string, every time - because a
rendering that drifted would be an uncontrolled variable in every comparison.
"""

from __future__ import annotations

import re
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.game import get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.core.types import Observation
from lgbg.games.catan.notation import Detail, render
from lgbg.games.catan.projection import observe, observe_spectator
from lgbg.games.catan.state import NO_OWNER, CatanState

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20250601


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _played() -> CatanState:
    """An opening state with a settlement, a road and a robber that has moved."""
    from dataclasses import replace

    from lgbg.games.catan.state import Placed

    state = _opening()
    settlements = [NO_OWNER] * len(state.placed.settlements)
    cities = [NO_OWNER] * len(state.placed.settlements)
    roads = [NO_OWNER] * len(state.placed.roads)
    settlements[4] = 0
    settlements[11] = 2
    cities[17] = 3
    roads[9] = 1
    return replace(
        state,
        placed=Placed(tuple(settlements), tuple(cities), tuple(roads)),
        robber=3,
        dice=(3, 4),
        turn=2,
    )


def _spectator(state: CatanState) -> Observation:
    return observe_spectator(state)


def test_the_full_rendering_names_the_phase_the_turn_and_the_round() -> None:
    text = render(_spectator(_played()))

    assert "catan" in text
    assert "setup_settlement" in text
    assert "turn 2" in text
    assert "round 0" in text


def test_the_full_rendering_shows_every_hex_with_its_terrain_and_token() -> None:
    state = _played()

    text = render(_spectator(state))

    for hex_id, terrain in enumerate(state.board.terrain):
        token = state.board.tokens[hex_id]
        expected = f"h{hex_id} {terrain.value}" + (f" t{token}" if token is not None else "")
        assert expected in text, expected


def test_the_full_rendering_lists_each_players_pieces() -> None:
    text = render(_spectator(_played()))

    assert "v4" in text, "settlements are named by vertex"
    assert "v11" in text, "each settlement separately"
    assert "v17" in text, "cities too"
    assert "e9" in text, "roads by edge"


def test_the_full_rendering_lays_the_board_out_in_rows() -> None:
    """The hexes are numbered row by row, so the rendering can reproduce the board's shape."""
    text = render(_spectator(_opening()))
    board_rows = [line for line in text.splitlines() if re.match(r"^h\d", line.strip())]

    assert len(board_rows) == 5, "a hexagon of side three has five rows"
    per_row = [len(re.findall(r"h\d+", line)) for line in board_rows]
    assert per_row == [3, 4, 5, 4, 3], "rows of a hexagon of side three"


def test_the_full_rendering_is_deterministic() -> None:
    state = _played()

    assert render(_spectator(state)) == render(_spectator(state))


def test_the_compact_rendering_is_shorter_and_still_says_what_matters() -> None:
    state = _played()
    full = render(_spectator(state), detail=Detail.FULL)
    compact = render(_spectator(state), detail=Detail.COMPACT)

    assert len(compact) < len(full)
    assert compact.count("\n") < full.count("\n")
    for fragment in ("catan", "setup_settlement", "turn 2"):
        assert fragment in compact
    assert "h9" in compact or "robber" in compact


def test_both_renderings_are_stable_across_calls_and_states() -> None:
    first = _played()
    second = _opening()

    for detail in (Detail.FULL, Detail.COMPACT):
        assert render(_spectator(first), detail=detail) == render(_spectator(first), detail=detail)
        assert render(_spectator(second), detail=detail) == render(
            _spectator(second), detail=detail
        )


def test_a_rendering_cannot_show_a_field_the_projection_left_out() -> None:
    """The projection is the gate; the renderer only ever sees what passed it."""
    state = _played()

    player_view = render(observe(state, 1))
    spectator_view = render(_spectator(state))

    assert "hands" not in player_view
    assert "hands" in spectator_view


def test_an_unrecognised_field_is_rendered_rather_than_dropped() -> None:
    """Rendering fails open on purpose: the projection is what decides what exists to render."""
    observation = dict(_spectator(_played()))
    observation["something_new"] = {"a": 1}

    text = render(observation)

    assert "something_new" in text


def test_rendering_a_players_view_never_mentions_another_players_hand() -> None:
    state = _played()

    for seat in range(PLAYERS):
        assert "hands" not in render(observe(state, seat))


def test_the_two_details_disagree_only_in_shape() -> None:
    """Both describe the same projection; a fact in one must not be missing from the other."""
    state = _played()
    spectator = _spectator(state)
    facts = [
        "catan",
        "setup_settlement",
        "turn 2",
        "h9",
        "v4",
        "v11",
    ]

    for fact in facts:
        assert fact in render(spectator, detail=Detail.FULL), fact
        assert fact in render(spectator, detail=Detail.COMPACT), fact


def test_the_rendering_reports_the_robber_and_the_dice() -> None:
    text = render(_spectator(_played()))

    assert "robber" in text
    assert "h3" in text, "the robber moved to hex 3"
    assert "dice: 3 4" in text, "the dice are visible to everybody"


def test_the_rendering_reports_the_bank_and_the_supply() -> None:
    text = render(_spectator(_played()))

    for resource in ("wood", "brick", "wool", "wheat", "ore"):
        assert resource in text
    assert "19" in text
    assert "15/5/4" in text


def test_the_rendering_of_the_opening_state_has_no_pieces() -> None:
    text = render(_spectator(_opening()))

    assert "none" in text
    assert "v4" not in text
