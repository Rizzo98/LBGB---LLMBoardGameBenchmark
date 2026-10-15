"""Victory accounting and win detection (PRD-v1 FR-15.1, FR-15.2; RULES.md 4.13).

Scoring is five terms and a sum, and the interesting part is not the sum but *when* it is
consulted. The condition is tested after every transition and at the start of a turn, and it is
applied to the player whose turn it is - so a player who reaches ten while somebody else is
playing has not won, and wins at the start of their own turn, before rolling a die. The only way
that happens in this game is the Longest Road card changing hands, which is why the edge case has
its own test rather than a comment.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import GameConfig
from lgbg.core.errors import GAME_OVER
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rules.victory import POINTS, TARGET, check, victory_points
from lgbg.games.catan.state import CARD_ORDER, CatanState, DevCard, Phase, encode_state
from tests.games.catan_boards import free_edge, holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251124
VP_CARD: Final[int] = CARD_ORDER.index(DevCard.VICTORY_POINT)


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _cards(state: CatanState, seat: int, **counts: int) -> CatanState:
    """Hand this player development cards, by name."""
    names = {card.value: index for index, card in enumerate(CARD_ORDER)}
    assert set(counts) <= set(names)
    rows = [list(row) for row in state.dev_cards]
    for name, count in counts.items():
        rows[seat][names[name]] = count
    return replace(state, dev_cards=tuple(tuple(row) for row in rows))


def _vertices(state: CatanState, count: int) -> list[int]:
    """This many vertices, none of them next to another, so a fixture can be scattered."""
    chosen: list[int] = []
    for vertex in range(len(state.placed.settlements)):
        if all(
            vertex not in state.board.topology.vertices_of_edge(edge)
            for site in chosen
            for edge in state.board.topology.edges_at(site)
        ):
            chosen.append(vertex)
        if len(chosen) == count:
            return chosen
    raise AssertionError(f"the board has no room for {count} scattered buildings")


def _at(
    points: int,
    state: CatanState,
    seat: int = 0,
    *,
    turn: int | None = None,
    keep_city: bool = False,
) -> CatanState:
    """A position in which this seat is worth exactly this many victory points.

    Built from pieces alone - four cities and five settlements are thirteen points, which is the
    whole range these tests need. The special cards are deliberately not used here: every action
    that changes the board recomputes them, so a fixture that handed out an award without the
    roads to justify it would lose it again inside the very action under test.
    """
    cities = min(points // POINTS["city"], 3 if keep_city else 4)
    settlements = points - cities * POINTS["city"]
    assert 0 <= settlements <= 5, f"{points} is not reachable with pieces alone"
    sites = _vertices(state, cities + settlements)
    board = layout(
        state,
        settlements=[(vertex, seat) for vertex in sites[cities:]],
        cities=[(vertex, seat) for vertex in sites[:cities]],
        turn=state.turn if turn is None else turn,
    )
    assert victory_points(board, seat) == points
    return board


def test_the_terms_are_the_ones_appendix_a_lists() -> None:
    assert {
        "settlement": 1,
        "city": 2,
        DevCard.VICTORY_POINT.value: 1,
        "longest_road": 2,
        "largest_army": 2,
    } == POINTS
    assert TARGET == 10
    state = _opening()
    board = layout(
        state,
        settlements=[(_vertices(state, 1)[0], 0), (_vertices(state, 2)[1], 0)],
        cities=[(_vertices(state, 3)[2], 0)],
    )
    board = _cards(replace(board, longest_road=0, largest_army=0), 0, victory_point=2)

    assert victory_points(board, 0) == 2 + 2 + 2 + 2 + 2
    assert victory_points(board, 1) == 0


def test_the_opening_position_is_worth_two_points_to_everybody() -> None:
    """RULES.md 4.13 item 11: two settlements each, so eight more points are needed."""
    state = _opening()
    board = layout(state, settlements=[(_vertices(state, 8)[0], 0), (_vertices(state, 8)[1], 0)])

    assert victory_points(board, 0) == 2


def test_nine_points_do_not_end_the_game() -> None:
    state = _at(TARGET - 1, _opening())

    assert GAME.is_terminal(state) is False
    assert check(state) == (state, [])


def test_ten_points_during_your_own_turn_wins_immediately() -> None:
    """RULES.md 4.13 item 4: the tenth point ends the game in the action that produced it."""
    state = _at(TARGET - 1, _opening(), keep_city=True)
    upgrade = next(vertex for vertex, owner in enumerate(state.placed.settlements) if owner == 0)
    assert state.supply[0].cities > 0, "the fixture must leave a city to build with"
    ready = holding(replace(state, turn=0, phase=Phase.ACTION), 0, wheat=2, ore=3)

    won = GAME.apply(
        ready,
        Action(player=0, type=phases.BUILD_CITY, params={"vertex": upgrade}),
        NullRandomSource(),
    )

    assert isinstance(won, Applied)
    assert won.state.phase is Phase.TERMINAL
    assert GAME.is_terminal(won.state) is True
    assert victory_points(won.state, 0) == TARGET
    assert [event.type for event in won.events][-2:] == ["game_won", "phase_started"]
    assert dict(won.events[-2].payload) == {"player": 0, "points": TARGET, "target": TARGET}


def test_eleven_points_win_too() -> None:
    """The rule is "10 or more", so a position that jumped past it still ends the game."""
    state = _at(TARGET + 1, _opening(), turn=0)

    won, events = check(state)

    assert won.phase is Phase.TERMINAL
    assert dict(events[0].payload)["points"] == TARGET + 1


def test_points_gained_off_turn_do_not_win_immediately() -> None:
    """RULES.md 4.13 item 6: the condition is applied to the player whose turn it is."""
    state = _at(TARGET + 1, _opening(), seat=2, turn=0)
    assert victory_points(state, 2) == TARGET + 1

    assert check(state) == (state, []), "seat 2 is not the player to move"
    assert GAME.is_terminal(state) is False

    ended = GAME.apply(
        replace(state, phase=Phase.ACTION),
        Action(player=0, type=phases.END_TURN, params={}),
        NullRandomSource(),
    )

    assert isinstance(ended, Applied)
    assert ended.state.turn == 1
    assert GAME.is_terminal(ended.state) is False, "the turn reached seat 1, who is not at ten"


def test_the_win_lands_at_the_start_of_the_winners_turn_and_no_die_is_rolled() -> None:
    """S5: a player who already has ten points does not have to roll, and the game is over."""
    state = _at(TARGET, _opening(), seat=1, turn=0)

    won = GAME.apply(
        replace(state, phase=Phase.ACTION),
        Action(player=0, type=phases.END_TURN, params={}),
        NullRandomSource(),
    )

    assert isinstance(won, Applied)
    assert won.state.turn == 1
    assert won.state.phase is Phase.TERMINAL
    assert "dice_rolled" not in [event.type for event in won.events]
    assert dict(next(e for e in won.events if e.type == "game_won").payload)["player"] == 1


def test_nothing_can_be_done_after_the_win() -> None:
    """RULES.md 4.13 item 8: no further transition is possible, and certainly not a roll."""
    won = _at(TARGET, _opening(), turn=0)
    ended, _events = check(won)
    assert ended.phase is Phase.TERMINAL

    refused = GAME.apply(ended, Action(player=0, type="roll_dice", params={}), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == GAME_OVER


def test_the_outcome_reports_true_totals_and_the_winner() -> None:
    """FR-15.4: every player's true total, the winner, and the round it ended in."""
    state = _at(TARGET, _opening(), seat=0, turn=0)
    ended, _events = check(replace(state, round=7))

    outcome = GAME.outcome(ended)

    assert outcome.winner == 0
    assert outcome.scores[str(0)] == TARGET
    assert outcome.scores[str(2)] == 0
    assert outcome.rounds == 7
    assert GAME.outcome(state).winner is None, "no win before the condition is met"


def test_the_check_is_pure_and_takes_no_source_of_randomness() -> None:
    """FR-15.3: nothing about the verdict may consume a draw or change the position."""
    import inspect

    state = _at(TARGET, _opening(), turn=0)
    before = to_canonical_json(encode_state(state))

    first = check(state)
    second = check(state)

    assert first == second
    assert to_canonical_json(encode_state(state)) == before
    assert list(inspect.signature(check).parameters) == ["state"]
    assert GAME.outcome(state) == GAME.outcome(state)


@pytest.mark.parametrize("seat", range(PLAYERS))
def test_every_seat_can_win_on_its_own_turn(seat: int) -> None:
    state = _at(TARGET, _opening(), seat=seat, turn=seat)

    won, events = check(state)

    assert won.phase is Phase.TERMINAL
    assert dict(events[0].payload)["player"] == seat
    assert GAME.outcome(won).winner == seat
    assert free_edge(state, 0) >= 0, "the fixture is still a board"
