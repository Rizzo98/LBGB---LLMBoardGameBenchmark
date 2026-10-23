"""Resources are reads of the one renderer (PRD-v2 FR-3.6 to PRD-v2 FR-3.9).

A resource that rendered the state a second way would be a second game: the same position would
look different to a model and to an operator, and a result would depend on which surface asked.
These tests hold the resource to the game's own renderer, to a game-agnostic URI shape, and to
the purity that makes a read repeatable.
"""

from __future__ import annotations

import re
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextResourceContents

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.mcp.server import McpSurface
from lgbg.core.canonical import to_canonical_json
from lgbg.core.game import get_game
from lgbg.core.log import god_log_path
from lgbg.core.types import Action
from tests.adapters.mcp.support import bound_surface, listed_resources, run
from tests.games.fixture_game import FixtureGame  # noqa: F401

RESOURCE_SHAPE = re.compile(
    r"^[a-z0-9_-]+://sessions/[^/]+/(?:state|decisions|surface)(?:\?player=\d+)?$"
)


async def read(surface: McpSurface, uri: str) -> str:
    async with create_connected_server_and_client_session(surface.server) as client:
        result = await client.read_resource(uri)  # type: ignore[arg-type]
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    return content.text


def test_the_projection_resource_is_the_game_s_own_rendering(tmp_path: Path) -> None:
    """v2 FR-3.9: both see the same bytes, because there is one renderer."""
    surface, facade, game_id = bound_surface(tmp_path / "run")
    game = get_game("fixture")

    text = run(read(surface, f"fixture://sessions/{game_id}/state?player=0"))

    assert text == game.render(facade.projection(game_id, 0))


def test_the_pending_decisions_resource_is_the_facade_s_own_list(tmp_path: Path) -> None:
    """PRD-v2 FR-3.6: a read of the decisions, not a second opinion about them."""
    surface, facade, game_id = bound_surface(tmp_path / "run")

    text = run(read(surface, f"fixture://sessions/{game_id}/decisions"))

    assert text == to_canonical_json(
        [
            {
                "request_id": request.request_id,
                "player": request.player,
                "kind": request.kind,
                "schema_ref": request.schema_ref,
                "context": request.context,
                "phase": request.phase,
            }
            for request in facade.pending_decisions(game_id)
        ]
    )


def test_resource_uris_are_game_agnostic_in_shape(tmp_path: Path) -> None:
    """PRD-v2 FR-3.7: the shape names sessions and state, never a board or a piece."""
    surface, _, _ = bound_surface(tmp_path / "run")

    uris = [str(resource.uri) for resource in run(listed_resources(surface))]
    assert uris, "control: a surface with a live session must advertise its reads"
    assert all(RESOURCE_SHAPE.fullmatch(uri) for uri in uris), uris
    assert all("vertex" not in uri and "settlement" not in uri for uri in uris)


def test_a_catan_projection_is_rendered_by_catan(tmp_path: Path) -> None:
    """v2 FR-3.9 over the awkward game: the board is the game's notation, not JSON the adapter
    made."""
    surface, facade, game_id = bound_surface(tmp_path / "run", game="catan", players=4)
    game = get_game("catan")

    text = run(read(surface, f"catan://sessions/{game_id}/state?player=0"))

    assert text == game.render(facade.projection(game_id, 0))
    assert text != to_canonical_json(facade.projection(game_id, 0))


def test_reading_resources_neither_mutates_nor_consumes_randomness(tmp_path: Path) -> None:
    """FR-3.8: two identical runs stay identical even when one of them is read repeatedly."""
    quiet_dir = tmp_path / "quiet"
    read_dir = tmp_path / "read"
    _quiet, quiet_facade, quiet_id = bound_surface(quiet_dir)
    read_surface, read_facade, read_id = bound_surface(read_dir)
    for _ in range(5):
        run(read(read_surface, f"fixture://sessions/{read_id}/state?player=0"))
        run(read(read_surface, f"fixture://sessions/{read_id}/decisions"))

    for facade, game_id in ((quiet_facade, quiet_id), (read_facade, read_id)):
        facade.submit_action(game_id, Action(player=0, type="gamble", params={}))

    assert (
        god_log_path(quiet_dir, quiet_id).read_bytes()
        == god_log_path(read_dir, read_id).read_bytes()
    )
