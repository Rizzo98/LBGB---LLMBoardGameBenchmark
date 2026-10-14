"""Replay and verification (ARCHITECTURE.md section 8.1; PRD-v1 FR-4.1 to FR-4.7).

Replay is what turns a record from a transcript into a program. It rebuilds the state after
every action through the *normal* 'apply' path with a ReplayRandomSource, so there is no
second implementation of the rules to drift from the first one, and a hash mismatch is a
statement about the engine rather than about a reimplementation of it.

Every failure localises itself to a seq and a kind (FR-4.7). At corpus scale, "replay
failed" is nearly useless; "seq 47: rng_mismatch: expected purpose 'dice_roll', got
'deck_deal'" is a diagnosis.

'verify' walks the same chain while keeping only the current state, which is what makes it
affordable across ten thousand games (FR-4.4). 'projection_replay' rebuilds the exact
sequence of observations one player saw, which is how a leaked field is caught as a fact
rather than argued about.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from lgbg.core.canonical import hash_state
from lgbg.core.config import RunConfig
from lgbg.core.errors import UNKNOWN_ACTION
from lgbg.core.game import Applied, Game
from lgbg.core.log import ActionRecord, GameLog
from lgbg.core.rng import (
    ReplayRandomSource,
    RngMismatchError,
    SeededRandomSource,
    UnconsumedDrawsError,
)
from lgbg.core.types import Event, Observation, PlayerId, Seq, State


class ReplayFailure(StrEnum):
    """Why a record did not reproduce. Always reported with the offending seq."""

    INITIAL_STATE_MISMATCH = "initial_state_mismatch"
    HASH_MISMATCH = "hash_mismatch"
    RNG_MISMATCH = "rng_mismatch"
    RNG_EXHAUSTION = "rng_exhaustion"
    EVENT_MISMATCH = "event_mismatch"
    UNKNOWN_ACTION = "unknown_action"
    RESULT_MISMATCH = "result_mismatch"
    TERMINAL_MISMATCH = "terminal_mismatch"


class ReplayError(Exception):
    """A record that does not replay, localised to one seq and one failure kind."""

    def __init__(self, kind: ReplayFailure, seq: Seq, detail: str) -> None:
        super().__init__(f"seq {seq}: {kind.value}: {detail}")
        self.kind = kind
        self.seq = seq
        self.detail = detail


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """The result of walking a chain: counts, never a list of states (FR-4.4)."""

    actions: int
    rejections: int
    terminal_hash: str


@dataclass(frozen=True, slots=True)
class ReplayedGame:
    """Every intermediate state: 'states[i]' is the state after action 'i - 1'."""

    states: list[State]
    actions: int
    rejections: int
    terminal_hash: str


def initial_state(log: GameLog, game: Game) -> State:
    """Rebuild the starting state from the header and check it against the recorded hash.

    The header pins the configuration and the hash it produced, so a replay that starts from
    a different board is caught before a single action is applied.
    """
    config = RunConfig.from_mapping(log.header.config, game_option_keys=None)
    state = game.initial_state(config.game_config, SeededRandomSource(config.seed))
    actual = hash_state(state, game)
    if actual != log.header.initial_state_hash:
        raise ReplayError(
            ReplayFailure.INITIAL_STATE_MISMATCH,
            0,
            f"the reconstructed initial state hashes to {actual}, but the header records "
            f"{log.header.initial_state_hash}",
        )
    return state


def replay(log: GameLog, game: Game) -> ReplayedGame:
    """Rebuild every intermediate state, verifying both hashes at every step (FR-4.1)."""
    states = list(_states(log, game))
    actions = len(log.actions)
    rejections = sum(1 for record in log.actions if record.result.get("ok") is False)
    terminal_hash = _check_terminal(log, game, states[-1], actions, rejections)
    return ReplayedGame(
        states=states, actions=actions, rejections=rejections, terminal_hash=terminal_hash
    )


def verify(log: GameLog, game: Game) -> VerificationReport:
    """Walk the chain without keeping the intermediate states (FR-4.4)."""
    # 'deque(maxlen=1)' keeps exactly one state while consuming the chain: the verification
    # never holds a list of intermediate states, which is what makes it affordable at scale.
    latest: State = deque(_states(log, game), maxlen=1)[-1]
    actions = len(log.actions)
    rejections = sum(1 for record in log.actions if record.result.get("ok") is False)
    terminal_hash = _check_terminal(log, game, latest, actions, rejections)
    return VerificationReport(actions=actions, rejections=rejections, terminal_hash=terminal_hash)


def projection_replay(log: GameLog, game: Game, player: PlayerId) -> list[Observation]:
    """Rebuild the exact sequence of observations one player saw (FR-4.6).

    One observation per action that player took, taken from the state immediately before it:
    that is what the player could know when they decided.
    """
    observations: list[Observation] = []
    state = initial_state(log, game)
    for record in log.actions:
        if record.player == player:
            observations.append(game.observe(state, player))
        state = _advance(game, state, record)
    return observations


def _states(log: GameLog, game: Game) -> Iterator[State]:
    """The state before the first action, then the state after every action."""
    state = initial_state(log, game)
    yield state
    for record in log.actions:
        state = _advance(game, state, record)
        yield state


def _advance(game: Game, state: State, record: ActionRecord) -> State:
    """Apply one recorded action, verifying the draw, the outcome, the events and the hash."""
    expected_prev = hash_state(state, game)
    if record.state_hash_prev != expected_prev:
        raise ReplayError(
            ReplayFailure.HASH_MISMATCH,
            record.seq,
            f"state_hash_prev is {record.state_hash_prev}, but the state before this action "
            f"hashes to {expected_prev}",
        )

    source = ReplayRandomSource(record.rng, action=f"#{record.seq}")
    try:
        result = game.apply(state, record.action, source)
    except RngMismatchError as error:
        raise ReplayError(ReplayFailure.RNG_MISMATCH, record.seq, str(error)) from error

    # An action the game does not declare is reported before anything else: it explains the
    # consequences (nothing was drawn, nothing was applied) rather than being explained by
    # them, and it is the diagnosis that tells a reader what to look at.
    if not isinstance(result, Applied) and result.rejection.code is UNKNOWN_ACTION:
        raise ReplayError(
            ReplayFailure.UNKNOWN_ACTION,
            record.seq,
            f"the record holds action type {record.action.type!r}, which this game does not "
            "declare",
        )

    try:
        source.assert_exhausted()
    except UnconsumedDrawsError as error:
        raise ReplayError(ReplayFailure.RNG_EXHAUSTION, record.seq, str(error)) from error

    accepted = record.result.get("ok") is True
    if isinstance(result, Applied):
        if not accepted:
            raise ReplayError(
                ReplayFailure.RESULT_MISMATCH,
                record.seq,
                "the record marks this action rejected, but replay accepted it",
            )
        if not _same_events(record.events, result.events):
            raise ReplayError(
                ReplayFailure.EVENT_MISMATCH,
                record.seq,
                f"the record holds events {[event.type for event in record.events]}, replay "
                f"produced {[event.type for event in result.events]}",
            )
        next_state = result.state
    else:
        if accepted:
            raise ReplayError(
                ReplayFailure.RESULT_MISMATCH,
                record.seq,
                f"the record marks this action accepted, but replay refused it with "
                f"{result.rejection.code.code}",
            )
        next_state = state

    actual = hash_state(next_state, game)
    if record.state_hash != actual:
        raise ReplayError(
            ReplayFailure.HASH_MISMATCH,
            record.seq,
            f"state_hash is {record.state_hash}, but replay produced {actual}",
        )
    return next_state


def _same_events(recorded: Sequence[Event], replayed: Sequence[Event]) -> bool:
    if len(recorded) != len(replayed):
        return False
    return all(
        left.type == right.type and dict(left.payload) == dict(right.payload)
        for left, right in zip(recorded, replayed, strict=True)
    )


def _check_terminal(log: GameLog, game: Game, state: State, actions: int, rejections: int) -> str:
    """Cross-check the terminal record: the counts only the runtime knows, and the verdict."""
    final_hash = hash_state(state, game)
    terminal = log.terminal
    if terminal is None:
        return final_hash
    if terminal.state_hash != final_hash:
        raise ReplayError(
            ReplayFailure.HASH_MISMATCH,
            terminal.seq,
            f"the terminal record's state_hash is {terminal.state_hash}, but the replayed "
            f"final state hashes to {final_hash}",
        )
    if terminal.total_actions != actions:
        raise ReplayError(
            ReplayFailure.TERMINAL_MISMATCH,
            terminal.seq,
            f"terminal.total_actions is {terminal.total_actions}, but the record holds "
            f"{actions} action(s)",
        )
    if terminal.rejections != rejections:
        raise ReplayError(
            ReplayFailure.TERMINAL_MISMATCH,
            terminal.seq,
            f"terminal.rejections is {terminal.rejections}, but replay counted {rejections}",
        )
    outcome = game.outcome(state)
    if terminal.winner != outcome.winner:
        raise ReplayError(
            ReplayFailure.TERMINAL_MISMATCH,
            terminal.seq,
            f"terminal.winner is {terminal.winner}, but the replayed outcome names winner "
            f"{outcome.winner}",
        )
    if dict(terminal.final_scores) != dict(outcome.scores):
        raise ReplayError(
            ReplayFailure.TERMINAL_MISMATCH,
            terminal.seq,
            f"terminal.final_scores is {dict(terminal.final_scores)}, but the replayed "
            f"outcome scores {dict(outcome.scores)}",
        )
    return final_hash
