"""Victory: what a position is worth, and when the game ends (RULES.md 4.13; PRD-v1 FR-15.1, 15.2).

Five terms, summed: a settlement is one point, a city two, a victory-point card one, and each of
the two special cards two. The total is *true* rather than public - it counts victory-point cards
in a hand whether or not anybody has seen them - because it is the number the game ends on. What
other players may compute is a different number, and it belongs to the projection (FR-16.4).

The timing is the interesting half. The condition is tested after every transition and at the
start of a turn, and it is applied to the player *whose turn it is*: a player who reaches ten
while somebody else is playing has not won yet. That is not a technicality - the only way it
happens is the Longest Road card changing hands when an opponent's settlement breaks a road - and
the rulebook is explicit that such a player waits for their own turn, where they win before
rolling a die.
"""

from __future__ import annotations

from typing import Final

from lgbg.core.types import Event
from lgbg.games.catan import phases
from lgbg.games.catan.state import CARD_ORDER, NO_OWNER, CatanState, DevCard, Phase

TARGET: Final[int] = 10
"""The number of victory points that ends the game (RULES.md 4.13 item 4)."""

POINTS: Final[dict[str, int]] = {
    "settlement": 1,
    "city": 2,
    DevCard.VICTORY_POINT.value: 1,
    "longest_road": 2,
    "largest_army": 2,
}
"""The five terms of PRD-v1 Appendix A, named the way the record names them."""

CARD: Final[int] = CARD_ORDER.index(DevCard.VICTORY_POINT)


def victory_points(state: CatanState, player: int) -> int:
    """Every point this player has, revealed or not (RULES.md 4.13 items 1 and 2)."""
    settlements = sum(1 for seat in state.placed.settlements if seat == player)
    cities = sum(1 for seat in state.placed.cities if seat == player)
    return (
        settlements * POINTS["settlement"]
        + cities * POINTS["city"]
        + state.dev_cards[player][CARD] * POINTS[DevCard.VICTORY_POINT.value]
        + (POINTS["longest_road"] if state.longest_road == player else 0)
        + (POINTS["largest_army"] if state.largest_army == player else 0)
    )


def public_points(state: CatanState, player: int) -> int:
    """What other players can compute about this player, which is not their true total (FR-16.4).

    A victory-point card is worth a point to its owner and nothing to anybody else until it is
    revealed, and revealing is not an action - it happens only as a consequence of winning
    (RULES.md 4.13 item 3). So the public total is the true total less the cards nobody has seen,
    and the difference between the two numbers is the whole of what makes "who is winning" a
    question a player has to reason about rather than read off the table.
    """
    return victory_points(state, player) - state.dev_cards[player][CARD]


def check(state: CatanState) -> tuple[CatanState, list[Event]]:
    """End the game if the player to move has reached the target (RULES.md 4.13 items 4 to 6).

    Off-turn totals are deliberately not consulted: a player who reached ten during somebody
    else's turn is not the winner yet, and the only way to become one is for the turn to reach
    them, which is the next check after the turn ends.
    """
    if state.phase is Phase.TERMINAL:
        return state, []
    player = state.turn
    if player == NO_OWNER or not 0 <= player < state.players:
        return state, []
    total = victory_points(state, player)
    if total < TARGET:
        return state, []
    won, announced = phases.begin(state, Phase.TERMINAL)
    return won, [
        Event(type="game_won", payload={"player": player, "points": total, "target": TARGET}),
        *announced,
    ]
