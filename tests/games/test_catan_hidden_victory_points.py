"""Victory-point cards, and what other players may compute (PRD-v1 FR-13.8, FR-16.4; RULES.md 4.13).

The card is worth a point to its owner and nothing to anybody else until it is shown, and showing
it is not an action - it happens only as a consequence of winning. That single fact is what makes
"who is winning" a question a player has to reason about rather than read off the table, and it is
why the projection carries two numbers per seat: the observer's own true total, and everybody
else's as far as it can be computed.

The leak test here is the same shape as the one for hands (K-028): two positions that differ only
in a hidden card must project identically for everybody who is not entitled to see it, with the
owner and the spectator as the controls that they really do differ.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig
from lgbg.core.game import get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.games.catan.notation import Detail, render
from lgbg.games.catan.projection import observe, observe_spectator
from lgbg.games.catan.rules.victory import public_points, victory_points
from lgbg.games.catan.state import CARD_ORDER, RESOURCE_ORDER, CatanState, DevCard
from tests.games.catan_boards import layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260126
VP: Final[int] = CARD_ORDER.index(DevCard.VICTORY_POINT)
SEATS: Final[tuple[int, ...]] = tuple(range(PLAYERS))


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _points(state: CatanState, seat: int, *, cards: int = 0, cities: int = 0) -> CatanState:
    """A position where one seat holds hidden victory-point cards and some buildings."""
    sites: list[int] = []
    if cities == 0:
        sites = []
    for vertex in range(len(state.placed.settlements)):
        if cities and len(sites) == cities:
            break
        if all(
            vertex not in state.board.topology.vertices_of_edge(edge)
            for site in sites
            for edge in state.board.topology.edges_at(site)
        ):
            sites.append(vertex)
    board = layout(state, cities=[(site, seat) for site in sites], turn=0)
    rows = [list(row) for row in board.dev_cards]
    rows[seat][VP] = cards
    return replace(board, dev_cards=tuple(tuple(row) for row in rows))


def test_a_victory_point_card_counts_for_its_owner() -> None:
    """FR-13.8: the card is worth a point to the player holding it, revealed or not."""
    state = _points(_opening(), 1, cards=2, cities=2)

    assert victory_points(state, 1) == 2 * 2 + 2
    assert public_points(state, 1) == 2 * 2, "and nothing at all to anybody counting the table"


def test_the_owners_view_counts_them_and_everybody_elses_does_not() -> None:
    """FR-16.4: the public total excludes the cards nobody has seen."""
    state = _points(_opening(), 1, cards=3, cities=1)

    mine = observe(state, 1)["points"]
    theirs = observe(state, 2)["points"]

    assert isinstance(mine, dict)
    assert isinstance(theirs, dict)
    assert int(mine["1"]) == 5, "a city and three cards"
    assert int(theirs["1"]) == 2, "the same city, and no cards"
    assert int(theirs["2"]) == victory_points(state, 2)


def test_the_public_total_is_not_the_true_total_for_anybody_but_the_owner() -> None:
    state = _points(_opening(), 2, cards=4, cities=1)

    for observer in SEATS:
        points = observe(state, observer)["points"]
        assert isinstance(points, dict)
        assert int(points["2"]) == (6 if observer == 2 else 2)


def test_hidden_cards_are_not_reachable_from_another_players_view() -> None:
    """The leak test: same public facts, different hidden cards, same observation."""
    before = _points(_opening(), 1, cards=1, cities=1)
    after = _points(_opening(), 1, cards=4, cities=1)

    for observer in (0, 2, 3):
        assert observe(before, observer) == observe(after, observer), (
            f"seat {observer} can tell one victory-point card from four"
        )
    assert observe(before, 1) != observe(after, 1), "the owner knows their own cards"
    assert observe_spectator(before) != observe_spectator(after), "control: the states differ"


@pytest.mark.parametrize("detail", [Detail.FULL, Detail.COMPACT])
def test_the_rendering_does_not_leak_them_either(detail: Detail) -> None:
    """K-028's rule, applied to the one field that is a *number* rather than a hand."""
    before = _points(_opening(), 1, cards=1, cities=1)
    after = _points(_opening(), 1, cards=4, cities=1)

    rendered = [render(observe(before, seat), detail=detail) for seat in (0, 2, 3)]
    changed = [render(observe(after, seat), detail=detail) for seat in (0, 2, 3)]

    assert rendered == changed
    for text in rendered:
        assert "points:" in text or "points " in text, "the score is rendered"
    hidden = render(observe(before, 1), detail=detail)
    assert hidden != rendered[0], "and the owner's own view says something different"


def test_the_two_numbers_differ_by_exactly_the_hidden_cards() -> None:
    state = _points(_opening(), 3, cards=5, cities=1)

    assert victory_points(state, 3) - public_points(state, 3) == 5
    assert public_points(state, 3) == 2, "everything about that seat except the five cards"


def test_a_card_bought_this_turn_is_publicly_invisible_too() -> None:
    """The purchase moves a card into the hand, and the point it is worth is not announced."""
    state = _points(_opening(), 0, cards=2, cities=1)
    rows = [list(row) for row in state.bought_this_turn]
    rows[0][VP] = 1
    fresh = replace(state, bought_this_turn=tuple(tuple(row) for row in rows))

    assert public_points(fresh, 0) == 2, "the city is public, the cards are not"
    assert victory_points(fresh, 0) == 4


def test_the_score_field_is_only_in_the_view_that_has_an_observer() -> None:
    """The spectator sees every hand, so it does not need a per-observer score."""
    state = _points(_opening(), 1, cards=2)

    assert "points" in observe(state, 0)
    assert "points" not in observe_spectator(state)
    assert "dev_cards" in observe_spectator(state)
    assert len(RESOURCE_ORDER) == 5, "the board still has five resources"
