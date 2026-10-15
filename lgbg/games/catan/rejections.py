"""The rejection codes the Catan plugin declares (RULES.md section 4; FR-6.8, FR-11.7).

Declaring codes is what lets the runtime and the metrics layer enumerate them without knowing
the game, which makes the *distribution* of rejections a game-agnostic metric: an illegal-move
rate by code, comparable across games. A rule that can fail silently is a rule nobody can
measure, so each of these is the specific reason a placement was refused, not a general
"illegal move".

The core codes are included because the runtime raises them too - an action after termination,
a request that is not open, a schema violation - and the fuzz audit of K-063 compares every
code seen in a fuzz run against this declaration. A code the runtime can raise is a code the
plugin must declare, or the audit fails on the runtime's own behaviour.
"""

from __future__ import annotations

from typing import Final

from lgbg.core.errors import CORE_REJECTION_CODES, RejectionCode

VERTEX_OCCUPIED: Final[RejectionCode] = RejectionCode(
    code="VERTEX_OCCUPIED", description="the vertex already carries a settlement or a city"
)
EDGE_OCCUPIED: Final[RejectionCode] = RejectionCode(
    code="EDGE_OCCUPIED", description="the edge already carries a road"
)
TOO_CLOSE: Final[RejectionCode] = RejectionCode(
    code="TOO_CLOSE",
    description="an adjacent vertex carries a building, and the distance rule forbids it",
)
NOT_CONNECTED: Final[RejectionCode] = RejectionCode(
    code="NOT_CONNECTED", description="the piece does not attach to the network it must attach to"
)
NO_PIECES_REMAINING: Final[RejectionCode] = RejectionCode(
    code="NO_PIECES_REMAINING", description="the player has no piece of that kind left in supply"
)

WRONG_DISCARD_TOTAL: Final[RejectionCode] = RejectionCode(
    code="WRONG_DISCARD_TOTAL",
    description="the forced discard does not return exactly half the hand, rounded down",
)
NOT_ENOUGH_RESOURCES: Final[RejectionCode] = RejectionCode(
    code="NOT_ENOUGH_RESOURCES",
    description="the player does not hold the resource cards the action spends or returns",
)

ROBBER_SAME_HEX: Final[RejectionCode] = RejectionCode(
    code="ROBBER_SAME_HEX", description="the robber was sent to the hex it already occupies"
)
ROBBER_ALREADY_MOVED: Final[RejectionCode] = RejectionCode(
    code="ROBBER_ALREADY_MOVED", description="the robber has already moved in this phase"
)

GAME_CODES: Final[tuple[RejectionCode, ...]] = (
    VERTEX_OCCUPIED,
    EDGE_OCCUPIED,
    TOO_CLOSE,
    NOT_CONNECTED,
    NO_PIECES_REMAINING,
    WRONG_DISCARD_TOTAL,
    NOT_ENOUGH_RESOURCES,
    ROBBER_SAME_HEX,
    ROBBER_ALREADY_MOVED,
)
"""The codes Catan itself raises, so far. Later slices add their own to this tuple."""

DECLARED_CODES: Final[tuple[RejectionCode, ...]] = GAME_CODES + CORE_REJECTION_CODES
"""Everything a run of this plugin can produce, which is what the declaration must cover."""
