"""The session facade: the one component that owns mutable game state (PRD-v2 FR-1.1 to FR-1.6).

Every surface v2 adds - the MCP server, the HTTP host, the runner, the CLI - is a transport over
this class and nothing else. That is the whole design, and it is what keeps three transports from
drifting into three subtly different games (FR-1.4, SC-2): there is one place a move can be made,
one place a state can be read, and one place a record can be written.

**The operations are the engine's, not the game's.** Create, list, read a projection, read the
open decisions, submit an action, read the decision surface at the run's assist level, read the
outcome, and end the session. Nothing here enumerates legal actions or asks a game a question
about itself: enumeration is an assist-level property of a *surface* (FR-3.3, FR-4), and a facade
that could enumerate would quietly make the assist level a suggestion. The set is closed and
declared in `PUBLIC_OPERATIONS`, and a test compares it against the class, so an operation is a
decision rather than an accident. `snapshot` is the one read that is not a player surface: it is
how an in-process driver hands a non-model seat the position (K-027), it still enumerates
nothing, and no transport serves it.

**Concurrency, stated rather than hoped for (FR-1.5, NFR-6).** There is one lock per session, held
for the duration of one operation, and one lock around the registry held only while the dictionary
is read or written. So:

- several sessions advance in parallel, because their locks are different locks;
- one session may have several open decisions answered at once, because the decisions are answered
  one operation at a time on a state that only moves when an action is accepted;
- a session's records are written by that session's writer, so a record that looks complete cannot
  be the result of two threads interleaving. A record cut short is a process that died, which is
  exactly what the reader already reports (`TruncatedLogError`) rather than hides.

**A game ends once, and the facade is what notices.** The moment an accepted action makes the game
terminal, the facade writes the terminal record and closes the files, so a completed game cannot be
mistaken for an abandoned one and a runner does not have to remember to close anything (FR-11.6). A
session ended before that leaves a record with no terminal line: that is an abandonment, and it says
so by saying nothing rather than by inventing a verdict (FR-7.5).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from threading import Lock, RLock
from typing import Final

from lgbg.core.assist import render_decision
from lgbg.core.config import RunConfig
from lgbg.core.game import ApplyResult, Game, get_game
from lgbg.core.run import GameRun
from lgbg.core.types import (
    Action,
    DecisionRequest,
    GameId,
    Observation,
    Outcome,
    PlayerId,
    State,
)

PUBLIC_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "create_session",
        "decision_surface",
        "end_session",
        "list_sessions",
        "outcome",
        "pending_decisions",
        "projection",
        "snapshot",
        "submit_action",
    }
)
"""The closed operation set of the facade (FR-1.2).

Declared here and asserted against the class by a test: adding an operation is then a reviewed
decision with a requirement behind it, rather than a method somebody needed on a Tuesday.
"""

SESSION_ID_PREFIX: Final[str] = "g-"
"""How an assigned session id is spelled. Seat numbers are not part of it: a game is a game."""


class SessionError(Exception):
    """Base class for every facade failure."""


class SessionNotFoundError(SessionError, LookupError):
    """No session is open under that id. A transport turns this into its own not-found answer."""


class SessionExistsError(SessionError, ValueError):
    """That id is already a live session. Two clients must not act on one game by accident."""


class SessionClosedError(SessionError, RuntimeError):
    """The session's record is closed: the game is over, or the session was ended."""


class SessionState(StrEnum):
    """How far a session is through its life. Only a session's own lock may change this."""

    OPEN = "open"
    COMPLETED = "completed"
    ENDED = "ended"


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """One read of a session as it stands: a value, not a handle (K-027).

    This is the *operator's* read, not a player's surface. A driver that has to choose an action
    without a model - a test-only reference seat - needs the position and the decisions that are
    open, and the game's own enumeration is the only thing that can turn those into a legal action.
    The snapshot therefore carries what the facade already owns rather than adding an enumeration
    to the facade: enumeration stays a property of the game and of the assist level, which is what
    keeps an L0 surface from becoming a disguised L2 one.

    It is not served by any transport. There is no HTTP route and no MCP tool or resource over it,
    so a player can never read another player's god view through it (FR-2.6); only in-process code
    the runner itself builds gets that far.
    """

    game: Game
    config: RunConfig
    state: State
    pending: tuple[DecisionRequest, ...]
    outcome: Outcome | None


@dataclass(slots=True)
class _Session:
    """One game in progress: the plugin, the configuration, the run and the lock over them."""

    game: Game
    config: RunConfig
    run: GameRun
    lock: RLock = field(default_factory=RLock)
    state: SessionState = SessionState.OPEN
    outcome: Outcome | None = None


class SessionFacade:
    """The single mutable authority a transport talks to (FR-1.1).

    Deliberately not thread-local and not per-request: one instance serves every seat of every
    session, and the state it holds is the dictionary of sessions, which is the only thing here that
    an operator could not rebuild from a record.
    """

    def __init__(self) -> None:
        self._sessions: dict[GameId, _Session] = {}
        self._lock = Lock()
        self._assigned = 0

    # --- lifecycle --------------------------------------------------------------------------

    def create_session(
        self,
        game: str,
        config: RunConfig,
        *,
        game_id: GameId | None = None,
        directory: Path | None = None,
    ) -> GameId:
        """Open one game and return the id it is known by (FR-1.2).

        'directory' is where the record goes: a session with no directory is played and recorded
        nowhere, which is what an exploration or a test wants and what a scored run never does.
        """
        plugin = get_game(game)
        with self._lock:
            assigned = self._assign(game_id)
            session = _Session(
                game=plugin,
                config=config,
                run=GameRun(plugin, config, game_id=assigned, directory=directory),
            )
            self._sessions[assigned] = session
            return assigned

    def list_sessions(self) -> list[GameId]:
        """The sessions currently open, in a stable order (FR-3.4's sandbox surface).

        A listing, not a second registry: the facade already owns the dictionary, so a transport
        that needs to show an operator what is live asks here rather than remembering what it
        created.
        """
        with self._lock:
            return sorted(self._sessions)

    def end_session(self, session_id: GameId) -> None:
        """Close a session's record and forget it (the abandonment path of FR-7.5).

        Ending a session that has already finished is not an error: the caller asked for the
        session to be over, and it is.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise SessionNotFoundError(f"no session {session_id!r} to end")
        with session.lock:
            if session.state is SessionState.OPEN:
                # No terminal record on purpose: a game that stopped early produced no outcome, and
                # a synthetic verdict would make it indistinguishable from a game that was lost.
                session.run.close()
                # The state is what refuses an operation already waiting on this lock: without it,
                # a submit that lost the race would write into a closed file instead of being told
                # that the session is over.
                session.state = SessionState.ENDED

    # --- reading ----------------------------------------------------------------------------

    def projection(self, session_id: GameId, player: PlayerId) -> Observation:
        """What that seat may see, built by the plugin's own allow-list (FR-1.2, FR-3.8).

        Reading consumes no randomness and mutates nothing, which is what lets a resource be read
        as often as a client likes.
        """
        with self._readable(session_id) as session:
            return session.game.observe(session.run.state, player)

    def pending_decisions(self, session_id: GameId) -> list[DecisionRequest]:
        """The decisions open right now, in the game's own resolution order (FR-1.2)."""
        with self._readable(session_id) as session:
            return session.run.pending

    def decision_surface(self, session_id: GameId, player: PlayerId) -> str:
        """What that seat is shown of the decision in front of it (FR-1.2, FR-4).

        Rendered by v1's one renderer at the level the run was configured for, so the CLI, a
        resource and a prompt cannot disagree about what a player was looking at.
        """
        with self._readable(session_id) as session:
            return render_decision(
                session.game, session.run.state, player, assist=session.config.assist
            )

    def outcome(self, session_id: GameId) -> Outcome | None:
        """The verdict, once the game has one. None while it is in progress or abandoned."""
        with self._readable(session_id) as session:
            return session.outcome

    def snapshot(self, session_id: GameId) -> SessionSnapshot:
        """The session's own position, for an in-process driver that is not a player (K-027).

        Read under the session's lock, so the state, the open decisions and the verdict agree with
        one another: a snapshot cannot mix a position before an action with the verdict after it.
        The copies are values, so the next accepted action cannot change a snapshot a caller holds.
        """
        with self._readable(session_id) as session:
            return SessionSnapshot(
                game=session.game,
                config=session.config,
                state=session.run.state,
                pending=tuple(session.run.pending),
                outcome=session.outcome,
            )

    # --- writing ----------------------------------------------------------------------------

    def submit_action(
        self, session_id: GameId, action: Action, *, request_id: str | None = None
    ) -> ApplyResult:
        """Apply one attempt and return the engine's answer, rejection included (FR-1.6).

        A rejection is an answer, not an exception and not a queue entry: the attempt is recorded,
        the state does not move, and the caller is told the code the engine chose. Answering a
        decision that is not this player's is refused here rather than deferred to whoever acts
        next.
        """
        with self._playing(session_id) as session:
            result = session.run.submit(action, request_id=request_id)
            self._settle(session)
            return result

    # --- internals --------------------------------------------------------------------------

    def _assign(self, requested: GameId | None) -> GameId:
        """The id this session will be known by, refusing a collision.

        Called with the registry lock held, so two creators cannot choose the same id.
        """
        if requested is not None:
            if requested in self._sessions:
                raise SessionExistsError(f"session {requested!r} is already open")
            return requested
        while True:
            self._assigned += 1
            candidate = f"{SESSION_ID_PREFIX}{self._assigned:04d}"
            if candidate not in self._sessions:
                return candidate

    def _session(self, session_id: GameId) -> _Session:
        with self._lock:
            session = self._sessions.get(session_id)
            known = sorted(self._sessions)
        if session is None:
            raise SessionNotFoundError(f"no session {session_id!r}; known sessions are {known}")
        return session

    @contextmanager
    def _readable(self, session_id: GameId) -> Iterator[_Session]:
        """The session under its own lock, for an operation that changes nothing."""
        session = self._session(session_id)
        with session.lock:
            yield session

    @contextmanager
    def _playing(self, session_id: GameId) -> Iterator[_Session]:
        """The session under its own lock, for the one operation that may change the game."""
        session = self._session(session_id)
        with session.lock:
            if session.state is not SessionState.OPEN:
                raise SessionClosedError(
                    f"session {session_id!r} is {session.state.value}; its record is closed to "
                    "further actions"
                )
            yield session

    def _settle(self, session: _Session) -> None:
        """Write the terminal record the moment the game is over. Called with the session locked."""
        if session.state is not SessionState.OPEN:
            return
        if not session.game.is_terminal(session.run.state):
            return
        session.outcome = session.game.outcome(session.run.state)
        session.run.finish()
        session.state = SessionState.COMPLETED
