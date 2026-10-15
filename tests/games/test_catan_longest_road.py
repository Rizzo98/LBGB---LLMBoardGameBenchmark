"""Longest Road: the award, its transfer, and the search behind it (FR-13.9, FR-13.10; SC-11).

The test matrix below is the one this rule deserves, because every part of it is a classic bug:
a road that branches is not the sum of its branches; a road interrupted by an opponent's
building is two roads; a loop is a continuous road that begins wherever you start counting; and
the card is held by a player rather than owned by the board, so a tie has to leave it, or take
it away, depending on who holds it.

The fixtures build their road networks by walking the board rather than by naming edge numbers,
so the shapes are the shapes the tests describe: a line, a T, a loop, a line with one vertex
taken by somebody else.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.rules.longest_road import MINIMUM, VALUE, holder, recompute, road_length
from lgbg.games.catan.state import NO_OWNER, CatanState
from tests.games.catan_boards import edges_at, holding, layout, vertices_of

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251117


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _run_from(
    state: CatanState, vertex: int, edge: int, edges: int, *, used: frozenset[int] = frozenset()
) -> list[int]:
    """A simple run of this many edges starting at this edge, found by walking the board.

    The fixtures walk the board rather than naming edge numbers, so a test that says "a line of
    six" is a line of six on whatever board the plugin ships.
    """
    found = _extend(state, vertex, edge, edges, frozenset({vertex}), frozenset(used))
    assert found is not None, f"the board has no run of {edges} edges here"
    return found


def _extend(
    state: CatanState,
    vertex: int,
    edge: int,
    needed: int,
    seen: frozenset[int],
    used: frozenset[int],
) -> list[int] | None:
    """Take this edge, then find enough more without repeating a vertex or an edge."""
    if edge in used:
        return None
    first, second = vertices_of(state, edge)
    far = second if first == vertex else first
    if far in seen:
        return None
    if needed == 1:
        return [edge]
    for following in edges_at(state, far):
        if following == edge or following in used:
            continue
        rest = _extend(state, far, following, needed - 1, seen | {far}, used | {edge})
        if rest is not None:
            return [edge, *rest]
    return None


def _line(state: CatanState, edges: int, *, used: frozenset[int] = frozenset()) -> list[int]:
    vertex = vertices_of(state, 0)[0]
    return _run_from(state, vertex, 0, edges, used=used)


def _junction(state: CatanState) -> tuple[int, list[list[int]]]:
    """A vertex with three branches of two roads each: the T that branchers get wrong.

    Found rather than assumed: the first vertex with three edges does not always have two free
    edges beyond each of them, so the helper looks until it finds one that does.
    """
    for middle in range(len(state.placed.cities)):
        if len(edges_at(state, middle)) < 3:
            continue
        used: frozenset[int] = frozenset()
        branches: list[list[int]] = []
        for edge in edges_at(state, middle):
            branch = _extend(state, middle, edge, 2, frozenset({middle}), used)
            if branch is None:
                branches = []
                break
            used = used | frozenset(branch)
            branches.append(branch)
        if branches:
            return middle, branches
    raise AssertionError("this board has no junction with three branches of two roads")


def _loop(state: CatanState, hex_id: int) -> list[int]:
    """The six edges around one hex, which form the smallest loop this board allows.

    Found by asking which vertices of the hex share an edge rather than by assuming the
    topology lists them in boundary order, which it does not.
    """
    around = list(state.board.topology.vertices_of_hex(hex_id))
    edges = {
        edge
        for index, first in enumerate(around)
        for second in around[index + 1 :]
        for edge in edges_at(state, first)
        if second in vertices_of(state, edge)
    }
    assert len(edges) == 6, "a hex is bounded by six edges"
    return sorted(edges)


def _roads(*groups: list[int]) -> list[tuple[int, int]]:
    """One run per seat, so the tests read as "seat 0 has this road and seat 1 has that one"."""
    return [(edge, seat) for seat, group in enumerate(groups) for edge in group]


def _for(seat: int, *groups: list[int]) -> list[tuple[int, int]]:
    """Several runs belonging to one player: branches, or a road and its extension."""
    return [(edge, seat) for group in groups for edge in group]


def test_a_run_of_five_roads_is_a_longest_road() -> None:
    state = layout(_opening(), roads=_roads(_line(_opening(), MINIMUM)))

    assert road_length(state, 0) == MINIMUM
    assert holder(state) == 0
    assert VALUE == 2, "the card is worth two victory points"


def test_four_roads_are_not_enough() -> None:
    state = layout(_opening(), roads=_roads(_line(_opening(), MINIMUM - 1)))

    assert road_length(state, 0) == MINIMUM - 1
    assert holder(state) == NO_OWNER


def test_a_branching_road_is_not_the_sum_of_its_branches() -> None:
    """Six roads in a T are a longest road of four, which is the bug this rule attracts."""
    middle, branches = _junction(_opening())
    state = layout(_opening(), roads=_for(0, *branches))
    assert middle >= 0

    assert sum(len(branch) for branch in branches) == 6
    assert road_length(state, 0) == 4, "a continuous road cannot repeat the junction"
    assert holder(state) == NO_OWNER, "and four is not five"
    assert middle in {
        vertex for branch in branches for edge in branch for vertex in vertices_of(state, edge)
    }


def test_an_opponents_building_breaks_the_road() -> None:
    """RULES.md 4.10 item 3: a building of another colour may be an end but not an interior."""
    state = _opening()
    line = _line(state, 6)
    middle = next(
        vertex for vertex in vertices_of(state, line[2]) if vertex in vertices_of(state, line[3])
    )
    broken = layout(state, roads=_roads(line), settlements=[(middle, 1)])

    assert road_length(broken, 0) == 3, "the two halves are roads of three each"
    assert road_length(broken, 1) == 0, "and a settlement is not a road"


def test_an_opponents_city_breaks_it_too() -> None:
    state = _opening()
    line = _line(state, 6)
    middle = next(
        vertex for vertex in vertices_of(state, line[2]) if vertex in vertices_of(state, line[3])
    )
    broken = layout(state, roads=_roads(line), cities=[(middle, 2)])

    assert road_length(broken, 0) == 3


def test_the_players_own_building_does_not_break_their_road() -> None:
    """S5: "Do my own settlements interrupt my continuous road? No." """
    state = _opening()
    line = _line(state, 6)
    middle = next(
        vertex for vertex in vertices_of(state, line[2]) if vertex in vertices_of(state, line[3])
    )
    mine = layout(state, roads=_roads(line), settlements=[(middle, 0)])

    assert road_length(mine, 0) == 6


def test_a_loop_counts_its_whole_length() -> None:
    """A simple cycle is a continuous road in its own right (RULES.md 4.10 item 2)."""
    state = _opening()
    loop = _loop(state, 0)
    looped = layout(state, roads=_roads(loop))

    assert len(loop) == 6
    assert road_length(looped, 0) == 6


def test_another_players_road_does_not_interrupt_it() -> None:
    """Only buildings interrupt a road: another player's roads are simply not part of it."""
    state = _opening()
    line = _line(state, 5)
    beside = _run_from(state, vertices_of(state, 60)[0], 60, 3)
    crossed = layout(
        _opening(), roads=[(edge, 0) for edge in line] + [(edge, 1) for edge in beside]
    )

    assert road_length(crossed, 0) == 5
    assert road_length(crossed, 1) == 3, "and each player's own roads are counted on their own"


def test_the_award_follows_the_lengths() -> None:
    state = _opening()
    mine = _line(state, 5)
    theirs = _run_from(state, vertices_of(state, 40)[0], 40, 6, used=frozenset(mine))
    assert not set(mine) & set(theirs), "the fixture needs two separate roads"
    board = layout(state, roads=_roads(mine, theirs))

    assert road_length(board, 0) == 5
    assert road_length(board, 1) == 6
    assert holder(board) == 1
    awarded, events = recompute(board)
    assert awarded.longest_road == 1
    assert [event.type for event in events] == ["longest_road_awarded"]
    assert dict(events[0].payload)["length"] == 6


def test_a_tie_leaves_the_card_where_it_is() -> None:
    state = _opening()
    mine = _line(state, 5)
    theirs = _run_from(state, vertices_of(state, 40)[0], 40, 5, used=frozenset(mine))
    board = layout(state, roads=_roads(mine, theirs))
    held = replace(board, longest_road=0)

    assert holder(held) == 0, "the incumbent is one of the tied players"
    assert recompute(held) == (held, [])


def test_a_tie_that_excludes_the_incumbent_takes_the_card_off_the_board() -> None:
    state = _opening()
    mine = _line(state, 5)
    theirs = _run_from(state, vertices_of(state, 40)[0], 40, 5, used=frozenset(mine))
    board = layout(state, roads=_roads(mine, theirs))
    held = replace(board, longest_road=2)

    assert holder(held) == NO_OWNER
    vacated, events = recompute(held)
    assert vacated.longest_road == NO_OWNER
    assert [event.type for event in events] == ["longest_road_vacated"]


def test_a_build_by_another_player_can_take_the_card_away_during_their_turn() -> None:
    """RULES.md 4.10 items 7 and 8: automatic, and not only on the holder's turn."""
    state = _opening()
    line = _line(state, 6)
    middle, spare = next(
        (vertex, free)
        for index in range(len(line) - 1)
        for vertex in vertices_of(state, line[index])
        if vertex in vertices_of(state, line[index + 1])
        for free in edges_at(state, vertex)
        if free not in line
    )
    board = layout(
        state,
        roads=[(edge, 0) for edge in line] + [(spare, 1)],
        turn=1,
    )
    held = replace(board, longest_road=0)
    ready = holding(held, 1, brick=1, wood=1, wool=1, wheat=1)

    built = GAME.apply(
        ready,
        Action(player=1, type=phases.BUILD_SETTLEMENT, params={"vertex": middle}),
        NullRandomSource(),
    )

    assert isinstance(built, Applied)
    assert built.state.longest_road == NO_OWNER, "the road it broke was the longest one"
    assert [event.type for event in built.events][-1] == "longest_road_vacated"


def test_building_the_fifth_road_awards_the_card_in_the_same_action() -> None:
    state = _opening()
    line = _line(state, 5)
    board = layout(state, roads=[(edge, 0) for edge in line[:4]], turn=0)
    ready = holding(board, 0, brick=1, wood=1)

    built = GAME.apply(
        ready,
        Action(player=0, type=phases.BUILD_ROAD, params={"edge": line[4]}),
        NullRandomSource(),
    )

    assert isinstance(built, Applied)
    assert built.state.longest_road == 0
    assert "longest_road_awarded" in [event.type for event in built.events]


def test_re_acquisition_is_immediate_and_remembers_nothing() -> None:
    """RULES.md 4.10 item 9: no priority, no waiting period, no memory of previous holders."""
    state = _opening()
    mine = _line(state, 5)
    theirs = _run_from(state, vertices_of(state, 40)[0], 40, 5, used=frozenset(mine))
    tied = replace(layout(state, roads=_roads(mine, theirs)), longest_road=2)
    vacated, _events = recompute(tied)
    assert vacated.longest_road == NO_OWNER

    longer = layout(state, roads=_roads(_line(state, 6), theirs))

    assert holder(longer) == 0, "the same player, one road longer, holds it again at once"
    assert recompute(longer)[0].longest_road == 0
