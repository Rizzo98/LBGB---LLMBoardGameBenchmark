"""A run: the only place an action attempt becomes a record (ARCHITECTURE.md section 8).

Everything a record promises is decided here.

- One record per attempt, accepted or rejected (FR-3.2). A rejection is logged and counted,
  never swallowed, because that is what makes the illegal-move rate measurable.
- A hash before and after every attempt (FR-3.3). A rejected attempt leaves it unchanged
  (FR-3.4), which is a cheap invariant and a powerful one.
- The draws of *this* action and no others: the initial state's draws belong to the seed,
  and a replay reproduces them from the header.
- Core-level validation before any rule logic (FR-9.2): an action for a player with no open
  decision, or naming a request that is not open, is refused by the runtime, not by the game.

The terminal record is written by 'finish', explicitly, rather than the moment the game ends.
A driver that keeps poking a finished game still gets its attempts logged as GAME_OVER
rejections (FR-15.5), and the record's last line stays the last line.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from lgbg.core.canonical import hash_state
from lgbg.core.config import RunConfig
from lgbg.core.errors import GAME_OVER, NO_SUCH_REQUEST, NOT_YOUR_DECISION, Rejection
from lgbg.core.game import Applied, ApplyResult, Game, Rejected
from lgbg.core.log import (
    ActionRecord,
    GameLogWriter,
    HeaderRecord,
    LogFormatError,
    PhaseRecord,
    SidecarWriter,
    TerminalRecord,
    god_log_path,
    rejected_result,
    sidecar_path,
)
from lgbg.core.rng import RngDraw, SeededRandomSource
from lgbg.core.schema import validate_action
from lgbg.core.types import (
    PHASE_STARTED_EVENT,
    Action,
    DecisionRequest,
    Event,
    GameId,
    JsonValue,
    PlayerId,
    State,
)


class AmbiguousRequestError(Exception):
    """An action names no request while its player has more than one open (FR-21.2).

    An error rather than a rejection: the *action* was never wrong, the caller failed to say
    which decision it was answering, and a driver that guesses would silently record a
    decision nobody made.
    """


class GameRun:
    """One game in progress: state, randomness, sequence counter and, optionally, its record."""

    def __init__(
        self,
        game: Game,
        config: RunConfig,
        *,
        game_id: GameId,
        directory: Path | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._game = game
        self._config = config
        self._game_id = game_id
        self._rng = SeededRandomSource(config.seed)
        self._state: State = game.initial_state(config.game_config, self._rng)
        self._seq = 0
        self._rejections = 0
        self._finished = False
        self._writer = (
            None if directory is None else GameLogWriter(god_log_path(directory, game_id))
        )
        self._sidecar = (
            None
            if directory is None
            else SidecarWriter(sidecar_path(directory, game_id), clock=clock)
        )
        if self._writer is not None:
            self._writer.write_header(self._header())

    @property
    def game(self) -> Game:
        return self._game

    @property
    def config(self) -> RunConfig:
        return self._config

    @property
    def state(self) -> State:
        return self._state

    @property
    def pending(self) -> list[DecisionRequest]:
        """The decisions open right now, in the game's own resolution order."""
        return self._game.pending_decisions(self._state)

    @property
    def actions(self) -> int:
        """How many attempts have been recorded, accepted or rejected."""
        return self._seq

    @property
    def rejections(self) -> int:
        return self._rejections

    def submit(self, action: Action, *, request_id: str | None = None) -> ApplyResult:
        """Apply one attempt, record it, and advance the sequence."""
        if self._finished:
            raise LogFormatError(
                f"game {self._game_id} has been finished; its record is closed to further actions"
            )
        previous = hash_state(self._state, self._game)
        request: DecisionRequest | None = None
        draws: Sequence[RngDraw] = ()

        if self._game.is_terminal(self._state):
            result: ApplyResult = Rejected(
                rejection=Rejection(
                    code=GAME_OVER,
                    message="the game has already terminated",
                    details={"seq": self._seq},
                )
            )
        else:
            resolved = self._resolve(action.player, request_id)
            if isinstance(resolved, Rejection):
                result = Rejected(rejection=resolved)
            else:
                request = resolved
                refusal = validate_action(self._game.action_schema(), action)
                if refusal is not None:
                    # The declared surface is binding: an action the schema does not describe, or
                    # describes and this one does not fit, never reaches rule logic (FR-18.2).
                    result = Rejected(rejection=refusal)
                else:
                    mark = len(self._rng.draws())
                    result = self._game.apply(self._state, action, self._rng)
                    draws = self._rng.draws()[mark:]

        if isinstance(result, Applied):
            self._state = result.state
            events = list(result.events)
            outcome: dict[str, JsonValue] = {"ok": True}
        else:
            events = []
            outcome = rejected_result(result.rejection)
            self._rejections += 1

        record = ActionRecord(
            seq=self._seq,
            player=action.player,
            action=action,
            result=outcome,
            state_hash_prev=previous,
            state_hash=hash_state(self._state, self._game),
            rng=draws,
            events=events,
            request_id=None if request is None else request.request_id,
        )
        if self._writer is not None:
            self._writer.write_action(record)
            self._write_phase_records(events)
        self._seq += 1
        return result

    def _write_phase_records(self, events: Sequence[Event]) -> None:
        """A phase transition is the game's event, but the record type is the runtime's.

        A game announces a transition with PHASE_STARTED_EVENT and never invents a record of
        its own (FR-3.9); the runtime turns the announcement into a phase record so a log can
        be read without replaying it.
        """
        if self._writer is None:
            return
        for event in events:
            if event.type != PHASE_STARTED_EVENT:
                continue
            self._writer.write_phase(
                PhaseRecord(
                    seq=self._seq + 1,
                    phase=str(event.payload.get("phase", "")),
                    detail={key: value for key, value in event.payload.items() if key != "phase"},
                )
            )

    def finish(self) -> TerminalRecord:
        """Close the record with the counts only the runtime can know, and the verdict."""
        if self._finished:
            raise LogFormatError(f"game {self._game_id} has already been finished")
        outcome = self._game.outcome(self._state)
        record = TerminalRecord(
            seq=self._seq,
            winner=outcome.winner,
            final_scores=dict(outcome.scores),
            rounds=outcome.rounds,
            total_actions=self._seq,
            rejections=self._rejections,
            state_hash=hash_state(self._state, self._game),
        )
        if self._writer is not None:
            self._writer.write_terminal(record)
            self._writer.close()
        if self._sidecar is not None:
            self._sidecar.write(
                "game",
                {
                    "actions": self._seq,
                    "game": self._game.name,
                    "game_id": self._game_id,
                    "rejections": self._rejections,
                    "rounds": outcome.rounds,
                    "winner": outcome.winner,
                },
            )
            self._sidecar.close()
        self._finished = True
        return record

    def close(self) -> None:
        """Abandon the run: close the files without writing a terminal record."""
        if self._writer is not None:
            self._writer.close()
        if self._sidecar is not None:
            self._sidecar.close()
        self._finished = True

    def __enter__(self) -> GameRun:
        return self

    def __exit__(self, *_: object) -> None:
        if not self._finished:
            self.close()

    def _header(self) -> HeaderRecord:
        return HeaderRecord(
            game_id=self._game_id,
            game=self._game.name,
            rules_version=self._game.rules_version,
            schema_version=self._game.schema_version,
            players=self._config.players,
            config=self._config.to_mapping(),
            prompt_hashes=dict(self._config.prompt_hashes),
            initial_state_hash=hash_state(self._state, self._game),
        )

    def _resolve(self, player: PlayerId, request_id: str | None) -> DecisionRequest | Rejection:
        """Match an attempt to the open decision it answers (FR-9.2, FR-21.2)."""
        requests = self.pending
        if request_id is not None:
            for candidate in requests:
                if candidate.request_id != request_id:
                    continue
                if candidate.player != player:
                    return Rejection(
                        code=NOT_YOUR_DECISION,
                        message=(
                            f"request {request_id!r} belongs to player {candidate.player}, "
                            f"not {player}"
                        ),
                        details={"request_id": request_id, "player": candidate.player},
                    )
                return candidate
            return Rejection(
                code=NO_SUCH_REQUEST,
                message=f"no open decision with request_id {request_id!r}",
                details={"request_id": request_id, "open": [r.request_id for r in requests]},
            )
        mine = [request for request in requests if request.player == player]
        if not mine:
            return Rejection(
                code=NOT_YOUR_DECISION,
                message=f"player {player} has no open decision",
                details={"open_players": [request.player for request in requests]},
            )
        if len(mine) > 1:
            raise AmbiguousRequestError(
                f"player {player} has {len(mine)} open decisions "
                f"({[request.request_id for request in mine]}); name one with request_id"
            )
        return mine[0]
