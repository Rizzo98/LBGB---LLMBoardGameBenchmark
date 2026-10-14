"""Board layout, ports and number tokens (PRD-v1 FR-7.4 to FR-7.6; RULES.md section 4.1, 4.2).

The rules pin more than a composition here. The number tokens go on in a fixed sequence along
a spiral walk that starts at a corner, and the sequence has a property the rulebook only asks
for in prose: no two red numbers (6 and 8) may end up adjacent. The tests below check that
property for *every* desert position and *every* starting corner - 114 boards - because a
sequence that works for one arrangement and fails for another is not a pinned sequence.

Loading a fixed board must consume no randomness: comparability across runs is the point of
having fixed boards at all (ARCHITECTURE.md section 7.6).
"""

from __future__ import annotations

from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest

from lgbg.core.rng import KIND_CHOICE, KIND_SHUFFLE, SeededRandomSource
from lgbg.games.catan.board.generation import (
    BOARD_NUMBER_CORNER,
    BOARD_NUMBER_SHUFFLE,
    BOARD_PORT_SHUFFLE,
    BOARD_TERRAIN_SHUFFLE,
    NUMBER_RANDOM,
    NUMBER_SPIRAL,
    NUMBER_SPIRAL_NO_ADJACENT_RED,
    TOKEN_SEQUENCE,
    BoardGenerationError,
    board_from_selector,
    coastal_edge_ring,
    corner_hex_ids,
    load_board,
    place_tokens_spiral,
    random_board,
    repair_adjacent_reds,
    spiral_walk,
)
from lgbg.games.catan.board.layout import (
    CANONICAL_TERRAINS,
    CANONICAL_TOKENS,
    Board,
    Resource,
    Terrain,
    check_board,
)
from lgbg.games.catan.board.topology import Topology, standard_topology

STANDARD: Final[Topology] = standard_topology()
RED_NUMBERS: Final[frozenset[int]] = frozenset({6, 8})


def _terrain_with_desert_at(position: int) -> tuple[Terrain, ...]:
    faces = list(CANONICAL_TERRAINS)
    faces.remove(Terrain.DESERT)
    faces.insert(position, Terrain.DESERT)
    return tuple(faces)


def _adjacent_reds(topology: Topology, tokens: tuple[int | None, ...]) -> list[tuple[int, int]]:
    reds = [hex_id for hex_id, token in enumerate(tokens) if token in RED_NUMBERS]
    return [
        (first, second)
        for first in reds
        for second in reds
        if second > first and second in topology.neighbouring_hexes(first)
    ]


def test_the_spiral_walk_visits_every_hex_exactly_once() -> None:
    walk = spiral_walk(STANDARD, corner_hex_ids(STANDARD)[0])

    assert len(walk) == len(STANDARD.hexes)
    assert sorted(walk) == [hex_.id for hex_ in STANDARD.hexes]


@pytest.mark.parametrize("corner_index", range(6))
def test_the_spiral_walk_is_contiguous_from_every_corner(corner_index: int) -> None:
    """RULES.md 4.2 item 3: every consecutive pair of hexes in the walk is adjacent."""
    corner = corner_hex_ids(STANDARD)[corner_index]
    walk = spiral_walk(STANDARD, corner)

    assert walk[0] == corner
    for first, second in pairwise(walk):
        assert second in STANDARD.neighbouring_hexes(first), f"{first} -> {second}"


def test_the_coastal_ring_visits_every_coastal_edge_once() -> None:
    """Ports are spread around this ring, so the ring itself has to be right."""
    ring = coastal_edge_ring(STANDARD)
    coastal = [edge.id for edge in STANDARD.edges if edge.is_coastal]

    assert sorted(ring) == sorted(coastal)
    for first, second in zip(ring, ring[1:] + ring[:1], strict=True):
        shared = set(STANDARD.vertices_of_edge(first)) & set(STANDARD.vertices_of_edge(second))
        assert shared, f"consecutive coastal edges {first} and {second} must share a vertex"


def test_the_six_corners_are_the_outer_ring_corners() -> None:
    corners = corner_hex_ids(STANDARD)

    assert len(corners) == 6
    assert len(set(corners)) == 6
    assert corners == tuple(sorted(corners)), "canonical order is by hex identifier"


def test_spiral_placement_follows_the_pinned_sequence_skipping_the_desert() -> None:
    terrain = _terrain_with_desert_at(0)
    tokens = place_tokens_spiral(STANDARD, terrain, corner_hex_ids(STANDARD)[0])

    assert tokens[0] is None, "the desert never receives a token"
    walk = spiral_walk(STANDARD, corner_hex_ids(STANDARD)[0])
    placed = [tokens[hex_id] for hex_id in walk if hex_id != 0]

    assert tuple(placed) == TOKEN_SEQUENCE


@pytest.mark.parametrize("desert", range(19))
def test_no_red_numbers_are_adjacent_for_any_desert_position(desert: int) -> None:
    """RULES.md 4.2 item 8: all six corners times all nineteen desert positions."""
    terrain = _terrain_with_desert_at(desert)

    for corner in corner_hex_ids(STANDARD):
        tokens = place_tokens_spiral(STANDARD, terrain, corner)

        assert _adjacent_reds(STANDARD, tokens) == [], f"desert {desert}, corner {corner}"


def test_the_adjacency_repair_removes_an_adjacent_pair() -> None:
    """A curated board that arrived with one defective pair must be repaired, not shipped.

    The construction is deliberate: one red token is moved next to another, in a place where
    no *other* red can see it, so the board has exactly one conflict - which is what a
    defective curated board looks like.
    """
    terrain = _terrain_with_desert_at(0)
    start = corner_hex_ids(STANDARD)[0]
    walk = spiral_walk(STANDARD, start)
    tokens = list(place_tokens_spiral(STANDARD, terrain, start))

    victim = next(hex_id for hex_id in walk if tokens[hex_id] in RED_NUMBERS)
    neighbour = next(
        hex_id
        for hex_id in STANDARD.neighbouring_hexes(victim)
        if tokens[hex_id] not in RED_NUMBERS
        and not any(
            tokens[other] in RED_NUMBERS
            for other in STANDARD.neighbouring_hexes(hex_id)
            if other != victim
        )
    )
    donor = next(
        hex_id
        for hex_id in walk
        if tokens[hex_id] in RED_NUMBERS
        and hex_id != victim
        and neighbour not in STANDARD.neighbouring_hexes(hex_id)
    )
    tokens[neighbour], tokens[donor] = tokens[donor], tokens[neighbour]

    assert len(_adjacent_reds(STANDARD, tuple(tokens))) == 1, "exactly one conflict to repair"

    repaired = repair_adjacent_reds(STANDARD, tuple(tokens), walk)

    assert _adjacent_reds(STANDARD, repaired) == []
    assert Counter(repaired) == Counter(tokens), "a repair swaps tokens; it never invents one"


def test_the_adjacency_repair_fails_loudly_rather_than_shipping_a_defective_board() -> None:
    """With no non-red hex to swap with, the repair must refuse, not loop or give up quietly."""
    terrain = _terrain_with_desert_at(0)
    start = corner_hex_ids(STANDARD)[0]
    walk = spiral_walk(STANDARD, start)
    every_hex_red: tuple[int | None, ...] = tuple(
        None if terrain[hex_id] is Terrain.DESERT else 6 for hex_id in range(len(STANDARD.hexes))
    )

    with pytest.raises(BoardGenerationError, match="red"):
        repair_adjacent_reds(STANDARD, every_hex_red, walk)


def test_a_random_board_consumes_exactly_the_pinned_draws() -> None:
    source = SeededRandomSource(1)

    random_board(source, number_placement=NUMBER_SPIRAL_NO_ADJACENT_RED, name="random")

    assert [(draw.purpose, draw.kind) for draw in source.draws()] == [
        (BOARD_TERRAIN_SHUFFLE, KIND_SHUFFLE),
        (BOARD_NUMBER_CORNER, KIND_CHOICE),
        (BOARD_PORT_SHUFFLE, KIND_SHUFFLE),
    ]


def test_random_number_placement_draws_a_shuffle_instead_of_a_corner() -> None:
    source = SeededRandomSource(2)

    random_board(source, number_placement=NUMBER_RANDOM, name="random")

    assert [draw.purpose for draw in source.draws()] == [
        BOARD_TERRAIN_SHUFFLE,
        BOARD_NUMBER_SHUFFLE,
        BOARD_PORT_SHUFFLE,
    ]


def test_a_random_board_is_sound_and_reproducible() -> None:
    first = random_board(SeededRandomSource(7), number_placement=NUMBER_SPIRAL, name="random")
    second = random_board(SeededRandomSource(7), number_placement=NUMBER_SPIRAL, name="random")

    assert check_board(first) == []
    assert first.terrain == second.terrain
    assert first.tokens == second.tokens
    assert first.ports == second.ports


@pytest.mark.parametrize("placement", [NUMBER_SPIRAL, NUMBER_SPIRAL_NO_ADJACENT_RED, NUMBER_RANDOM])
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_every_generated_board_satisfies_the_composition(seed: int, placement: str) -> None:
    board = random_board(SeededRandomSource(seed), number_placement=placement, name="random")

    assert check_board(board) == []
    assert _adjacent_reds(STANDARD, board.tokens) == []


def test_the_terrain_composition_is_the_pinned_one() -> None:
    board = load_board("standard_a")

    assert Counter(board.terrain) == Counter(
        {
            Terrain.FOREST: 4,
            Terrain.PASTURE: 4,
            Terrain.FIELD: 4,
            Terrain.HILLS: 3,
            Terrain.MOUNTAINS: 3,
            Terrain.DESERT: 1,
        }
    )


def test_a_fixed_board_loads_from_data_and_is_sound() -> None:
    board = load_board("standard_a")

    placed = [token for token in board.tokens if token is not None]

    assert board.name == "fixed:standard_a"
    assert check_board(board) == []
    assert Counter(placed) == Counter(CANONICAL_TOKENS)
    assert board.tokens[board.desert_hex] is None


def test_a_fixed_board_consumes_no_randomness() -> None:
    """ARCHITECTURE.md 7.6: fixed boards are the default because comparability is the point."""
    source = SeededRandomSource(99)

    board = board_from_selector("fixed:standard_a", rng=source, number_placement=NUMBER_SPIRAL)

    assert source.draws() == []
    assert board.name == "fixed:standard_a"


def test_the_curated_board_keeps_the_properties_its_rationale_claims() -> None:
    """A rationale nobody checks is marketing; these are the two constraints it names."""
    board = load_board("standard_a")
    centre = next(hex_.id for hex_ in STANDARD.hexes if hex_.axial.q == 0 and hex_.axial.r == 0)

    assert board.desert_hex == centre, "the robber starts in the middle of the board"
    for hex_id, terrain in enumerate(board.terrain):
        if terrain is Terrain.DESERT:
            continue
        for neighbour in STANDARD.neighbouring_hexes(hex_id):
            assert board.terrain[neighbour] is not terrain, (
                f"hexes {hex_id} and {neighbour} are adjacent and both {terrain}"
            )


def test_the_curated_port_edges_are_evenly_spread_around_the_coast() -> None:
    board = load_board("standard_a")
    ring = coastal_edge_ring(STANDARD)
    positions = sorted(ring.index(port.edge) for port in board.ports)
    gaps = [
        (following - current) % len(ring)
        for current, following in pairwise(positions + positions[:1])
    ]

    assert set(gaps) <= {3, 4}, f"the harbour edges are unevenly spread: gaps {gaps}"


def test_the_ports_are_nine_coastal_edges_with_the_pinned_mix() -> None:
    board = load_board("standard_a")
    edges = {port.edge for port in board.ports}

    assert len(board.ports) == 9
    assert len(edges) == 9
    assert all(board.topology.edges[edge].is_coastal for edge in edges), "ports sit on the coast"
    assert Counter(port.ratio for port in board.ports) == Counter({3: 4, 2: 5})
    assert {port.resource for port in board.ports if port.ratio == 2} == set(Resource)


def test_the_selector_chooses_between_a_curated_board_and_a_generated_one() -> None:
    fixed = board_from_selector(
        "fixed:standard_a", rng=SeededRandomSource(1), number_placement=NUMBER_SPIRAL
    )
    generated = board_from_selector(
        "random", rng=SeededRandomSource(1), number_placement=NUMBER_SPIRAL
    )

    assert fixed.name.startswith("fixed:")
    assert generated.name == "random"
    assert fixed.terrain != generated.terrain or fixed.ports != generated.ports


def test_an_unknown_board_selector_is_rejected() -> None:
    with pytest.raises(ValueError, match="no_such_board"):
        board_from_selector(
            "fixed:no_such_board", rng=SeededRandomSource(1), number_placement=NUMBER_SPIRAL
        )

    with pytest.raises(ValueError, match="sideways"):
        board_from_selector("sideways", rng=SeededRandomSource(1), number_placement=NUMBER_SPIRAL)


def test_an_unknown_number_placement_is_rejected() -> None:
    with pytest.raises(ValueError, match="backwards"):
        random_board(SeededRandomSource(1), number_placement="backwards", name="random")


def test_the_board_check_has_teeth() -> None:
    """A check that cannot fail would let a defective curated board become the reference."""
    board = load_board("standard_a")
    broken = Board(
        name=board.name,
        topology=board.topology,
        terrain=board.terrain,
        tokens=(*board.tokens[:-1], 7),
        ports=board.ports,
        token_start_hex=board.token_start_hex,
    )

    violations = check_board(broken)

    assert violations
    assert any("token" in violation for violation in violations)


def test_the_board_data_file_is_json_and_says_how_it_was_chosen() -> None:
    """Curated data carries its rationale, or the next person cannot judge it."""
    import json

    data = json.loads(
        (Path("lgbg/games/catan/board/boards/standard_a.json")).read_text(encoding="utf-8")
    )

    assert data["name"] == "standard_a"
    assert len(data["terrain"]) == 19
    assert len(data["ports"]) == 9
    assert data["rationale"]
    assert data["number_start_hex"] in range(19)


def test_the_board_draws_carry_the_pinned_kinds_and_arguments() -> None:
    """RULES.md 3.1: D1 over 19 terrain faces, D3 over 18 tokens, D4 over 9 port faces."""
    source = SeededRandomSource(3)

    random_board(source, number_placement=NUMBER_RANDOM, name="random")

    assert [(draw.purpose, draw.kind, dict(draw.args)) for draw in source.draws()] == [
        (BOARD_TERRAIN_SHUFFLE, KIND_SHUFFLE, {"n": 19}),
        (BOARD_NUMBER_SHUFFLE, KIND_SHUFFLE, {"n": 18}),
        (BOARD_PORT_SHUFFLE, KIND_SHUFFLE, {"n": 9}),
    ]
