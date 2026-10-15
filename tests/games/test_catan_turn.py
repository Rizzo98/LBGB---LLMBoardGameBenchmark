"""The turn: the roll, and ending it (PRD-v1 FR-10.1, FR-10.2; RULES.md 4.4).

A turn is two phases. It opens by offering the roll, the roll consumes two independent dice
draws, and what the roll means decides where the turn goes next: a seven skips production and
sends everybody over the limit to discard, anything else opens the action phase. Ending the turn
opens the next seat's.

The dice are two draws, never one draw of a total - the distributions differ, and a recorded
draw has to be replayable semantically (ARCHITECTURE.md 5.4).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.errors import NOT_YOUR_DECISION, WRONG_PHASE
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify
from lgbg.core.rng import KIND_RANDINT, NullRandomSource, SeededRandomSource
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rules.turn import DICE_DIE_1, DICE_DIE_2
from lgbg.games.catan.state import Phase

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20250801


def _in_production(seat: int = 0) -> Any:
    """A state waiting for a seat to roll, which is where every turn begins."""
    state = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return replace(state, phase=Phase.TURN_PRODUCTION, turn=seat, dice=None)


def _roll(state: Any, seat: int | None = None) -> Any:
    player = state.turn if seat is None else seat
    return GAME.apply(
        state, Action(player=player, type="roll_dice", params={}), SeededRandomSource(SEED)
    )


def test_the_turn_opens_with_the_roll_offered_to_the_current_player() -> None:
    state = _in_production(seat=2)

    requests = GAME.pending_decisions(state)

    assert len(requests) == 1
    assert requests[0].player == 2
    assert requests[0].schema_ref == "roll_dice"
    assert dict(requests[0].context)["actions"] == ["roll_dice"]


def test_the_roll_consumes_two_independent_dice_draws() -> None:
    """Draws D6 and D7: two randint(1, 6), never one randint(2, 12)."""
    source = SeededRandomSource(SEED)

    result = GAME.apply(_in_production(), Action(player=0, type="roll_dice", params={}), source)

    assert isinstance(result, Applied)
    draws = source.draws()
    assert [draw.purpose for draw in draws] == [DICE_DIE_1, DICE_DIE_2]
    assert all(draw.kind == KIND_RANDINT for draw in draws)
    assert all(dict(draw.args) == {"lo": 1, "hi": 6} for draw in draws)
    first, second = result.state.dice
    assert (first, second) == (draws[0].value, draws[1].value)
    assert 1 <= first <= 6
    assert 1 <= second <= 6


def test_the_roll_is_announced_and_becomes_visible() -> None:
    result = _roll(_in_production())

    assert isinstance(result, Applied)
    assert next(event.type for event in result.events) == "dice_rolled"
    payload = dict(result.events[0].payload)
    assert payload["dice"] == list(result.state.dice)
    assert payload["total"] == sum(result.state.dice)


def test_the_roll_closes_the_production_phase() -> None:
    state = _in_production()

    rolled = _roll(state)

    assert isinstance(rolled, Applied)
    seven = sum(rolled.state.dice) == 7
    # Nobody holds a card in this position, so a seven opens the discard phase and closes it in
    # the same breath: the game is then the robber's to move.
    assert rolled.state.phase is (Phase.ROBBER if seven else Phase.ACTION)
    if not seven:
        assert [request.schema_ref for request in GAME.pending_decisions(rolled.state)] == [
            "end_turn"
        ], "the production request is gone and the turn's action phase has opened"


def test_a_seven_opens_the_discard_phase_instead() -> None:
    """FR-10.5: a seven skips production and everybody over the limit discards first."""
    state = replace(_in_production(), dice=(3, 4))

    advanced, events = phases.advance(state)

    assert [event.type for event in events] == ["phase_started", "phase_started"]
    assert [dict(event.payload)["phase"] for event in events] == ["discard", "robber"]
    assert advanced.phase is Phase.ROBBER, (
        "nobody holds a card in this position, so the discard phase has nothing to ask and the "
        "game is already waiting for the robber to move"
    )


def test_production_ends_into_the_action_phase_on_any_other_total() -> None:
    state = replace(_in_production(), dice=(3, 3))

    advanced, _events = phases.advance(state)

    assert advanced.phase is Phase.ACTION
    assert [request.schema_ref for request in GAME.pending_decisions(advanced)] == ["end_turn"]


def test_ending_the_turn_opens_the_next_seats_production_phase() -> None:
    state = replace(_in_production(seat=1), phase=Phase.ACTION, dice=(2, 5))

    result = GAME.apply(state, Action(player=1, type="end_turn", params={}), NullRandomSource())

    assert isinstance(result, Applied)
    assert result.state.turn == 2
    assert result.state.phase is Phase.TURN_PRODUCTION
    assert result.state.dice is None, "the next seat has not rolled yet"
    assert [event.type for event in result.events] == ["turn_ended", "phase_started"]
    assert GAME.pending_decisions(result.state)[0].player == 2


def test_the_round_advances_when_the_turn_wraps_to_the_first_seat() -> None:
    state = replace(_in_production(seat=PLAYERS - 1), phase=Phase.ACTION, round=3, dice=(1, 1))

    result = GAME.apply(
        state, Action(player=PLAYERS - 1, type="end_turn", params={}), NullRandomSource()
    )

    assert isinstance(result, Applied)
    assert result.state.turn == 0
    assert result.state.round == 4


@pytest.mark.parametrize(
    ("phase", "action_type", "expected"),
    [
        (Phase.ACTION, "roll_dice", WRONG_PHASE),
        (Phase.TURN_PRODUCTION, "end_turn", WRONG_PHASE),
    ],
)
def test_an_action_in_the_wrong_phase_is_refused(
    phase: Phase, action_type: str, expected: Any
) -> None:
    state = replace(_in_production(), phase=phase)

    result = GAME.apply(state, Action(player=0, type=action_type, params={}), NullRandomSource())

    assert isinstance(result, Rejected)
    assert result.rejection.code == expected


def test_only_the_current_seat_may_roll() -> None:
    result = _roll(_in_production(seat=0), seat=3)

    assert isinstance(result, Rejected)
    assert result.rejection.code == NOT_YOUR_DECISION


def test_the_dice_stay_unrolled_when_the_roll_is_refused() -> None:
    state = _in_production(seat=0)

    _roll(state, seat=1)

    assert state.dice is None


def test_a_draft_then_a_turn_replays_from_its_record(tmp_path: Any) -> None:
    """The turn joins the draft on the same runtime, with the same guarantees."""
    run = GameRun(
        GAME,
        RunConfig(
            seed=SEED,
            players=PLAYERS,
            interaction_protocol="decline_only",
            game_config=GameConfig({"board": "fixed:standard_a"}),
        ),
        game_id="g-0001",
        directory=tmp_path,
    )
    for _ in range(16):
        request = run.pending[0]
        legal = GAME.legal_actions(run.state, request.player)
        assert isinstance(run.submit(legal[0]), Applied)
    rolled = run.submit(Action(player=run.state.turn, type="roll_dice", params={}))
    assert isinstance(rolled, Applied)
    ended = run.submit(Action(player=run.state.turn, type="end_turn", params={}))
    assert isinstance(ended, Applied)
    run.finish()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()
    report = verify(log, GAME)

    assert report.actions == 18
    assert report.rejections == 0
    assert [record.phase for record in log.phases] == [
        "setup_round_2",
        "turn_production",
        "action",
        "turn_production",
    ], "the draft, the first turn's roll, its action phase, and the next seat's turn"
