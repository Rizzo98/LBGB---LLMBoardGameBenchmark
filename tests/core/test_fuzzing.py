"""The generic harness, driven against the games that exist (FR-22; kanban card K-064).

Two plugins and three policies: the fixture game, which exists as a canary for the platform rather
than as a game anybody plays, and Catan. What is asserted is the harness's own claims - it does not
object to a game that merely wanders, and it does not pass a game that breaks something it declared
about itself.
"""

from __future__ import annotations

from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.fuzzing import POLICIES, run_fuzz, uniform
from lgbg.core.game import InvariantViolation, get_game
from tests.games.fixture_game import PLAYERS as FIXTURE_PLAYERS
from tests.games.fixture_game import FixtureGame

GAME: Final[Any] = get_game("catan")
FIXTURE: Final[Any] = get_game(FixtureGame.name)
LIVELOCK_SEED: Final[int] = 20260901
"""The seed K-062 measured as not finishing inside four thousand actions, so a short cap of it is
a livelock by construction rather than by luck.
"""


def _config(seed: int = 20261201, *, for_catan: bool = True, players: int = 4) -> RunConfig:
    options = {"board": "fixed:standard_a"} if for_catan else {}
    return RunConfig(
        seed=seed,
        players=players,
        interaction_protocol="decline_only",
        game_config=GameConfig(options),
    )


def test_the_harness_drives_any_registered_plugin() -> None:
    """FR-22.5: the fixture game is the canary, and the harness has to handle it too."""
    # The fixture game declares its own number of seats; the harness takes the config at its word,
    # so the test hands it one the game can answer for.
    config = _config(for_catan=False, players=FIXTURE_PLAYERS)
    report = run_fuzz(FIXTURE, config, max_actions=200)

    assert report.actions > 0, "the harness must have played something"
    assert report.clean, report.offenders


def test_every_policy_drives_catan_without_breaking_a_declaration() -> None:
    for name, policy in sorted(POLICIES.items()):
        report = run_fuzz(GAME, _config(), policy=policy, max_actions=200)

        assert report.clean, f"{name}: {report.offenders[:3]}"
        assert report.actions > 20, f"{name} barely played"


def test_a_game_that_will_not_end_is_reported_as_a_livelock() -> None:
    """FR-22.4: a livelock is not a rule failure, and this one is a measured livelock."""
    report = run_fuzz(GAME, _config(seed=LIVELOCK_SEED), policy=uniform, max_actions=300)

    assert report.finished is False
    assert report.livelock is True
    assert report.clean, "wandering is not breaking a declaration"


def test_the_harness_fails_a_game_that_breaks_its_own_declaration(monkeypatch: Any) -> None:
    """The control: a harness that never objects to anything proves nothing."""

    def broken(self: Any, state: Any) -> list[Any]:
        return [InvariantViolation(invariant="toy", detail="deliberately broken")]

    monkeypatch.setattr(type(GAME), "check_invariants", broken)

    report = run_fuzz(GAME, _config(), policy=uniform, max_actions=40)

    assert report.clean is False
    assert any("toy" in offender for offender in report.offenders)
