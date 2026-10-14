"""The error model (ARCHITECTURE.md section 10).

Rejections are not exceptions. 'apply' returns a Rejected result; an exception is a bug in
the engine, and a fuzzer that hits one has found a defect. Keeping the two apart is what
makes the illegal-move rate measurable, and every rejection is a first-class logged record
whose state hash is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from lgbg.core.types import JsonValue


@dataclass(frozen=True, slots=True)
class RejectionCode:
    """A rejection code and what it means, declared by the runtime or by a plugin.

    Declaring codes is what lets the runtime and the metrics layer enumerate them without
    knowing the game, so rejection-code distribution is a game-agnostic metric.
    """

    code: str
    description: str

    def __str__(self) -> str:
        return self.code


NOT_YOUR_DECISION: Final[RejectionCode] = RejectionCode(
    code="NOT_YOUR_DECISION", description="the action names a player with no open decision"
)
NO_SUCH_REQUEST: Final[RejectionCode] = RejectionCode(
    code="NO_SUCH_REQUEST", description="the referenced decision request is not open"
)
WRONG_PHASE: Final[RejectionCode] = RejectionCode(
    code="WRONG_PHASE", description="the action is not valid in the current phase"
)
GAME_OVER: Final[RejectionCode] = RejectionCode(
    code="GAME_OVER", description="the game has already terminated"
)
UNKNOWN_ACTION: Final[RejectionCode] = RejectionCode(
    code="UNKNOWN_ACTION", description="the action type is not declared by the game's schema"
)
BAD_PARAMS: Final[RejectionCode] = RejectionCode(
    code="BAD_PARAMS", description="the action's parameters do not validate against the schema"
)
SCHEMA_VERSION_MISMATCH: Final[RejectionCode] = RejectionCode(
    code="SCHEMA_VERSION_MISMATCH", description="the game schema and the record disagree"
)

CORE_REJECTION_CODES: Final[tuple[RejectionCode, ...]] = (
    NOT_YOUR_DECISION,
    NO_SUCH_REQUEST,
    WRONG_PHASE,
    GAME_OVER,
    UNKNOWN_ACTION,
    BAD_PARAMS,
    SCHEMA_VERSION_MISMATCH,
)
"""Lifecycle and protocol conditions that exist independently of any game."""


@dataclass(frozen=True, slots=True)
class Rejection:
    """A refused action. 'details' is structured, never prose-only, and always recorded."""

    code: RejectionCode
    message: str
    details: Mapping[str, JsonValue]
