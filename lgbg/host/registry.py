"""The host's session registry: which id names which game (PRD-v2 FR-2.4).

The facade owns the only mutable game state and already assigns ids. This is the host's table
*over* that authority: it records the game a session id belongs to, refuses an id that is not a
legal path segment, and refuses a second claim on an id that is live. Two clients therefore
cannot create, or act on, "the same" session under different assumptions - the id is allocated
once, and the game behind it is recorded at that moment.

The registry holds no game state. Every operation it exposes is either a validation or a call to
the facade; that separation is what keeps the facade the single authority (FR-1.1) while still
giving the host a place to answer "what is live, and what is it?".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Final

from lgbg.core.config import RunConfig
from lgbg.core.types import GameId
from lgbg.host.facade import SessionFacade, SessionNotFoundError

SESSION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
"""An id is a path segment: letters, digits, dot, dash, underscore, and not empty."""


class InvalidSessionIdError(ValueError):
    """The requested id cannot be a session id, so it never reaches the facade."""


@dataclass(frozen=True, slots=True)
class Registration:
    """One live session, as the host lists it."""

    session_id: GameId
    game: str


class SessionRegistry:
    """The host's live-session table over the facade (FR-2.4)."""

    def __init__(self, facade: SessionFacade) -> None:
        self._facade = facade
        self._games: dict[GameId, str] = {}
        self._lock = Lock()

    def create(
        self,
        game: str,
        config: RunConfig,
        *,
        game_id: GameId | None = None,
        directory: Path | None = None,
    ) -> GameId:
        """Open a session and remember the game it names.

        The id is assigned by the facade when not requested; either way, the mapping is written
        before another caller can observe the session, so a listing never shows an id whose game
        is not yet known.
        """
        if game_id is not None:
            self._validate(game_id)
        with self._lock:
            assigned = self._facade.create_session(
                game, config, game_id=game_id, directory=directory
            )
            self._games[assigned] = game
            return assigned

    def game_of(self, session_id: GameId) -> str:
        """The game this id names, or a not-found error that names the live ids."""
        self._validate(session_id)
        with self._lock:
            game = self._games.get(session_id)
            known = sorted(self._games)
        if game is None:
            raise SessionNotFoundError(f"no session {session_id!r}; known sessions are {known}")
        return game

    def sessions(self) -> list[GameId]:
        """The live session ids, in a stable order."""
        with self._lock:
            return sorted(self._games)

    def entries(self) -> list[Registration]:
        """The live sessions with the game each one names, in a stable order."""
        with self._lock:
            return [
                Registration(session_id=session_id, game=self._games[session_id])
                for session_id in sorted(self._games)
            ]

    def end(self, session_id: GameId) -> None:
        """Close a session through the facade and forget it."""
        self._validate(session_id)
        with self._lock:
            self._facade.end_session(session_id)
            self._games.pop(session_id, None)

    def _validate(self, session_id: str) -> None:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise InvalidSessionIdError(
                f"session id {session_id!r} must match {SESSION_ID_PATTERN.pattern}"
            )
