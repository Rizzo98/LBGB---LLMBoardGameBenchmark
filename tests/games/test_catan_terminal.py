"""Terminality: a finished game, and what it reports (PRD-v1 FR-15.3 to FR-15.5; RULES.md 4.13).

Three promises, and all of them are about what happens *after* somebody has won. The game is over
the moment the tenth point lands - nobody is asked for another decision, and a driver that keeps
poking it is told so rather than obeyed. The verdict answers without consuming a draw or touching
the position, because a verdict that changed the game it describes would be no verdict at all.
And the outcome states the true totals, the winner and the length of the game, which is what
every later metric is computed from.
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.canonical import hash_state, to_canonical_json
from lgbg.core.config import GameConfig
from lgbg.core.errors import GAME_OVER
from lgbg.core.game import Rejected, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rules.victory import TARGET, check, victory_points
from lgbg.games.catan.state import CARD_ORDER, CatanState, DevCard, Phase, encode_state
from tests.games.catan_boards import layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251201


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _vertices(state: CatanState, count: int) -> list[int]:
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


def _finished(seat: int = 0, *, round_: int = 9) -> CatanState:
    """A game that has been won: ten points for one seat, in the terminal phase."""
    state = _opening()
    sites = _vertices(state, 6)
    board = layout(
        state,
        cities=[(vertex, seat) for vertex in sites[:4]],
        settlements=[(vertex, seat) for vertex in sites[4:6]],
        turn=seat,
    )
    assert victory_points(board, seat) == TARGET
    won, _events = check(replace(board, round=round_))
    assert won.phase is Phase.TERMINAL
    return won


def test_only_the_terminal_phase_is_terminal() -> None:
    state = _opening()

    assert GAME.is_terminal(state) is False
    for phase in (Phase.SETUP_ROUND_1, Phase.TURN_PRODUCTION, Phase.ACTION, Phase.DISCARD):
        assert GAME.is_terminal(replace(state, phase=phase)) is False
    assert GAME.is_terminal(_finished()) is True


def test_a_finished_game_asks_nobody_for_a_decision() -> None:
    """FR-15.5: there is nothing to answer, and asking must not raise as an unimplemented phase."""
    won = _finished()

    assert phases.pending_decisions(won) == []
    for seat in range(PLAYERS):
        assert GAME.legal_actions(won, seat) == []
        assert GAME.action_domains(won, seat) == []


@pytest.mark.parametrize("action_type", ["roll_dice", "end_turn", "build_road", "move_robber"])
def test_no_action_is_accepted_after_the_win(action_type: str) -> None:
    """FR-15.5: a rejection with the core code, and a position that has not moved."""
    won = _finished()
    before = hash_state(won, GAME)

    refused = GAME.apply(won, Action(player=0, type=action_type, params={}), NullRandomSource())

    assert isinstance(refused, Rejected)
    assert refused.rejection.code == GAME_OVER
    assert dict(refused.rejection.details)["phase"] == Phase.TERMINAL.value
    assert hash_state(won, GAME) == before, "a rejection leaves the position exactly as it was"


def test_every_action_type_the_game_declares_is_refused_after_the_win() -> None:
    """The same promise over the whole declared surface rather than a sample of it."""
    won = _finished()
    declared = sorted(GAME.action_schema())

    assert len(declared) >= 6, "the surface must be worth sweeping"
    for action_type in declared:
        refused = GAME.apply(won, Action(player=0, type=action_type, params={}), NullRandomSource())
        assert isinstance(refused, Rejected), f"{action_type} was accepted after the win"
        assert refused.rejection.code == GAME_OVER


def test_the_outcome_reports_the_totals_the_winner_and_the_length() -> None:
    """FR-15.4: per-player true totals, the winner, and how long the game ran."""
    won = _finished(seat=2, round_=11)

    outcome = GAME.outcome(won)

    assert outcome.winner == 2
    assert dict(outcome.scores) == {str(seat): victory_points(won, seat) for seat in range(PLAYERS)}
    assert outcome.scores[str(2)] == TARGET
    assert outcome.rounds == 11


def test_a_game_still_in_progress_has_no_winner() -> None:
    """An empty board is worth nothing yet, and the draft has not put anything on it."""
    outcome = GAME.outcome(_opening())

    assert outcome.winner is None
    assert dict(outcome.scores) == {str(seat): 0 for seat in range(PLAYERS)}
    assert outcome.rounds == 0


def test_the_verdict_is_pure_and_takes_no_source_of_randomness() -> None:
    """FR-15.3: neither may draw, and neither may change the position it describes."""
    won = _finished()
    before = to_canonical_json(encode_state(won))

    assert GAME.is_terminal(won) == GAME.is_terminal(won)
    assert GAME.outcome(won) == GAME.outcome(won)
    assert to_canonical_json(encode_state(won)) == before
    assert list(inspect.signature(GAME.is_terminal).parameters) == ["state"]
    assert list(inspect.signature(GAME.outcome).parameters) == ["state"]


def test_a_won_game_stays_won_however_it_is_asked() -> None:
    """Nothing about asking a finished game for its verdict may revive it."""
    won = _finished()
    asked = GAME.outcome(won)

    assert GAME.outcome(won) == asked
    refused = GAME.apply(won, Action(player=0, type=phases.END_TURN, params={}), NullRandomSource())
    assert isinstance(refused, Rejected)
    assert GAME.is_terminal(won) is True


def test_the_terminal_answers_are_what_the_runtime_writes_into_its_record() -> None:
    """The runtime builds its terminal record from exactly these three answers.

    A GameRun cannot be handed a position, so what is asserted here is the contract the runtime
    reads - the winner, the final scores and the rounds all come from the outcome, and the final
    hash from the state it is called on. A game actually played to a win, and committed as a
    fixture, is K-038's.
    """
    won = _finished(seat=1, round_=4)

    outcome = GAME.outcome(won)

    assert outcome.winner == 1
    assert dict(outcome.scores) == {str(seat): victory_points(won, seat) for seat in range(PLAYERS)}
    assert outcome.rounds == 4
    assert hash_state(won, GAME) == hash_state(won, GAME)


def test_the_terminal_state_renders() -> None:
    """An operator must be able to read a finished game, so the notation must render it."""
    won = _finished()

    for detail in ("full", "compact", "board"):
        text = GAME.render(GAME.observe_spectator(won), detail=detail)
        assert isinstance(text, str)
        assert text.strip(), f"the {detail} rendering is empty"
    assert "terminal" in GAME.render(GAME.observe_spectator(won))


def test_a_victory_point_card_is_counted_from_the_god_view_only() -> None:
    """The one scoring term other players cannot compute is still counted (RULES.md 4.13 item 2)."""
    state = _opening()
    sites = _vertices(state, 6)
    board = layout(
        state,
        cities=[(vertex, 0) for vertex in sites[:3]],
        settlements=[(vertex, 0) for vertex in sites[3:5]],
        turn=0,
    )
    rows = [list(row) for row in board.dev_cards]
    rows[0][CARD_ORDER.index(DevCard.VICTORY_POINT)] = 1
    with_card = replace(board, dev_cards=tuple(tuple(row) for row in rows))

    assert victory_points(with_card, 0) == TARGET - 1, "three cities, two settlements, one card"
    won, _events = check(with_card)
    assert won.phase is not Phase.TERMINAL, "nine points is not ten"
    assert GAME.observe_spectator(with_card)["dev_cards"] == [
        list(row) for row in with_card.dev_cards
    ]
