"""Board topology, derived from coordinates (PRD-v1 FR-7.1 to FR-7.3, FR-6.10, SC-7).

The board's shape is an emergent fact of the coordinate system, not a table somebody typed.
That matters for a specific reason: a hand-authored adjacency table of 54 vertices and 72
edges is unverifiable by reading, and a single wrong entry is a silent rule error that no
test written against the same table will ever catch.

So the tests below do two things. They pin the counts the rule requires, and they prove the
derivation is real: a different board shape produces a different, still consistent board, and
the order the hexes are enumerated in changes nothing.

Vertex and edge identifiers are frozen by this card. They appear in recorded actions, so
changing the derivation invalidates every existing record (PRD-v1 open question Q3).
"""

from __future__ import annotations

from collections import Counter
from typing import Final

import pytest

from lgbg.games.catan.board.topology import (
    HEX_DIRECTIONS,
    STANDARD_HEXES,
    Axial,
    Topology,
    build_topology,
    check_structure,
    standard_topology,
)

STANDARD: Final[Topology] = standard_topology()


def _run_the_structural_self_check_at_import() -> None:
    """ARCHITECTURE.md section 7.5: the board's self-check runs when the plugin is imported.

    Not only when a test asks for it: a board that is structurally wrong should stop the suite
    at collection, naming the violation, rather than fail one particular assertion.
    """
    violations = check_structure(standard_topology())
    if violations:
        raise AssertionError("the derived board is unsound: " + "; ".join(violations))


_run_the_structural_self_check_at_import()

# Verified independently of the implementation: Euler characteristic V - E + H = 1, and the
# handshake counts from the classification. See the module docstring for the derivation.
EXPECTED_HEXES: Final[int] = 19
EXPECTED_VERTICES: Final[int] = 54
EXPECTED_EDGES: Final[int] = 72
EXPECTED_VERTEX_CLASSES: Final[Counter[int]] = Counter({3: 24, 2: 12, 1: 18})
EXPECTED_EDGE_CLASSES: Final[Counter[int]] = Counter({2: 42, 1: 30})
EXPECTED_DEGREES: Final[Counter[int]] = Counter({3: 36, 2: 18})


def test_the_standard_board_is_a_hexagon_of_side_three() -> None:
    distances = {max(abs(hex_.q), abs(hex_.r), abs(hex_.q + hex_.r)) for hex_ in STANDARD_HEXES}

    assert len(STANDARD_HEXES) == EXPECTED_HEXES
    assert len(set(STANDARD_HEXES)) == EXPECTED_HEXES
    assert distances == {0, 1, 2}, "a filled hexagon: the centre, a ring at 1 and a ring at 2"


def test_the_board_derives_the_counts_the_rule_requires() -> None:
    """FR-7.2, SC-7: 19 hexes, 54 vertices, 72 edges."""
    assert len(STANDARD.hexes) == EXPECTED_HEXES
    assert len(STANDARD.vertices) == EXPECTED_VERTICES
    assert len(STANDARD.edges) == EXPECTED_EDGES


def test_identifiers_are_dense_and_in_canonical_order() -> None:
    """FR-7.3: ids come from a canonical sort of the derived coordinates, not from enumeration."""
    assert [hex_.id for hex_ in STANDARD.hexes] == list(range(EXPECTED_HEXES))
    assert [vertex.id for vertex in STANDARD.vertices] == list(range(EXPECTED_VERTICES))
    assert [edge.id for edge in STANDARD.edges] == list(range(EXPECTED_EDGES))


def test_hex_identifiers_run_row_by_row_from_the_top() -> None:
    """The documented order for hexes: by row, then by column."""
    keys = [(hex_.axial.r, hex_.axial.q) for hex_ in STANDARD.hexes]

    assert keys == sorted(keys)


def test_edge_identifiers_follow_their_endpoints() -> None:
    keys = [edge.vertices for edge in STANDARD.edges]

    assert keys == sorted(keys), "an edge is ordered by its two vertex ids"


def test_the_derivation_does_not_depend_on_enumeration_order() -> None:
    """A hand-authored table would produce the same board; a derivation must not care."""
    shuffled = build_topology(list(reversed(STANDARD_HEXES)))

    assert [hex_.axial for hex_ in shuffled.hexes] == [hex_.axial for hex_ in STANDARD.hexes]
    assert [vertex.hexes for vertex in shuffled.vertices] == [
        vertex.hexes for vertex in STANDARD.vertices
    ]
    assert [edge.vertices for edge in shuffled.edges] == [edge.vertices for edge in STANDARD.edges]


def test_a_different_board_shape_is_derived_rather_than_tabulated() -> None:
    """Seven hexes is a board nobody wrote a table for, and it still has to be consistent."""
    small = build_topology([hex_ for hex_ in STANDARD_HEXES if hex_.distance(Axial(0, 0)) <= 1])

    assert len(small.hexes) == 7
    assert check_structure(small) == []
    assert len(small.vertices) != EXPECTED_VERTICES


def test_every_hex_has_six_vertices_and_six_edges() -> None:
    for hex_ in STANDARD.hexes:
        assert len(STANDARD.vertices_of_hex(hex_.id)) == 6
        assert len(STANDARD.edges_of_hex(hex_.id)) == 6
        assert len(set(STANDARD.vertices_of_hex(hex_.id))) == 6
        assert len(set(STANDARD.edges_of_hex(hex_.id))) == 6


def test_every_edge_joins_two_vertices_and_one_or_two_hexes() -> None:
    for edge in STANDARD.edges:
        assert len(set(edge.vertices)) == 2, "an edge has two distinct endpoints"
        assert 1 <= len(edge.hexes) <= 2, "an edge is shared by at most two hexes"


def test_adjacency_is_symmetric() -> None:
    """FR-7.2: if A is adjacent to B then B is adjacent to A, on every relation."""
    for vertex in STANDARD.vertices:
        for edge_id in STANDARD.edges_at(vertex.id):
            assert vertex.id in STANDARD.vertices_of_edge(edge_id)
        for hex_id in vertex.hexes:
            assert vertex.id in STANDARD.vertices_of_hex(hex_id)

    for edge in STANDARD.edges:
        for vertex_id in edge.vertices:
            assert edge.id in STANDARD.edges_at(vertex_id)
        for hex_id in edge.hexes:
            assert edge.id in STANDARD.edges_of_hex(hex_id)


def test_hex_adjacency_is_symmetric() -> None:
    for hex_ in STANDARD.hexes:
        for neighbour in STANDARD.neighbouring_hexes(hex_.id):
            assert hex_.id in STANDARD.neighbouring_hexes(neighbour)


def test_the_vertex_classification_matches_the_geometry() -> None:
    """24 vertices where three hexes meet, 12 where two do, 18 at a corner of the board."""
    classes = Counter(len(vertex.hexes) for vertex in STANDARD.vertices)

    assert classes == EXPECTED_VERTEX_CLASSES
    assert sum(1 for vertex in STANDARD.vertices if vertex.is_coastal) == 30


def test_the_edge_classification_matches_the_geometry() -> None:
    """42 edges shared by two hexes, 30 on the coast - the coast is where ports go."""
    classes = Counter(len(edge.hexes) for edge in STANDARD.edges)

    assert classes == EXPECTED_EDGE_CLASSES
    assert sum(1 for edge in STANDARD.edges if edge.is_coastal) == 30


def test_the_degree_distribution_matches_the_geometry() -> None:
    degrees = Counter(len(vertex.edges) for vertex in STANDARD.vertices)

    assert degrees == EXPECTED_DEGREES
    assert all(degree in {2, 3} for degree in degrees)


def test_the_structural_self_check_passes_on_the_standard_board() -> None:
    """FR-6.10: the check the plugin declares, run as a test."""
    assert check_structure(STANDARD) == []


def test_the_structural_self_check_has_teeth() -> None:
    """A self-check that cannot fail is decoration, so break the board and watch it report."""
    sabotaged = Topology(
        hexes=STANDARD.hexes,
        vertices=STANDARD.vertices,
        edges=STANDARD.edges[:-1],
    )

    violations = check_structure(sabotaged)

    assert violations, "dropping an edge must be reported"
    assert any("edge" in violation for violation in violations)


def test_hex_directions_are_six_distinct_neighbours() -> None:
    assert len(HEX_DIRECTIONS) == 6
    assert len(set(HEX_DIRECTIONS)) == 6
    assert all(
        Axial(0, 0).neighbour(index) == direction for index, direction in enumerate(HEX_DIRECTIONS)
    )
    assert all(
        direction.q + direction.r + (-direction.q - direction.r) == 0
        for direction in HEX_DIRECTIONS
    )


@pytest.mark.parametrize("radius", [1, 2, 3])
def test_the_euler_characteristic_holds_for_any_hexagonal_board(radius: int) -> None:
    """V - E + H = 1 for a hexagon; a derivation that lost a vertex would break it."""
    board = build_topology(_hexagon(radius))

    assert len(board.hexes) == 3 * radius * (radius + 1) + 1, "a hexagon of radius r has 3r^2+3r+1"
    assert len(board.vertices) - len(board.edges) + len(board.hexes) == 1
    assert check_structure(board) == []


def _hexagon(radius: int) -> list[Axial]:
    return [
        Axial(q, r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if abs(q + r) <= radius
    ]
