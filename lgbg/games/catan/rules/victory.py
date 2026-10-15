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

from dataclasses import replace
from typing import Final

from lgbg.core.types import Event
from lgbg.games.catan import phases
from lgbg.games.catan.state import CARD_ORDER, NO_OWNER, CatanState, DevCard, Phase

TARGET: Final[int] = 10

ARMY: Final[int] = 3
"""How many played knights the Largest Army card requires (RULES.md 4.11 item 3)."""
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


def largest_army_holder(state: CatanState) -> int:
    """Who holds the Largest Army card, by the algorithm Longest Road also uses (RULES.md 4.11).

    The count is the number of knights a player has *played*, which never goes down: played
    knights stay face up for the rest of the game. That is why the rules can say the "unheld
    after a tie" branch is unreachable here - whoever holds the card has at least three knights
    and can never lose them - and the branch is implemented anyway, because it is the shared
    algorithm and a rule that is skipped is a rule nobody can test.
    """
    counts = {player: state.knights_played[player] for player in range(state.players)}
    best = max(counts.values(), default=0)
    if best < ARMY:
        return NO_OWNER
    tied = sorted(player for player, count in counts.items() if count == best)
    if len(tied) == 1:
        return tied[0]
    return state.largest_army if state.largest_army in tied else NO_OWNER


def recompute_awards(state: CatanState) -> tuple[CatanState, list[Event]]:
    """Award, keep or revoke Largest Army, saying so when it moves (RULES.md 4.11 item 4).

    Longest Road recomputes itself from the road builder, because every road changes it. Largest
    Army is recomputed from the knight, for the same reason, and both are recomputed rather than
    claimed: no action exists for taking an award.
    """
    awarded = largest_army_holder(state)
    if awarded == state.largest_army:
        return state, []
    if awarded == NO_OWNER:
        return (
            replace(state, largest_army=NO_OWNER),
            [Event(type="largest_army_vacated", payload={"player": state.largest_army})],
        )
    return (
        replace(state, largest_army=awarded),
        [
            Event(
                type="largest_army_awarded",
                payload={"player": awarded, "knights": state.knights_played[awarded]},
            )
        ],
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
