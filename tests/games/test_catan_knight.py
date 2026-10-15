"""The knight card (PRD-v1 FR-12.6; RULES.md 4.8, 4.9).

A knight does what a seven does: it moves the robber and it steals. The card is worth testing
precisely because it must *not* be worth implementing twice - the robber flow already exists, and
what the knight does is put the game into the phase that runs it. The two things a test has to
hold apart are the ones that differ: a knight never opens the discard phase (A-2), even from a
table full of cards, and a knight played before the roll gives the turn back to the roll rather
than to the action phase.

The card also counts itself. A played knight stays face up for the rest of the game, and the
count is what Largest Army is computed from (K-047).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rules.robber import destinations, robber_victims
from lgbg.games.catan.state import CARD_ORDER, CatanState, DevCard, Phase
from tests.games.catan_boards import free_edge, holding, layout, vertices_of

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251229
KNIGHT: Final[int] = CARD_ORDER.index(DevCard.KNIGHT)
PLENTY: Final[int] = CARD_ORDER.index(DevCard.YEAR_OF_PLENTY)


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _with(
    state: CatanState,
    *,
    knights: int = 1,
    plenty: int = 0,
    seat: int = 0,
    phase: Phase = Phase.ACTION,
    dice: tuple[int, int] | None = (3, 4),
    settlements: tuple[tuple[int, int], ...] = (),
) -> CatanState:
    """A position holding development cards, in whichever window the test is about."""
    board = layout(state, turn=seat, settlements=settlements)
    cards = [list(row) for row in board.dev_cards]
    cards[seat][KNIGHT] = knights
    cards[seat][PLENTY] = plenty
    return replace(board, dev_cards=tuple(tuple(row) for row in cards), phase=phase, dice=dice)


def _play(state: CatanState, card: str = "knight", seat: int = 0) -> Any:
    return GAME.apply(
        state,
        Action(player=seat, type=phases.PLAY_DEV_CARD, params={"card": card}),
        NullRandomSource(),
    )


def _two_households(state: CatanState) -> CatanState:
    """A robber destination with two neighbours holding cards: the flow needs a victim choice."""
    hex_id = next(hex_.id for hex_ in state.board.topology.hexes if hex_.id != state.robber)
    first, second = state.board.topology.vertices_of_hex(hex_id)[:2]
    board = _with(state, settlements=((first, 1), (second, 2)))
    return holding(holding(board, 1, brick=2), 2, wood=2)


def _move_and_rob(state: CatanState, hex_id: int) -> CatanState:
    """Drive the robber flow the knight opened, the way a driver would."""
    moved = GAME.apply(
        state, Action(player=0, type=phases.MOVE_ROBBER, params={"hex": hex_id}), NullRandomSource()
    )
    assert isinstance(moved, Applied)
    while not GAME.is_terminal(moved.state) and any(
        request.kind == phases.CHOOSE_ROBBER_VICTIM
        for request in GAME.pending_decisions(moved.state)
    ):
        candidates = list(robber_victims(moved.state))
        choice = GAME.apply(
            moved.state,
            Action(player=0, type=phases.CHOOSE_ROBBER_VICTIM, params={"victim": candidates[0]}),
            SeededRandomSource(SEED),
        )
        assert isinstance(choice, Applied)
        moved = choice
    resolved: CatanState = moved.state
    return resolved


def test_playing_a_knight_moves_the_robber() -> None:
    """FR-12.6: the card puts the game into the robber phase, which asks for the move."""
    state = _with(_opening())

    played = _play(state)

    assert isinstance(played, Applied)
    assert played.state.phase is Phase.ROBBER
    assert [request.kind for request in GAME.pending_decisions(played.state)] == [
        phases.MOVE_ROBBER
    ]
    assert played.state.knights_played[0] == 1, "and the card counts itself"
    assert [event.type for event in played.events] == ["dev_card_played", "phase_started"]


def test_the_knight_runs_the_flow_a_seven_runs_and_then_gives_the_turn_back() -> None:
    """The flow is reused: the same move, the same victim choice, and back to the action phase."""
    state = _two_households(_with(_opening()))
    hex_id = next(hex_.id for hex_ in state.board.topology.hexes if hex_.id != state.robber)
    played = _play(state)
    assert isinstance(played, Applied)

    resolved = _move_and_rob(played.state, hex_id)

    assert resolved.phase is Phase.ACTION, "the turn goes on where the robber interrupted it"
    assert resolved.robber == hex_id
    assert sum(sum(hand) for hand in resolved.hands) == sum(sum(hand) for hand in state.hands)
    assert GAME.check_invariants(resolved) == []


def test_a_knight_played_before_the_roll_gives_the_turn_back_to_the_roll() -> None:
    """RULES.md 4.9: a knight may be played before the roll, and then the turn still wants one."""
    state = _with(_opening(), phase=Phase.TURN_PRODUCTION, dice=None)

    played = _play(state)
    assert isinstance(played, Applied)
    assert played.state.phase is Phase.ROBBER

    hex_id = destinations(played.state)[0]
    resolved = _move_and_rob(played.state, hex_id)

    assert resolved.phase is Phase.TURN_PRODUCTION, "the roll is still to come"
    assert resolved.dice is None
    assert [request.schema_ref for request in GAME.pending_decisions(resolved)] == [
        phases.ROLL_DICE
    ]


def test_a_knight_never_opens_the_discard_phase() -> None:
    """A-2: only a seven makes players discard half their hands, whatever a knight does."""
    state = _with(_opening(), settlements=((vertices_of(_opening(), 0)[0], 1),))
    hands = [list(row) for row in state.hands]
    hands[1] = [3, 3, 3, 3, 3]
    state = replace(state, hands=tuple(tuple(row) for row in hands))
    assert sum(state.hands[1]) > 7

    played = _play(state)
    assert isinstance(played, Applied)
    resolved = _move_and_rob(played.state, destinations(played.state)[0])

    assert resolved.phase is Phase.ACTION
    assert resolved.hands[1] == state.hands[1], "the hand is untouched: nobody discarded"
    assert [event for event in played.events if event.type == "discarded"] == []


def test_knights_accumulate_across_turns() -> None:
    """A played knight stays in play: the count is what Largest Army reads (K-047)."""
    state = _with(_opening(), knights=1)
    first = _play(state)
    assert isinstance(first, Applied)
    moved = _move_and_rob(first.state, destinations(first.state)[0])
    ended = GAME.apply(moved, Action(player=0, type=phases.END_TURN, params={}), NullRandomSource())
    assert isinstance(ended, Applied)
    assert ended.state.knights_played[0] == 1

    second = replace(ended.state, turn=0, phase=Phase.ACTION, dice=(3, 4))
    cards = [list(row) for row in second.dev_cards]
    cards[0][KNIGHT] = 1
    second = replace(second, dev_cards=tuple(tuple(row) for row in cards))
    again = _play(second)

    assert isinstance(again, Applied)
    assert again.state.knights_played[0] == 2


def test_the_knight_is_the_card_that_is_offered_and_the_others_are_not() -> None:
    """K-041's offer, now that effects exist: the card in hand is offered, under its own name."""
    state = _with(_opening(), knights=1, plenty=0)

    offered = [
        dict(action.params)["card"]
        for action in GAME.legal_actions(state, 0)
        if action.type == phases.PLAY_DEV_CARD
    ]

    assert offered == [DevCard.KNIGHT.value], "one card in hand, one card offered"
    assert free_edge(state, vertices_of(state, 0)[0]) >= 0, "the fixture is still a board"
    assert holding(state, 3, wool=1) is not state
