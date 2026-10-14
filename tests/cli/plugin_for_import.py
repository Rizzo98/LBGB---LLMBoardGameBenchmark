"""A game that lives outside the engine, used to test the --plugin discovery path.

It is not named test_*, so pytest never imports it: the only thing that imports it is the
test that asks the CLI to. That is the point - importing a module is what registers a game.
"""

from __future__ import annotations

from typing import Any

from lgbg.core.game import register_game
from lgbg.core.types import DecisionRequest
from tests.games.fixture_game import FixtureGame


@register_game
class ImportedGame(FixtureGame):
    """The fixture again, under another name, from another module."""

    name = "imported"
    rules_version = "imported-rules-1"
    schema_version = "imported-actions-1"


@register_game
class TwoDecisions(FixtureGame):
    """A plugin with two decisions open for one player, so a driver must refuse to guess."""

    name = "two_decisions"
    rules_version = "two-decisions-rules-1"
    schema_version = "two-decisions-actions-1"

    def pending_decisions(self, state: Any) -> list[DecisionRequest]:
        return [
            DecisionRequest(
                request_id="d0",
                player=0,
                kind="turn",
                schema_ref="turn",
                context={"which": "first"},
                phase="play",
            ),
            DecisionRequest(
                request_id="d1",
                player=0,
                kind="turn",
                schema_ref="turn",
                context={"which": "second"},
                phase="play",
            ),
        ]
