"""The host's session registry (PRD-v2 FR-2.4).

The facade already keeps the dictionary of live sessions; the registry is the host's table over
it. It assigns an id through the authority, remembers which game that id names, refuses a second
claim on the same id, and refuses an id that is not a legal path segment before it can become one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tests.games.fixture_game  # noqa: F401 - registers the fixture game
from lgbg.core.config import RunConfig
from lgbg.host.facade import SessionExistsError, SessionFacade, SessionNotFoundError
from lgbg.host.registry import InvalidSessionIdError, SessionRegistry


def config(seed: int = 1) -> RunConfig:
    return RunConfig(seed=seed, players=2, interaction_protocol="decline_only")


def test_the_registry_assigns_an_id_and_remembers_the_game() -> None:
    registry = SessionRegistry(SessionFacade())

    game_id = registry.create("fixture", config())

    assert game_id.startswith("g-")
    assert registry.game_of(game_id) == "fixture"
    assert registry.sessions() == [game_id]


def test_a_second_client_cannot_claim_an_id_already_in_use() -> None:
    registry = SessionRegistry(SessionFacade())
    game_id = registry.create("fixture", config(), game_id="g-shared")

    with pytest.raises(SessionExistsError):
        registry.create("fixture", config(seed=2), game_id="g-shared")

    assert registry.game_of(game_id) == "fixture"


def test_an_id_that_is_not_a_path_segment_is_refused_before_it_is_used() -> None:
    registry = SessionRegistry(SessionFacade())

    for bad in ("", "../escape", "with space", "x" * 65):
        with pytest.raises(InvalidSessionIdError):
            registry.create("fixture", config(), game_id=bad)


def test_an_unknown_id_is_not_found_and_ending_forgets_the_session(tmp_path: Path) -> None:
    registry = SessionRegistry(SessionFacade())
    game_id = registry.create("fixture", config(), directory=tmp_path)

    registry.end(game_id)

    assert registry.sessions() == []
    with pytest.raises(SessionNotFoundError):
        registry.game_of(game_id)
    with pytest.raises(SessionNotFoundError):
        registry.end(game_id)
