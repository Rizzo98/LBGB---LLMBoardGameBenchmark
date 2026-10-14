"""A game that lives outside the engine, used to test the --plugin discovery path.

It is not named test_*, so pytest never imports it: the only thing that imports it is the
test that asks the CLI to. That is the point - importing a module is what registers a game.
"""

from __future__ import annotations

from lgbg.core.game import register_game
from tests.games.fixture_game import FixtureGame


@register_game
class ImportedGame(FixtureGame):
    """The fixture again, under another name, from another module."""

    name = "imported"
    rules_version = "imported-rules-1"
    schema_version = "imported-actions-1"
