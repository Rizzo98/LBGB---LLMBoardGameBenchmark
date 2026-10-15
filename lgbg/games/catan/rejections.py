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

NO_DEV_CARDS_REMAINING: Final[RejectionCode] = RejectionCode(
    code="NO_DEV_CARDS_REMAINING",
    description="there are no development cards left to buy",
)
CARD_BOUGHT_THIS_TURN: Final[RejectionCode] = RejectionCode(
    code="CARD_BOUGHT_THIS_TURN",
    description="a development card bought this turn may not be played this turn",
)
ONE_CARD_PER_TURN: Final[RejectionCode] = RejectionCode(
    code="ONE_CARD_PER_TURN", description="a player may play at most one development card a turn"
)
CARD_NOT_PLAYABLE: Final[RejectionCode] = RejectionCode(
    code="CARD_NOT_PLAYABLE",
    description="this card is not one that is played: a victory-point card is revealed, not played",
)
SAME_RESOURCE_TRADE: Final[RejectionCode] = RejectionCode(
    code="SAME_RESOURCE_TRADE",
    description="a trade must exchange one resource for a different one",
)
WRONG_TRADE_RATIO: Final[RejectionCode] = RejectionCode(
    code="WRONG_TRADE_RATIO",
    description="the offered number of cards is not the ratio this player trades at",
)
BANK_LACKS_RESOURCE: Final[RejectionCode] = RejectionCode(
    code="BANK_LACKS_RESOURCE",
    description="the bank does not hold the resource cards the action asks of it",
)
OFFER_NOT_BACKED: Final[RejectionCode] = RejectionCode(
    code="OFFER_NOT_BACKED",
    description="the offer gives resource cards the offerer does not hold",
)
TRADE_ALREADY_OPEN: Final[RejectionCode] = RejectionCode(
    code="TRADE_ALREADY_OPEN",
    description="an offer is already open, and only one offer is open at a time",
)
NO_OPEN_OFFER: Final[RejectionCode] = RejectionCode(
    code="NO_OPEN_OFFER",
    description="there is no open offer to answer or to withdraw",
)
NOT_A_RESPONDER: Final[RejectionCode] = RejectionCode(
    code="NOT_A_RESPONDER",
    description="this player was not asked to answer the open offer",
)
ALREADY_RESPONDED: Final[RejectionCode] = RejectionCode(
    code="ALREADY_RESPONDED", description="this player has already answered the open offer"
)
NOT_AN_ACCEPTOR: Final[RejectionCode] = RejectionCode(
    code="NOT_AN_ACCEPTOR", description="the named partner did not accept the open offer"
)
INSUFFICIENT_RESOURCES: Final[RejectionCode] = RejectionCode(
    code="INSUFFICIENT_RESOURCES",
    description="the other side of a trade does not hold the cards the offer asks of them",
)
NOT_YOUR_SETTLEMENT: Final[RejectionCode] = RejectionCode(
    code="NOT_YOUR_SETTLEMENT",
    description="the vertex does not carry one of the player's own settlements to upgrade",
)
ROBBER_SAME_HEX: Final[RejectionCode] = RejectionCode(
    code="ROBBER_SAME_HEX", description="the robber was sent to the hex it already occupies"
)
ROBBER_ALREADY_MOVED: Final[RejectionCode] = RejectionCode(
    code="ROBBER_ALREADY_MOVED", description="the robber has already moved in this phase"
)
ROBBER_VICTIM_NOT_ADJACENT: Final[RejectionCode] = RejectionCode(
    code="ROBBER_VICTIM_NOT_ADJACENT",
    description="the named victim has no building on the hex the robber occupies",
)

GAME_CODES: Final[tuple[RejectionCode, ...]] = (
    VERTEX_OCCUPIED,
    EDGE_OCCUPIED,
    TOO_CLOSE,
    NOT_CONNECTED,
    NO_PIECES_REMAINING,
    WRONG_DISCARD_TOTAL,
    NOT_ENOUGH_RESOURCES,
    SAME_RESOURCE_TRADE,
    WRONG_TRADE_RATIO,
    BANK_LACKS_RESOURCE,
    OFFER_NOT_BACKED,
    TRADE_ALREADY_OPEN,
    NO_OPEN_OFFER,
    NOT_A_RESPONDER,
    ALREADY_RESPONDED,
    NOT_AN_ACCEPTOR,
    INSUFFICIENT_RESOURCES,
    NO_DEV_CARDS_REMAINING,
    CARD_BOUGHT_THIS_TURN,
    ONE_CARD_PER_TURN,
    CARD_NOT_PLAYABLE,
    NOT_YOUR_SETTLEMENT,
    ROBBER_SAME_HEX,
    ROBBER_ALREADY_MOVED,
    ROBBER_VICTIM_NOT_ADJACENT,
)
"""The codes Catan itself raises, so far. Later slices add their own to this tuple."""

DECLARED_CODES: Final[tuple[RejectionCode, ...]] = GAME_CODES + CORE_REJECTION_CODES
"""Everything a run of this plugin can produce, which is what the declaration must cover."""
