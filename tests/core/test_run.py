"""The run: applying actions, hashing, and writing the record (PRD-v1 FR-3.2, FR-9.2, FR-15.5).

A run is the only place where an action attempt becomes a record. Everything the record
promises is decided here: one record per attempt, accepted or rejected; a hash before and
after every attempt; the draws of *this* action and no others; and core-level validation
that happens before any rule logic.

A rejected attempt is deliberately not an exception. It is logged, counted, and leaves the
state hash untouched, because that is what makes an illegal-move rate measurable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from lgbg.core.canonical import hash_state
from lgbg.core.config import RunConfig
from lgbg.core.errors import GAME_OVER, NO_SUCH_REQUEST, NOT_YOUR_DECISION
from lgbg.core.game import Applied, Rejected
from lgbg.core.log import GameLogReader, LogFormatError, god_log_path, sidecar_path
from lgbg.core.replay import replay, verify
from lgbg.core.run import AmbiguousRequestError, GameRun
from lgbg.core.types import PHASE_STARTED_EVENT, Action, DecisionRequest, Event
from tests.games.fixture_game import FixtureGame

SEED: Final[int] = 31337
PROTOCOL: Final[str] = "decline_only"
FIXED_TIME: Final[str] = "2025-01-01T00:00:00+00:00"


class _TwoRequestsAtOnce(FixtureGame):
    """A game with two decisions open for the same player: the ambiguity case of FR-21.2."""

    def pending_decisions(self, state: Any) -> list[DecisionRequest]:
        return [
            DecisionRequest(
                request_id="d7",
                player=0,
                kind="turn",
                schema_ref="turn",
                context={},
                phase="play",
            ),
            DecisionRequest(
                request_id="d8",
                player=0,
                kind="turn",
                schema_ref="turn",
                context={},
                phase="play",
            ),
        ]


class _PhaseAnnouncing(FixtureGame):
    """The fixture again, announcing a phase transition whenever an action is accepted."""

    def apply(self, state: Any, action: Action, rng: Any) -> Any:
        result = super().apply(state, action, rng)
        if not isinstance(result, Applied):
            return result
        return Applied(
            state=result.state,
            events=[
                *result.events,
                Event(
                    type=PHASE_STARTED_EVENT,
                    payload={
                        "index": state.decisions + 1,
                        "phase": "play",
                        "turn": result.state.turn,
                    },
                ),
            ],
        )


def _run(tmp_path: Path | None = None, game: FixtureGame | None = None, **config: Any) -> GameRun:
    settings: dict[str, Any] = {"seed": SEED, "players": 2, "interaction_protocol": PROTOCOL}
    settings.update(config)
    return GameRun(
        game if game is not None else FixtureGame(),
        RunConfig(**settings),
        game_id="g-0001",
        directory=tmp_path,
        clock=lambda: FIXED_TIME,
    )


def _act(run: GameRun, type_: str = "gamble", *, player: int | None = None) -> Any:
    pending = run.pending
    if player is None:
        player = pending[0].player if pending else 0
    return run.submit(Action(player=player, type=type_, params={}))


def test_the_header_records_the_configuration_and_the_initial_hash(tmp_path: Path) -> None:
    run = _run(tmp_path)
    expected = hash_state(run.state, FixtureGame())

    run.finish()
    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()

    assert log.header.game == "fixture"
    assert log.header.players == 2
    assert log.header.initial_state_hash == expected
    assert log.header.config["seed"] == SEED
    assert log.header.engine_version


def test_an_accepted_action_is_logged_with_both_hashes_and_its_events(tmp_path: Path) -> None:
    run = _run(tmp_path)
    before = hash_state(run.state, FixtureGame())

    result = _act(run)
    run.finish()

    record = GameLogReader(god_log_path(tmp_path, "g-0001")).read().actions[0]
    assert isinstance(result, Applied)
    assert record.seq == 0
    assert record.state_hash_prev == before
    assert record.state_hash != before
    assert [event.type for event in record.events] == ["tokens_gained"]
    assert record.request_id is not None


def test_the_record_carries_only_the_draws_of_that_action(tmp_path: Path) -> None:
    run = _run(tmp_path)

    _act(run)
    _act(run)
    run.finish()

    actions = GameLogReader(god_log_path(tmp_path, "g-0001")).read().actions

    assert [len(record.rng) for record in actions] == [1, 1]
    assert all(draw.purpose == "gamble_bonus" for record in actions for draw in record.rng)


def test_a_rejected_action_is_logged_with_an_unchanged_hash(tmp_path: Path) -> None:
    run = _run(tmp_path)
    before = hash_state(run.state, FixtureGame())

    result = _act(run, "spend")
    run.finish()

    record = GameLogReader(god_log_path(tmp_path, "g-0001")).read().actions[0]
    assert isinstance(result, Rejected)
    assert record.result["ok"] is False
    assert record.result["error"] == "TOKENS_UNAVAILABLE"
    assert record.state_hash == record.state_hash_prev == before


def test_an_action_from_a_player_with_no_open_request_is_rejected(tmp_path: Path) -> None:
    run = _run(tmp_path)

    result = _act(run, "take", player=1)
    run.finish()

    assert isinstance(result, Rejected)
    assert result.rejection.code == NOT_YOUR_DECISION
    assert GameLogReader(god_log_path(tmp_path, "g-0001")).read().actions[0].request_id is None


def test_an_unknown_request_id_is_rejected(tmp_path: Path) -> None:
    run = _run(tmp_path)
    request = run.pending[0]

    result = run.submit(Action(player=request.player, type="take", params={}), request_id="d999")
    run.finish()

    assert isinstance(result, Rejected)
    assert result.rejection.code == NO_SUCH_REQUEST


def test_the_sole_open_request_is_used_when_none_is_named(tmp_path: Path) -> None:
    run = _run(tmp_path)
    request = run.pending[0]

    _act(run, "take")
    run.finish()

    assert GameLogReader(god_log_path(tmp_path, "g-0001")).read().actions[0].request_id == (
        request.request_id
    )


def test_an_ambiguous_choice_names_the_candidates(tmp_path: Path) -> None:
    run = _run(tmp_path, game=_TwoRequestsAtOnce())

    with pytest.raises(AmbiguousRequestError) as raised:
        run.submit(Action(player=0, type="take", params={}))

    assert "d7" in str(raised.value)
    assert "d8" in str(raised.value)
    run.close()


def test_naming_the_request_resolves_the_ambiguity(tmp_path: Path) -> None:
    run = _run(tmp_path, game=_TwoRequestsAtOnce())

    result = run.submit(Action(player=0, type="take", params={}), request_id="d8")
    run.finish()

    assert isinstance(result, Applied)
    assert GameLogReader(god_log_path(tmp_path, "g-0001")).read().actions[0].request_id == "d8"


def test_an_attempt_after_termination_is_recorded_as_a_game_over_rejection(tmp_path: Path) -> None:
    run = _run(tmp_path)
    for _ in range(200):
        if run.game.is_terminal(run.state):
            break
        _act(run, "spend" if run.state.tokens[run.state.turn] >= 4 else "take")

    result = _act(run, "take")
    terminal = run.finish()
    actions = GameLogReader(god_log_path(tmp_path, "g-0001")).read().actions

    assert isinstance(result, Rejected)
    assert result.rejection.code == GAME_OVER
    assert actions[-1].result["error"] == GAME_OVER.code
    assert actions[-1].state_hash == actions[-1].state_hash_prev
    assert terminal.state_hash == actions[-1].state_hash


def test_the_terminal_record_carries_the_counts_the_runtime_owns(tmp_path: Path) -> None:
    run = _run(tmp_path)
    _act(run, "take")
    _act(run, "spend")
    _act(run, "take")

    terminal = run.finish()
    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()

    assert terminal.seq == 3
    assert terminal.total_actions == 3
    assert terminal.rejections == 1
    assert log.terminal == terminal
    assert dict(terminal.final_scores) == dict(run.game.outcome(run.state).scores)


def test_finishing_twice_is_an_error(tmp_path: Path) -> None:
    run = _run(tmp_path)
    run.finish()

    with pytest.raises(LogFormatError):
        run.finish()


def test_a_run_writes_a_sidecar_beside_the_record(tmp_path: Path) -> None:
    run = _run(tmp_path)
    _act(run, "take")
    run.finish()

    written = json.loads(
        sidecar_path(tmp_path, "g-0001").read_text(encoding="utf-8").splitlines()[0]
    )

    assert written["at"] == FIXED_TIME
    assert written["t"] == "game"
    assert written["actions"] == 1
    assert '"at":' not in god_log_path(tmp_path, "g-0001").read_text(encoding="utf-8")


def test_a_recorded_game_replays_and_verifies(tmp_path: Path) -> None:
    """The slice 1 exit condition: play a game, then verify the record it produced."""
    run = _run(tmp_path)
    for _ in range(40):
        if run.game.is_terminal(run.state):
            break
        _act(run, "spend" if run.state.tokens[run.state.turn] >= 4 else "gamble")
    _act(run, "nonsense")
    run.finish()
    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()

    report = verify(log, FixtureGame())
    replayed = replay(log, FixtureGame())

    assert report.actions == len(log.actions) == run.actions
    assert report.rejections == 1
    assert len(replayed.states) == report.actions + 1
    assert hash_state(replayed.states[-1], FixtureGame()) == report.terminal_hash


def test_a_phase_transition_becomes_a_phase_record(tmp_path: Path) -> None:
    """FR-9.4: the game announces the transition, and the runtime owns the record type.

    A game carries its narrative in events and never invents a record of its own (FR-3.9), so
    the runtime turns the announcement into a record - which is then redundant with the event,
    and verified by replay like everything else.
    """
    run = _run(tmp_path, game=_PhaseAnnouncing())
    _act(run, "take")
    _act(run, "take")
    run.finish()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()

    assert [record.phase for record in log.phases] == ["play", "play"]
    assert [record.seq for record in log.phases] == [1, 2]
    assert dict(log.phases[0].detail) == {"index": 1, "turn": 1}
    assert verify(log, _PhaseAnnouncing()).actions == 2


def test_the_run_exposes_the_open_decisions(tmp_path: Path) -> None:
    run = _run(tmp_path)

    assert [request.player for request in run.pending] == [0]
    _act(run, "take")
    assert [request.player for request in run.pending] == [1]
    run.close()
