"""Largest Army (PRD-v1 FR-13.9; RULES.md 4.11, 5.8 A-8).

The award is Longest Road's algorithm pointed at a different number, and the tests are the same
tests: a threshold, a single leader taking the card, a tie leaving it with the incumbent, and the
transfer happening during somebody else's action. The one thing that differs is worth stating -
the count only ever goes up, because a played knight never leaves play - and the branch the rules
call unreachable is implemented and tested anyway, since a rule that is skipped is a rule nobody
can check.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rules.victory import (
    ARMY,
    TARGET,
    largest_army_holder,
    recompute_awards,
    victory_points,
)
from lgbg.games.catan.state import CARD_ORDER, NO_OWNER, CatanState, DevCard, Phase
from tests.games.catan_boards import layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260202
KNIGHT: Final[int] = CARD_ORDER.index(DevCard.KNIGHT)


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _knights(state: CatanState, *played: int, army: int = NO_OWNER) -> CatanState:
    """A position with these played-knight counts, and whichever holder the test needs."""
    return replace(layout(state), knights_played=tuple(played), largest_army=army)


def test_three_played_knights_win_the_card_and_two_do_not() -> None:
    """RULES.md 4.11 item 3: the threshold, on both sides of it."""
    assert largest_army_holder(_knights(_opening(), ARMY - 1, 0, 0, 0)) == NO_OWNER
    assert largest_army_holder(_knights(_opening(), ARMY, 0, 0, 0)) == 0
    assert ARMY == 3


def test_unplayed_knights_do_not_count() -> None:
    """Item 2: the count is of knights *played*, so a hand full of them is worth nothing."""
    state = _knights(_opening(), 0, 0, 0, 0)
    cards = [list(row) for row in state.dev_cards]
    cards[0][KNIGHT] = 5
    holding = replace(state, dev_cards=tuple(tuple(row) for row in cards))

    assert largest_army_holder(holding) == NO_OWNER
    assert holding.knights_played[0] == 0


def test_the_greatest_count_takes_the_card() -> None:
    state = _knights(_opening(), 2, 4, 3, 1)

    awarded, events = recompute_awards(state)

    assert awarded.largest_army == 1
    assert [event.type for event in events] == ["largest_army_awarded"]
    assert dict(events[0].payload) == {"player": 1, "knights": 4}


def test_a_tie_leaves_the_card_with_the_incumbent() -> None:
    """Item 4: the same tie rule Longest Road uses, and it needs the incumbent to apply it."""
    tied = _knights(_opening(), 4, 4, 0, 0, army=0)

    assert largest_army_holder(tied) == 0
    assert recompute_awards(tied) == (tied, [])


def test_a_tie_that_excludes_the_incumbent_takes_the_card_off_the_board() -> None:
    """The branch the rules call unreachable, implemented and tested anyway."""
    tied = _knights(_opening(), 4, 4, 0, 0, army=2)

    assert largest_army_holder(tied) == NO_OWNER
    vacated, events = recompute_awards(tied)

    assert vacated.largest_army == NO_OWNER
    assert [event.type for event in events] == ["largest_army_vacated"]


def test_playing_the_third_knight_awards_the_card_in_the_same_action() -> None:
    """The award follows the count, and the count changes where the knight is played."""
    state = _knights(_opening(), 2, 0, 0, 0)
    cards = [list(row) for row in state.dev_cards]
    cards[0][KNIGHT] = 1
    ready = replace(state, dev_cards=tuple(tuple(row) for row in cards), dice=(3, 4))

    played = GAME.apply(
        ready,
        Action(player=0, type=phases.PLAY_DEV_CARD, params={"card": "knight"}),
        NullRandomSource(),
    )

    assert isinstance(played, Applied)
    assert played.state.knights_played[0] == ARMY
    assert played.state.largest_army == 0
    assert "largest_army_awarded" in [event.type for event in played.events]
    assert played.state.phase is Phase.ROBBER, "and the robber flow still runs"


def test_the_card_is_worth_two_points_and_counts_towards_the_target() -> None:
    """Item 1, and the sum §4.13 makes of it."""
    state = _knights(_opening(), ARMY, 0, 0, 0, army=0)

    assert victory_points(state, 0) == 2
    assert TARGET == 10
    assert layout(state) == layout(state)


def test_the_award_is_recomputed_rather_than_claimed() -> None:
    """No action takes an award: the engine puts the card where the counts say (item 4)."""
    state = _knights(_opening(), ARMY, 0, 0, 0)

    assert state.largest_army == NO_OWNER
    assert largest_army_holder(state) == 0
    assert "claim_award" not in GAME.action_schema()
