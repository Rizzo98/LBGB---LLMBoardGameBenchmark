"""One leak test per hidden field per observer (FR-16.6, SC-6; kanban card K-065).

The rule the whole projection lives under: a fact is there because somebody named it, and every
other fact is absent from every view that is not entitled to it. Rather than scanning a rendering
for a word that should not appear, each test here changes the hidden field and asserts that the
observer cannot tell - the projection, and every rendering of it, comes out byte for byte the same.
The control is in the same test: the mutation is real, and the spectator sees it move.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig
from lgbg.core.delta import render_delta
from lgbg.core.game import get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.games.catan.state import CARD_ORDER, CatanState, DevCard
from tests.games.catan_boards import holding, layout

GAME: Final[Any] = get_game("catan")
SEATS: Final[int] = 4
DETAILS: Final[tuple[str, ...]] = ("full", "compact", "board")
KNIGHT: Final[int] = CARD_ORDER.index(DevCard.KNIGHT)


def _midgame() -> CatanState:
    """A position with pieces, cards and a roll: every hidden field has content to hide."""
    state = layout(
        GAME.initial_state(
            GameConfig({"board": "fixed:standard_a", "players": SEATS}),
            SeededRandomSource(20261101),
        ),
        roads=[(0, 0), (3, 1)],
        settlements=[(1, 0), (2, 1)],
    )
    for seat, cards in enumerate(({"wood": 2}, {"ore": 3}, {"wool": 1}, {"wheat": 2})):
        state = holding(state, seat, **cards)
    return replace(state, dice=(3, 4))


def _one_knight() -> tuple[int, ...]:
    """One knight for seat 0: a card that moves no visible total, since it is not a point."""
    counts = [0] * len(CARD_ORDER)
    counts[KNIGHT] = 1
    return tuple(counts)


MUTATIONS: Final[dict[str, Any]] = {
    "bought_this_turn": lambda s: replace(
        s, bought_this_turn=((0, 0, 0, 1, 0), *s.bought_this_turn[1:])
    ),
    "dev_cards": lambda s: replace(s, dev_cards=(_one_knight(), *s.dev_cards[1:])),
    "dev_deck": lambda s: replace(s, dev_deck=s.dev_deck[1:] or s.dev_deck),
    "discards_pending": lambda s: replace(s, discards_pending=(2, 0, 0, 0)),
    # The same size of hand with different contents: hand *counts* are public (FR-16.2), so a
    # bigger hand would be visible to everybody and would prove nothing about the contents.
    "hands": lambda s: replace(s, hands=((0, 0, 0, sum(s.hands[0]), 0), *s.hands[1:])),
    "knights_played": lambda s: replace(s, knights_played=(0, 5, 0, 0)),
    "played_this_turn": lambda s: replace(s, played_this_turn=(0, 1, 0, 0)),
    "responses": lambda s: replace(s, responses=(0, 1, 0, 0)),
}
"""One mutation per hidden field: a value no observer may see, in a field the spectator may."""


def _views(state: CatanState, seat: int) -> list[str]:
    """Everything one observer is ever shown: the projection and every rendering of it."""
    observation = GAME.observe(state, seat)
    return [
        str(sorted(observation.items())),
        *(GAME.render(observation, detail=detail) for detail in DETAILS),
    ]


@pytest.mark.parametrize("field", sorted(MUTATIONS))
@pytest.mark.parametrize("seat", range(SEATS))
def test_a_hidden_field_is_invisible_to_every_observer(field: str, seat: int) -> None:
    before = _midgame()
    after = MUTATIONS[field](before)

    if field == "hands" and seat == 0:
        # The one case where the observer is entitled to see it: seat 0's own hand. That the hand
        # *is* visible to its owner, and only to its owner, is what the test below asserts.
        pytest.skip("seat 0 may see its own hand")

    assert _views(after, seat) == _views(before, seat), f"{field} leaked to seat {seat}"


@pytest.mark.parametrize("field", sorted(MUTATIONS))
def test_the_mutation_is_real_and_the_spectator_sees_it(field: str) -> None:
    """The control: a mutation nothing can see would make the tests above pass for free."""
    before = _midgame()
    after = MUTATIONS[field](before)

    assert after != before, f"{field} was not actually changed"
    assert GAME.observe_spectator(after) != GAME.observe_spectator(before)


def test_one_players_hand_is_not_another_players_hand() -> None:
    """The observer-relative half: seat 1 sees its own hand and never seat 0's."""
    before = _midgame()
    after = replace(before, hands=((0, 0, 0, sum(before.hands[0]), 0), *before.hands[1:]))

    assert GAME.observe(after, 1) == GAME.observe(before, 1), "seat 1 is told nothing of seat 0"
    assert GAME.observe(after, 0) != GAME.observe(before, 0), "seat 0 is told its own"
    assert render_delta(GAME.observe(before, 0), GAME.observe(after, 0)).startswith("delta:")
